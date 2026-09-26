"""Construct one DAG edit within pinned inputs, then apply fixed task acceptance."""
import argparse
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap
bootstrap.activate(("generation", "model-kernel", "assurance"))
sys.path.insert(0, str(bootstrap.PLATFORM / "adapters"))

from dag_construction import DagEditSpace, prepare_dag
from fixtures import load_case
from task_acceptance import EngineeringTaskCard, SourcePath, TaskRunResult, _inside, run_task
from task_checks import check_tasks
from task_contracts import load_task
from modelspine_assurance.tasks import PreparedTask, prepare_task
from modelspine_generation.bounded import CandidateEvaluation, ConstructionRun, search
from modelspine_kernel import ModelKernel
from modelspine_protocols import (
    ArtifactRef, ContractError, EvidenceRef, Metamodel, Snapshot, digest, dumps, loads, ref, require, to_data,
    select_scope, validate_artifact_ref, validate_model, validate_report,
)


@dataclass(frozen=True)
class BoundedTaskRun:
    space_ref: ArtifactRef
    search: ConstructionRun
    run: TaskRunResult | None


@dataclass(frozen=True)
class ConstructionCaseCard:
    schema_version: Literal["construction-case/0.1"]
    metamodel: str
    model: str
    task: str
    task_ref: ArtifactRef
    sources: tuple[SourcePath, ...]
    space: str
    space_ref: ArtifactRef
    predecessor: ArtifactRef | None


def _pinned_space(prepared_task, snapshot, space_bytes, space_ref):
    require(prepared_task.contract.base == ref(snapshot), "task initial snapshot mismatch", "conflict")
    space_ref = validate_artifact_ref(space_ref)
    require(type(space_bytes) is bytes, "edit space requires original bytes")
    require(sha256(space_bytes).hexdigest() == space_ref.content_hash, "edit space hash mismatch", "conflict")
    try:
        text = space_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("invalid", "edit space requires UTF-8") from exc
    space = loads(DagEditSpace, text)
    require((space_ref.project_id, space_ref.artifact_id, space_ref.revision) ==
            (snapshot.project_id, space.id, space.version), "edit space identity mismatch", "conflict")
    require(space.task_ref == prepared_task.task_ref and space.base == prepared_task.contract.base,
            "edit space task/base mismatch", "conflict")
    return space


def run_construction(prepared_task, metamodel, snapshot, space_bytes, space_ref,
                     *, controller=None, construction_plan=None) -> BoundedTaskRun:
    """Trusted host; reference answers never enter construction or task acceptance.

    A controller and its plan may be explicitly injected together. They change
    preconstruction decisions only; the builder and final checker stay fixed.
    """
    require(type(prepared_task) is PreparedTask, "expected prepared task")
    check_plan = prepared_task.contract.plan
    require(check_plan is not None, "construction requires a fixed task check plan", "unsupported")
    require(digest(check_plan) == prepared_task.plan_hash, "prepared plan changed", "conflict")
    require((controller is None) == (construction_plan is None),
            "controller and construction plan must be provided together")
    space = _pinned_space(prepared_task, snapshot, space_bytes, space_ref)
    actor = "bounded-construction-host"
    kernel = ModelKernel(snapshot, metamodel, check_plan, check_tasks, frozenset({actor}))
    intent_refs = tuple(dict.fromkeys((
        EvidenceRef(prepared_task.task_ref, "artifact", "fixed-task-contract"),
        EvidenceRef(space_ref, "artifact", "fixed-edit-space"),
        *(e for s in prepared_task.contract.statements for e in s.source_refs),
    )))
    constructor = prepare_dag(snapshot, check_plan, space, intent_refs)

    def evaluate(proposal):
        # Only kernel.preview creates candidates; the search core trusts this
        # host for proposal-to-candidate semantics and validates report bindings.
        candidate = kernel.preview(proposal).candidate
        return CandidateEvaluation(candidate, check_tasks(candidate, check_plan))

    result = search(snapshot, prepared_task.task_ref, check_plan,
                    constructor.plan if construction_plan is None else construction_plan,
                    constructor.options, space.max_options,
                    constructor.control if controller is None else controller,
                    constructor.build, evaluate)
    run = None
    if result.status == "candidate_found":
        # Repeat the real fixed-task acceptance boundary before saving. Search
        # success alone never authorizes a model commit.
        run = run_task(prepared_task, metamodel, snapshot, result.proposal, check_tasks, actor)
    return BoundedTaskRun(space_ref, result, run)


def _case_path(folder, relative):
    require(type(relative) is str and bool(relative) and not Path(relative).anchor,
            "case paths must be relative")
    return _inside(folder, relative)


def _source_paths(folder, sources):
    paths = {}
    for source in sources:
        require(source.ref not in paths, "duplicate task card source")
        paths[source.ref] = _case_path(folder, source.path)
    return paths


def _read_case(card_path):
    card_path = Path(card_path)
    folder = card_path.parent
    card = loads(ConstructionCaseCard, card_path.read_text(encoding="utf-8"))
    paths = _source_paths(folder, card.sources)
    prepared = load_task(_case_path(folder, card.task), card.task_ref, paths)
    metamodel = loads(Metamodel, _case_path(folder, card.metamodel).read_text(encoding="utf-8"))
    snapshot = loads(Snapshot, _case_path(folder, card.model).read_text(encoding="utf-8"))
    validate_model(snapshot, metamodel)
    raw = _case_path(folder, card.space).read_bytes()
    _pinned_space(prepared, snapshot, raw, card.space_ref)
    return card, (prepared, metamodel, snapshot, raw, card.space_ref), paths


