"""One fixed multitask engineering batch; app owns all model state transitions."""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform as host_platform
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from studies.construction import run as single
from modelspine_protocols import ArtifactRef, decode, digest, dumps, loads, ref, require, to_data
from support.task_oracle import EvaluationSpec, pin_evaluation_spec

FIXTURES = ROOT / "tests" / "fixtures" / "construction" / "multitask"
CARDS = ROOT / "domain-packs" / "structural-graph" / "construction" / "multitask"
CASE_IDS = ("fork-stage1", "diamond", "disconnected", "fork-stage2", "unsupported-cycle")


def bind_reference(case_id, inputs, card_path):
    """Bind fixed successor semantics to a task using a distinct artifact version."""
    index = json.loads((FIXTURES / "reference-index.json").read_text(encoding="utf-8"))
    name = case_id + "-reference.json"
    raw = (FIXTURES / name).read_bytes()
    template_ref = decode(ArtifactRef, index[name])
    template = pin_evaluation_spec(raw, template_ref)
    spec = loads(EvaluationSpec, template.content.decode("utf-8"))
    card_raw = card_path.read_bytes()
    card = json.loads(card_raw)
    require(spec.task_ref == decode(ArtifactRef, card["task_ref"]),
            "reference template does not match fixed case task", "conflict")
    prepared = inputs[0]
    if case_id == "fork-stage2":
        require(card["predecessor"] is not None, "successor reference needs predecessor", "conflict")
        require((prepared.task_ref.project_id, prepared.task_ref.artifact_id, prepared.task_ref.revision) ==
                (spec.task_ref.project_id, spec.task_ref.artifact_id,
                 spec.task_ref.revision + "/bound-" + digest(ref(inputs[2]))),
                "successor reference requires the bound successor task", "conflict")
        version = spec.version + "/bound-" + digest(prepared.task_ref)
        content = dumps(replace(spec, task_ref=prepared.task_ref, version=version)).encode("utf-8")
        bound_ref = replace(template_ref, revision=version, content_hash=sha256(content).hexdigest())
        pinned = pin_evaluation_spec(content, bound_ref)
    else:
        require(spec.task_ref == prepared.task_ref, "reference task does not match prepared task", "conflict")
        pinned = template
    require(loads(EvaluationSpec, pinned.content.decode("utf-8")).task_ref == prepared.task_ref,
            "bound reference task mismatch", "conflict")
    return pinned, {
        "template_ref": to_data(template_ref), "template_content": raw.decode("utf-8"),
        "bound_ref": to_data(pinned.spec_ref), "bound_content": pinned.content.decode("utf-8"),
        "card_sha256": sha256(card_raw).hexdigest(),
        "reason": "fixed successor cases; bind task_ref with distinct reference version" if case_id == "fork-stage2"
                  else "fixed initial reference; no rebinding",
    }


def source_hashes():
    hashes = single.source_hashes()
    paths = [ROOT / "tests" / "test_construction_multitask.py",
             ROOT / "tests" / "test_construction_cases.py",
             Path(__file__).with_name("multitask-protocol.md")]
    paths += [p for p in FIXTURES.rglob("*") if p.is_file()]
    paths += [p for p in CARDS.rglob("*") if p.is_file()]
    for path in paths:
        hashes[path.relative_to(ROOT).as_posix()] = sha256(path.read_bytes()).hexdigest()
    return dict(sorted(hashes.items()))


