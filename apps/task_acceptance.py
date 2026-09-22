"""Apply an explicit proposal only after fixed declared task goals are satisfied."""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap
bootstrap.activate(("protocols", "model-kernel", "assurance"))
sys.path.insert(0, str(bootstrap.PLATFORM / "adapters"))

from fixtures import load_case
from task_contracts import load_task
from task_checks import check_tasks
from modelspine_assurance.tasks import PreparedTask, assess_task
from modelspine_kernel import ModelKernel
from modelspine_protocols import (
    ArtifactRef, ChangeProposal, Checker, Commit, ContractError, Metamodel, Snapshot,
    TaskAssessment, digest, loads, ref, require, to_data, validate_model,
)


@dataclass(frozen=True)
class TaskRunResult:
    assessment: TaskAssessment
    commit: Commit | None
    candidate: Snapshot | None
    accepted: Snapshot
    reason: str


@dataclass(frozen=True)
class SourcePath:
    ref: ArtifactRef
    path: str


@dataclass(frozen=True)
class EngineeringTaskCard:
    schema: Literal["engineering-task-card/0.1"]
    task: str
    task_ref: ArtifactRef
    sources: tuple[SourcePath, ...]
    proposal: str


def run_task(prepared_task: PreparedTask, metamodel: Metamodel, snapshot: Snapshot,
             proposal: ChangeProposal, checker: Checker, actor: str) -> TaskRunResult:
    require(type(prepared_task) is PreparedTask, "expected prepared task")
    require(ref(snapshot) == prepared_task.contract.base, "task initial snapshot mismatch", "conflict")
    validate_model(snapshot, metamodel)
    require(type(actor) is str and bool(actor.strip()), "empty task actor")
    plan = prepared_task.contract.plan
    if plan is None:
        assessment = assess_task(prepared_task, None, checker)
        return TaskRunResult(assessment, None, None, snapshot, "no executable check plan")

    def pinned_check(candidate, actual_plan, scope=None):
        require(digest(actual_plan) == prepared_task.plan_hash and actual_plan == plan,
                "task check plan changed", "conflict")
        return checker(candidate, actual_plan, scope)

    kernel = ModelKernel(snapshot, metamodel, plan, pinned_check, frozenset({actor}))
    preview = kernel.preview(proposal)
    assessment = assess_task(prepared_task, preview.candidate, pinned_check)
    if assessment.intent_status != "ready" or assessment.goal_status != "satisfied":
        return TaskRunResult(assessment, None, preview.candidate, kernel.snapshot(),
                             "required intent unresolved or declared goals not satisfied")
    decision = kernel.decide(proposal, assessment.report, actor)
    commit = kernel.apply(proposal, decision, actor)
    return TaskRunResult(assessment, commit, preview.candidate, kernel.snapshot(),
                         "declared goals satisfied; model saved")


def _inside(folder: Path, relative: str) -> Path:
    require(type(relative) is str and bool(relative), "empty task card path")
    path = (folder / relative).resolve()
    require(path.is_relative_to(folder.resolve()), "task card path escapes its directory")
    return path


def load_example(profile: str):
    require(profile in ("structural-graph", "finite-automaton"), "unsupported engineering example")
    folder = bootstrap.PLATFORM / "domain-packs" / profile
    task_folder = folder / "tasks"
    # Cards are trusted application assembly, selected before the candidate.
    card = loads(EngineeringTaskCard, (task_folder / "card.json").read_text(encoding="utf-8"))
    source_paths = {}
    for item in card.sources:
        require(item.ref not in source_paths, "duplicate task card source")
        source_paths[item.ref] = _inside(task_folder, item.path)
    prepared = load_task(_inside(task_folder, card.task), card.task_ref, source_paths)
    metamodel, snapshot, _ = load_case(folder)
    proposal = loads(ChangeProposal, _inside(task_folder, card.proposal).read_text(encoding="utf-8"))
    return prepared, metamodel, snapshot, proposal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=("structural-graph", "finite-automaton"))
    args = parser.parse_args()
    try:
        prepared, metamodel, snapshot, proposal = load_example(args.profile)
        result = run_task(prepared, metamodel, snapshot, proposal, check_tasks, "task-author")
    except (ContractError, OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "code": getattr(exc, "code", "invalid"),
                          "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(to_data(result), ensure_ascii=False, indent=2))
    return 0 if result.commit is not None else 1


if __name__ == "__main__":
    sys.exit(main())