def load_construction_case(card_path: Path):
    """Load pinned task/model/space inputs, with no preselected proposal file."""
    card, inputs, _ = _read_case(card_path)
    require(card.predecessor is None, "successor case requires a committed predecessor", "conflict")
    return inputs


def advance_construction(previous_inputs, previous_result: BoundedTaskRun, card_path: Path):
    """Bind a predeclared additive task to this app's actual accepted snapshot.

    This is trusted local composition, not a portable commit-authentication API.
    Sources and goals come from the pinned template; only base/version links change.
    """
    parent, meta, before, previous_raw, previous_ref = previous_inputs
    require(type(parent) is PreparedTask and type(previous_result) is BoundedTaskRun,
            "expected prepared predecessor and bounded app result")
    _pinned_space(parent, before, previous_raw, previous_ref)
    run, search_result = previous_result.run, previous_result.search
    require(run is not None and run.commit is not None, "predecessor did not commit", "conflict")
    require(search_result.task_ref == parent.task_ref and search_result.base == ref(before)
            and search_result.plan.check_plan_hash == parent.plan_hash
            and previous_result.space_ref == previous_ref,
            "predecessor result input mismatch", "conflict")
    accepted = run.accepted
    validate_model(accepted, meta)
    require(search_result.status == "candidate_found" and search_result.proposal is not None
            and search_result.proposal.base == ref(before)
            and run.commit.proposal_id == search_result.proposal.proposal_id
            and run.commit.snapshot == ref(accepted) and run.candidate == accepted
            and run.assessment.task_ref == parent.task_ref and run.assessment.candidate == ref(accepted)
            and run.assessment.goal_status == "satisfied" and run.assessment.intent_status == "ready"
            and (accepted.project_id, accepted.model_id, accepted.metamodel, accepted.metamodel_hash)
                == (before.project_id, before.model_id, before.metamodel, before.metamodel_hash)
            and accepted.revision == before.revision + 1,
            "predecessor commit/accepted binding mismatch", "conflict")
    require(parent.contract.plan is not None, "predecessor requires a fixed plan", "conflict")
    for report in (run.assessment.report, run.commit.report):
        require(validate_report(report, accepted, parent.contract.plan,
                                select_scope(parent.contract.plan)).satisfied,
                "predecessor report did not satisfy the fixed task", "conflict")
    card, template_inputs, paths = _read_case(card_path)
    template, next_meta, template_base, raw, space_ref = template_inputs
    require(card.predecessor == parent.task_ref, "successor predecessor task mismatch", "conflict")
    require(next_meta == meta and ref(template_base) == ref(before),
            "successor template model/base mismatch", "conflict")
    old_task, task = parent.contract, template.contract
    require(task.id == old_task.id and task.version != old_task.version,
            "successor needs the same task ID and a new version", "conflict")
    require(old_task.plan is not None and task.plan is not None, "successor requires fixed plans", "unsupported")
    require(task.plan.id == old_task.plan.id and task.plan.version != old_task.plan.version
            and task.plan.rule_version == old_task.plan.rule_version
            and task.plan.assumptions == old_task.plan.assumptions,
            "successor plan identity/version or assumptions mismatch", "conflict")
    for old, new, label in ((old_task.statements, task.statements, "statements"),
                            (old_task.plan.obligations, task.plan.obligations, "obligations"),
                            (old_task.bindings, task.bindings, "bindings")):
        require(all(item in new for item in old), f"successor must preserve parent {label}", "conflict")
    suffix = "/bound-" + digest(ref(accepted))
    bound = replace(task, base=ref(accepted), version=task.version + suffix)
    task_raw = dumps(bound).encode("utf-8")
    task_ref = replace(template.task_ref, revision=bound.version, content_hash=sha256(task_raw).hexdigest())
    prepared = prepare_task(task_raw, task_ref, {source: path.read_bytes() for source, path in paths.items()})
    space = loads(DagEditSpace, raw.decode("utf-8"))
    space = replace(space, base=ref(accepted), task_ref=task_ref, version=space.version + suffix)
    space_raw = dumps(space).encode("utf-8")
    bound_space_ref = replace(space_ref, revision=space.version, content_hash=sha256(space_raw).hexdigest())
    return prepared, meta, accepted, space_raw, bound_space_ref


def load_example():
    folder = bootstrap.PLATFORM / "domain-packs" / "structural-graph"
    task_folder = folder / "tasks"
    card = loads(EngineeringTaskCard, (task_folder / "card.json").read_text(encoding="utf-8"))
    prepared = load_task(_inside(task_folder, card.task), card.task_ref, _source_paths(task_folder, card.sources))
    metamodel, snapshot, _ = load_case(folder)
    construction = folder / "construction"
    return (prepared, metamodel, snapshot, (construction / "space.json").read_bytes(),
            loads(ArtifactRef, (construction / "space-ref.json").read_text(encoding="utf-8")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, help="explicit initial construction case card")
    args = parser.parse_args()
    try:
        result = run_construction(*(load_example() if args.case is None else load_construction_case(args.case)))
    except (ContractError, OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "code": getattr(exc, "code", "invalid"),
                          "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(to_data(result), ensure_ascii=False, indent=2))
    return 0 if result.run and result.run.commit is not None else 1


if __name__ == "__main__":
    sys.exit(main())