def collect(checkpoint=None):
    # Do not consume evaluator truth fields to select, repair or skip an app candidate.
    planned = [{"id": f"{case_id}/{condition}", "case_id": case_id, "condition": condition,
                "predecessor": f"fork-stage1/{condition}" if case_id == "fork-stage2" else None,
                "trajectory": f"fork/{condition}" if case_id.startswith("fork-") else None}
               for condition in single.CONDITIONS for case_id in CASE_IDS]
    def git(*args):
        return subprocess.check_output(["git", "-c", f"safe.directory={ROOT.as_posix()}",
                                        "-C", str(ROOT), *args], text=True).strip()
    record = {
        "schema": "construction-multitask/0.1", "started_utc": datetime.now(timezone.utc).isoformat(),
        "planned_trials": planned, "planned": len(planned), "core_task_structures": 3,
        "independent_statistical_samples": False, "git_head": git("rev-parse", "HEAD"),
        "git_status_before": git("status", "--short"), "python": sys.version,
        "host_platform": host_platform.platform(), "source_hashes_before": source_hashes(),
        "trials": [], "active_trial": None, "run_status": "in_progress", "source_stable_during_run": None,
    }
    parents = {}

    def persist():
        observed = record["trials"] + ([record["active_trial"]] if record["active_trial"] else [])
        record.update(started=sum(t.get("started") is True for t in observed),
                      terminal=sum(t.get("started") is True for t in record["trials"]),
                      not_started=sum(t.get("status") == "not_started" for t in record["trials"]),
                      returned=sum(t.get("returned") is True for t in observed),
                      saved=sum(t.get("saved") is True for t in observed),
                      reference_error_trials=sum(t.get("reference_status") == "error" for t in observed),
                      preparation_error_trials=sum(t.get("error_stage") == "input_or_reference_preparation"
                                                   for t in observed),
                      status_counts={status: sum(t.get("status") == status for t in observed)
                                     for status in ("candidate_found", "exhausted", "budget_exhausted",
                                                    "unknown", "error", "not_started")})
        if checkpoint is not None:
            checkpoint(record)

    persist()
    for planned_trial in planned:
        case_id, condition = planned_trial["case_id"], planned_trial["condition"]
        card_path = CARDS / case_id / "card.json"
        metadata = {**planned_trial, "planned": True, "card": card_path.relative_to(ROOT).as_posix(),
                    "human_setup_seconds": None, "human_incremental_seconds": None,
                    "human_cost_reason": "setup and incremental reuse time not measured",
                    "human_seconds": None, "human_seconds_reason": "design/build/review time not measured",
                    "compute_cost": None, "compute_cost_reason": "not metered", "llm_calls": 0, "paid_api_cost": 0}
        parent = parents.get(condition)
        if planned_trial["predecessor"] and (parent is None or parent[1].run is None or parent[1].run.commit is None):
            predecessor = next(t for t in record["trials"] if t["id"] == planned_trial["predecessor"])
            record["trials"].append({**metadata, "status": "not_started", "started": False,
                                     "returned": False, "saved": None, "app_started": False,
                                     "reference_status": "not_run", "reason": "predecessor did not return a commit",
                                     "predecessor_status": predecessor["status"],
                                     "predecessor_reason": predecessor["reason"],
                                     "wall_seconds": None, "preparation_seconds": None,
                                     "reference_seconds": None, "counts": None, "llm_calls": 0})
            persist()
            continue
        record["active_trial"] = {**metadata, "started": True, "app_started": False,
                                  "reference_status": "not_run"}
        persist()
        preparation_start = perf_counter()
        try:
            inputs = (single.bounded_generation.advance_construction(*parent, card_path) if planned_trial["predecessor"]
                      else single.bounded_generation.load_construction_case(card_path))
            pinned, binding = bind_reference(case_id, inputs, card_path)
            card = json.loads(card_path.read_bytes())
            task_template_raw = (card_path.parent / card["task"]).read_bytes()
            task_raw = dumps(inputs[0].contract).encode("utf-8") if planned_trial["predecessor"] else task_template_raw
            require(sha256(task_raw).hexdigest() == inputs[0].task_ref.content_hash,
                    "recorded task bytes do not match prepared reference", "conflict")
        except Exception as exc:
            preparation_seconds = perf_counter() - preparation_start
            record["trials"].append({**record["active_trial"], "status": "error", "returned": False,
                                     "saved": None, "error_stage": "input_or_reference_preparation",
                                     "exception_type": type(exc).__name__, "exception_code": getattr(exc, "code", None),
                                     "reason": str(exc), "preparation_seconds": preparation_seconds,
                                     "wall_seconds": None, "reference_seconds": None, "counts": None, "llm_calls": 0})
            record["active_trial"] = None
            persist()
            continue
        preparation_seconds = perf_counter() - preparation_start
        metadata.update(preparation_seconds=preparation_seconds, reference_binding=binding,
                        task_content=task_raw.decode("utf-8"), space_content=inputs[3].decode("utf-8"),
                        task_template_ref=card["task_ref"], space_template_ref=card["space_ref"],
                        input_snapshot=to_data(ref(inputs[2])),
                        predecessor_accepted=to_data(parent[1].run.commit.snapshot) if planned_trial["predecessor"] else None)

        def app_checkpoint(trial):
            record["active_trial"] = {**trial, **metadata, "app_started": True}
            persist()

        def receive_result(result):
            if case_id == "fork-stage1":
                parents[condition] = (inputs, result)

        trial = single.observe_trial(planned_trial["id"], condition, inputs, pinned,
                                     checkpoint=app_checkpoint, result_sink=receive_result)
        record["trials"].append({**trial, **metadata, "app_started": True})
        record["active_trial"] = None
        persist()
    record.update(run_status="error" if record["preparation_error_trials"] else
                             "reference_error" if record["reference_error_trials"] else "complete",
                  finished_utc=datetime.now(timezone.utc).isoformat(), source_hashes_after=source_hashes())
    record["source_stable_during_run"] = record["source_hashes_before"] == record["source_hashes_after"]
    persist()
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump({"schema": "construction-multitask/0.1", "run_status": "initializing", "trials": []}, stream)
        stream.write("\n")
    try:
        record = collect(checkpoint=lambda value: single._write_checkpoint(output, value))
    except Exception as exc:
        record = json.loads(output.read_text(encoding="utf-8"))
        record.update(run_status="error", run_error={"exception_type": type(exc).__name__, "reason": str(exc)},
                      finished_utc=datetime.now(timezone.utc).isoformat())
        single._write_checkpoint(output, record)
        raise
    print(json.dumps({key: record[key] for key in ("planned", "started", "terminal", "not_started", "returned", "saved",
                                                  "status_counts", "reference_error_trials", "preparation_error_trials", "run_status",
                                                  "source_stable_during_run")}, indent=2))
    return 0 if record["run_status"] == "complete" and record["source_stable_during_run"] else 2


if __name__ == "__main__":
    sys.exit(main())
