"""Run the predeclared finite mechanism comparisons; never feed back the oracle."""
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
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps"))
sys.path.insert(0, str(ROOT / "tests"))

import bounded_generation
from bounded_generation import load_example, run_construction
from dag_construction import DagEditSpace
from modelspine_generation.bounded import ConstructionDecision
from modelspine_protocols import ArtifactRef, decode, digest, dumps, loads, to_data
from studies.construction.controls import control_plan, ordinary_control
from support.task_oracle import evaluate_candidate, pin_evaluation_spec

CONDITIONS = ("terminal-only", "dag-construction", "ordinary-rule")
SCENARIOS = (
    ("budget-1", {"max_options": 1}),
    ("budget-2", {"max_options": 2}),
    ("budget-3", {"max_options": 3}),
    ("budget-9", {"max_options": 9}),
    ("only-valid", {"sources": ("node-a",), "destinations": ("node-c",), "max_options": 1}),
    ("only-invalid", {"sources": ("node-a",), "destinations": ("node-a",), "max_options": 1}),
    ("unchanged", {"sources": ("node-b",), "destinations": ("node-c",), "max_options": 1}),
)


def reference_spec():
    folder = ROOT / "tests" / "fixtures" / "task-acceptance"
    index = json.loads((folder / "reference-index.json").read_text(encoding="utf-8"))
    return pin_evaluation_spec((folder / "graph-reference.json").read_bytes(),
                               decode(ArtifactRef, index["graph-reference.json"]))


def scenario_inputs(inputs, changes):
    prepared, meta, snapshot, raw, reference = inputs
    space = replace(loads(DagEditSpace, raw.decode("utf-8")), **changes)
    raw = dumps(space).encode("utf-8")
    return prepared, meta, snapshot, raw, replace(reference, content_hash=sha256(raw).hexdigest())


def execute_condition(condition, inputs, fault=None):
    if condition not in CONDITIONS:
        raise ValueError("unknown study condition")
    if condition == "dag-construction":
        if fault is not None:
            raise ValueError("fault probes use ordinary-rule only")
        return run_construction(*inputs)
    prepared, _, snapshot, raw, _ = inputs
    space = loads(DagEditSpace, raw.decode("utf-8"))
    if fault not in (None, "unknown", "error", "exception"):
        raise ValueError("unknown fault probe")

    def controller(option):
        if fault == "exception":
            raise RuntimeError("explicit engineering controller exception")
        if fault is not None:
            return ConstructionDecision(digest(option), fault, "explicit engineering fault probe")
        return ordinary_control(snapshot, space, option, terminal_only=condition == "terminal-only")

    return run_construction(*inputs, controller=controller,
                            construction_plan=control_plan(prepared.contract.plan,
                                                           ordinary=condition == "ordinary-rule"))


def observe_trial(trial_id, condition, inputs, pinned, fault=None):
    record = {"id": trial_id, "condition": condition, "fault": fault,
              "stratum": "injected-fault" if fault else "comparison",
              "planned": True, "started": True, "task_ref": to_data(inputs[0].task_ref),
              "base": to_data(inputs[0].contract.base), "space_ref": to_data(inputs[4]),
              "space": json.loads(inputs[3]), "reference_ref": to_data(pinned.spec_ref),
              "llm_calls": 0, "paid_api_cost": 0,
              "compute_cost": None, "compute_cost_reason": "not metered",
              "human_seconds": None, "human_seconds_reason": "design/build/review time not measured"}
    checker_calls = 0
    original_checker = bounded_generation.check_tasks

    def counted_checker(*args, **kwargs):
        nonlocal checker_calls
        checker_calls += 1
        return original_checker(*args, **kwargs)

    start = perf_counter()
    try:
        with patch.object(bounded_generation, "check_tasks", counted_checker):
            result = execute_condition(condition, inputs, fault)
        elapsed = perf_counter() - start
    except Exception as exc:
        elapsed = perf_counter() - start
        # An experiment boundary must preserve failed attempts. No replacement,
        # retry, fabricated trace, success or suppressed exception information.
        record.update(status="error", returned=False, exception_type=type(exc).__name__,
                      reason=str(exc), app_result=None, counts=None, saved=None,
                      counts_reason="app raised; no ConstructionRun trace returned",
                      saved_reason="app raised without returning an acceptance result",
                      independent_candidates=[], independent_saved=None)
    else:
        record.update(status=result.search.status, returned=True, reason=result.search.reason,
                      app_result=to_data(result), saved=bool(result.run and result.run.commit))
        steps = result.search.steps
        record["counts"] = {
            "considered": len(steps),
            "excluded": sum(s.decision.status == "exclude" for s in steps),
            "no_change": sum(s.decision.status == "no_change" for s in steps),
            "constructed": sum(s.proposal is not None for s in steps),
            "search_candidate_checks": sum(s.evaluation is not None for s in steps),
            "final_acceptance_checker_calls": checker_calls - sum(s.evaluation is not None for s in steps),
        }
    record["wall_seconds"] = elapsed
    record["total_development_checker_calls"] = checker_calls
    reference_start = perf_counter()
    if record["returned"]:
        # This is deliberately after the complete app call and its save decision.
        record["independent_candidates"] = [
            {"option": s.option.id, "evaluation": to_data(evaluate_candidate(s.evaluation.candidate, pinned))}
            for s in result.search.steps if s.evaluation is not None]
        record["independent_saved"] = (to_data(evaluate_candidate(result.run.accepted, pinned))
                                          if record["saved"] else None)
    record["reference_seconds"] = perf_counter() - reference_start if record["returned"] else None
    return record


