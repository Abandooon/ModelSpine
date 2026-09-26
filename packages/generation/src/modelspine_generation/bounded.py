"""Bounded option construction with complete terminal checking, never model writes.

The trusted host supplies domain control/build semantics and evaluates each
proposal through its actual preview/check path. This module verifies identities
and full report coverage; it cannot prove that a callback implements the option
or proposal semantics, or that the finite option space covers all solutions.
"""
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal

from modelspine_protocols import (
    ArtifactRef, ChangeProposal, CheckPlan, GenerationPlan, Property, Snapshot,
    SnapshotRef, ValidationReport, checked, digest, properties, ref, require,
    select_scope, validate_artifact_ref, validate_evidence_refs, validate_plan,
    validate_report, validate_snapshot_ref,
)


@dataclass(frozen=True)
class EditOption:
    id: str
    target: str
    values: tuple[Property, ...]


@dataclass(frozen=True)
class ConstructionDecision:
    option_hash: str
    status: Literal["allow", "exclude", "no_change", "unknown", "error"]
    reason: str


@dataclass(frozen=True)
class CandidateEvaluation:
    candidate: Snapshot
    report: ValidationReport


@dataclass(frozen=True)
class ConstructionStep:
    option: EditOption
    decision: ConstructionDecision
    proposal: ChangeProposal | None
    evaluation: CandidateEvaluation | None


@dataclass(frozen=True)
class ConstructionRun:
    task_ref: ArtifactRef
    base: SnapshotRef
    plan: GenerationPlan
    steps: tuple[ConstructionStep, ...]
    status: Literal["candidate_found", "exhausted", "budget_exhausted", "unknown", "error"]
    proposal: ChangeProposal | None
    reason: str


def _construction_plan(value: GenerationPlan, check_plan: CheckPlan) -> GenerationPlan:
    value = checked(value, GenerationPlan)
    require(value.check_plan_hash == digest(check_plan), "construction plan hash mismatch", "conflict")
    expected = {o.id: o.version for o in check_plan.obligations}
    actual = {c.obligation_id: c.obligation_version for c in value.controls}
    require(len(actual) == len(value.controls) and actual == expected,
            "construction plan obligation coverage mismatch", "conflict")
    for control in value.controls:
        require(control.stage in ("construction", "terminal-only"), "unsupported control stage", "unsupported")
        require(bool(control.fragment.strip() and control.mechanism.strip() and control.remaining.strip()),
                "missing control explanation")
    residual = {c.obligation_id for c in value.controls if c.stage == "terminal-only"}
    require(len(set(value.residual)) == len(value.residual) and set(value.residual) == residual,
            "construction residual coverage mismatch", "conflict")
    return value


def search(snapshot: Snapshot, task_ref: ArtifactRef, check_plan: CheckPlan,
           construction_plan: GenerationPlan, options: tuple[EditOption, ...], max_options: int,
           control: Callable[[EditOption], ConstructionDecision],
           build: Callable[[EditOption], ChangeProposal],
           evaluate: Callable[[ChangeProposal], CandidateEvaluation]) -> ConstructionRun:
    """Return the first fully satisfied candidate within a fixed, ordered space.

Every control call consumes one option, including excluded and unchanged ones.
Unknown/error stops the search; only a fully evaluated violation may continue.
Callback exceptions propagate. A found candidate carries no commit authority.
"""
    snapshot = checked(snapshot, Snapshot)
    base = validate_snapshot_ref(ref(snapshot))
    task_ref = validate_artifact_ref(task_ref)
    require(task_ref.project_id == base.project_id, "task/model project mismatch", "conflict")
    check_plan = validate_plan(check_plan)
    construction_plan = _construction_plan(construction_plan, check_plan)
    require(type(options) is tuple, "options must be a fixed tuple")
    options = tuple(checked(option, EditOption) for option in options)
    require(len({option.id for option in options}) == len(options), "duplicate option ID")
    for option in options:
        require(bool(option.id.strip() and option.target.strip() and option.values), "incomplete edit option")
        properties(option.values)
    require(type(max_options) is int and max_options >= 0, "invalid option budget")
    require(callable(control) and callable(build) and callable(evaluate), "invalid construction callbacks")
    scope = select_scope(check_plan)
    steps = []

    def finish(status, reason, proposal=None):
        return ConstructionRun(task_ref, base, construction_plan, tuple(steps), status, proposal, reason)

    for option in options:
        if len(steps) >= max_options:
            return finish("budget_exhausted", "option_budget_exhausted")
        decision = checked(control(option), ConstructionDecision)
        require(decision.option_hash == digest(option), "control option binding mismatch", "conflict")
        require(bool(decision.reason.strip()), "missing construction decision reason")
        if decision.status != "allow":
            steps.append(ConstructionStep(option, decision, None, None))
            if decision.status in ("unknown", "error"):
                return finish(decision.status, "control_" + decision.status)
            continue
        proposal = checked(build(option), ChangeProposal)
        require(bool(proposal.proposal_id.strip() and proposal.operations), "empty construction proposal")
        require(digest(proposal.base) == digest(base), "proposal base mismatch", "conflict")
        validate_evidence_refs(proposal.intent_refs)
        evaluation = checked(evaluate(proposal), CandidateEvaluation)
        candidate = evaluation.candidate
        require(ref(candidate) == replace(base, revision=base.revision + 1, content_hash=digest(candidate)),
                "candidate identity/revision mismatch", "conflict")
        report = validate_report(evaluation.report, candidate, check_plan, scope)
        steps.append(ConstructionStep(option, decision, proposal, evaluation))
        statuses = {outcome.status for outcome in report.outcomes}
        if "error" in statuses:
            return finish("error", "terminal_error")
        if "unknown" in statuses or "not_applicable" in statuses:
            return finish("unknown", "terminal_unknown" if "unknown" in statuses else "terminal_not_applicable")
        if report.satisfied:
            return finish("candidate_found", "all_terminal_obligations_satisfied", proposal)
    return finish("exhausted", "option_space_exhausted")
