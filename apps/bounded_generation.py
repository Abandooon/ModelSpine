"""Construct one DAG edit within pinned inputs, then apply fixed task acceptance."""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap
bootstrap.activate(("generation", "model-kernel", "assurance"))
sys.path.insert(0, str(bootstrap.PLATFORM / "adapters"))

from dag_construction import DagEditSpace, prepare_dag
from task_acceptance import TaskRunResult, load_example as load_task_example, run_task
from task_checks import check_tasks
from modelspine_assurance.tasks import PreparedTask
from modelspine_generation.bounded import CandidateEvaluation, ConstructionRun, search
from modelspine_kernel import ModelKernel
from modelspine_protocols import (
    ArtifactRef, ContractError, EvidenceRef, digest, loads, ref, require, to_data,
    validate_artifact_ref,
)


@dataclass(frozen=True)
class BoundedTaskRun:
    space_ref: ArtifactRef
    search: ConstructionRun
    run: TaskRunResult | None


def run_construction(prepared_task, metamodel, snapshot, space_bytes, space_ref,
                     *, controller=None, construction_plan=None) -> BoundedTaskRun:
    """Trusted host; reference answers never enter construction or task acceptance.

    A controller and its plan may be explicitly injected together. They change
    preconstruction decisions only; the builder and final checker stay fixed.
    """
    require(type(prepared_task) is PreparedTask, "expected prepared task")
    require(prepared_task.contract.base == ref(snapshot), "task initial snapshot mismatch", "conflict")
    check_plan = prepared_task.contract.plan
    require(check_plan is not None, "construction requires a fixed task check plan", "unsupported")
    require(digest(check_plan) == prepared_task.plan_hash, "prepared plan changed", "conflict")
    require((controller is None) == (construction_plan is None),
            "controller and construction plan must be provided together")
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


def load_example():
    prepared, metamodel, snapshot, _ = load_task_example("structural-graph")
    folder = bootstrap.PLATFORM / "domain-packs" / "structural-graph" / "construction"
    return (prepared, metamodel, snapshot, (folder / "space.json").read_bytes(),
            loads(ArtifactRef, (folder / "space-ref.json").read_text(encoding="utf-8")))


def main():
    try:
        result = run_construction(*load_example())
    except (ContractError, OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "code": getattr(exc, "code", "invalid"),
                          "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(to_data(result), ensure_ascii=False, indent=2))
    return 0 if result.run and result.run.commit is not None else 1


if __name__ == "__main__":
    sys.exit(main())