def source_hashes():
    paths = set()
    for folder in ("packages", "adapters", "apps"):
        paths.update((ROOT / folder).rglob("*.py"))
    paths.update((ROOT / "domain-packs" / "structural-graph").rglob("*.json"))
    paths.update((ROOT / "domain-packs" / "structural-graph").rglob("*.txt"))
    paths.update((ROOT / "studies" / "construction").glob("*.py"))
    paths.add(ROOT / "studies" / "construction" / "protocol.md")
    paths.add(ROOT / "tests" / "support" / "task_oracle.py")
    paths.add(ROOT / "tests" / "test_construction_study.py")
    paths.update((ROOT / "tests" / "fixtures" / "construction").glob("*"))
    for name in ("graph-reference.json", "reference-index.json"):
        paths.add(ROOT / "tests" / "fixtures" / "task-acceptance" / name)
    return {p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths) if p.is_file()}


def collect():
    pinned = reference_spec()  # Pin evaluator bytes before any candidate call.
    inputs = load_example()
    planned = [(f"{name}/{condition}", condition, changes, None)
               for name, changes in SCENARIOS for condition in CONDITIONS]
    planned += [(f"fault-{fault}/ordinary-rule", "ordinary-rule", {"max_options": 3}, fault)
                for fault in ("unknown", "error", "exception")]
    def git(*arguments):
        return subprocess.check_output(["git", "-c", f"safe.directory={ROOT.as_posix()}",
                                        "-C", str(ROOT), *arguments], text=True).strip()
    before = source_hashes()
    record = {"schema": "construction-pilot/0.1", "started_utc": datetime.now(timezone.utc).isoformat(),
              "task_count": 1, "independent_statistical_samples": False,
              "planned_trials": [p[0] for p in planned], "planned": len(planned),
              "git_head": git("rev-parse", "HEAD"), "git_status_before": git("status", "--short"),
              "python": sys.version, "host_platform": host_platform.platform(),
              "source_hashes_before": before, "trials": []}
    for trial_id, condition, changes, fault in planned:
        record["trials"].append(observe_trial(trial_id, condition, scenario_inputs(inputs, changes), pinned, fault))
    trials = record["trials"]
    record.update(started=len(trials), returned=sum(t["returned"] for t in trials),
                  terminal=len(trials), saved=sum(t["saved"] is True for t in trials),
                  status_counts={s: sum(t["status"] == s for t in trials)
                                 for s in ("candidate_found", "exhausted", "budget_exhausted", "unknown", "error")},
                  finished_utc=datetime.now(timezone.utc).isoformat())
    record["source_hashes_after"] = source_hashes()
    record["source_stable_during_run"] = before == record["source_hashes_after"]
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as output:
        record = collect()
        json.dump(record, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps({k: record[k] for k in ("planned", "started", "returned", "terminal", "saved",
                                            "status_counts", "source_stable_during_run")}, indent=2))
    return 0 if record["source_stable_during_run"] else 2


if __name__ == "__main__":
    sys.exit(main())
