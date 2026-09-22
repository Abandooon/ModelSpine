"""Pure, explicitly sourced task preparation and fixed-plan assessment.

PreparedTask is a trusted in-process assembly value, not a security token.
Source integrity and explicit mappings do not establish semantic fidelity.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import re

from modelspine_protocols import (
    ArtifactRef, Checker, ContractError, Snapshot, TaskAssessment, TaskContract,
    checked, digest, loads, ref, require, select_scope, validate_artifact_ref,
    validate_evidence_refs, validate_plan, validate_report, validate_snapshot_ref,
)


@dataclass(frozen=True)
class PreparedTask:
    contract: TaskContract
    task_ref: ArtifactRef
    plan_hash: str | None
    mapped_statements: tuple[str, ...]
    unresolved: tuple[str, ...]


def _text(raw: bytes, label: str) -> str:
    require(type(raw) is bytes, f"{label}: expected raw bytes")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("invalid", f"{label}: expected UTF-8") from exc


def prepare_task(contract_bytes: bytes, expected_task_ref: ArtifactRef,
                 source_contents: Mapping[ArtifactRef, bytes]) -> PreparedTask:
    """The caller pins expected_task_ref before producing a candidate."""
    expected_task_ref = validate_artifact_ref(expected_task_ref)
    text = _text(contract_bytes, "task")
    require(sha256(contract_bytes).hexdigest() == expected_task_ref.content_hash,
            "task file hash mismatch", "conflict")
    contract = loads(TaskContract, text)
    validate_snapshot_ref(contract.base)
    require((contract.base.project_id, contract.id, contract.version) == (
        expected_task_ref.project_id, expected_task_ref.artifact_id, expected_task_ref.revision),
        "task identity/version mismatch", "conflict")
    require(isinstance(source_contents, Mapping), "expected explicit source mapping")
    statements = {statement.id: statement for statement in contract.statements}
    require(len(statements) == len(contract.statements), "duplicate task statement")
    for statement in contract.statements:
        require(bool(statement.id.strip() and statement.text.strip()), "empty task statement")
        require(statement.pending_reason is None or bool(statement.pending_reason.strip()),
                "empty pending reason")
        require(bool(statement.source_refs) or statement.pending_reason is not None,
                f"{statement.id}: missing source without pending reason")
        require(statement.confirmation == "confirmed" or statement.pending_reason is not None,
                f"{statement.id}: unresolved confirmation needs a reason")
        validate_evidence_refs(statement.source_refs)
        for evidence in statement.source_refs:
            require(evidence.source in source_contents, f"{statement.id}: declared source missing", "not_found")
            raw = source_contents[evidence.source]
            source_text = _text(raw, "source")
            require(sha256(raw).hexdigest() == evidence.source.content_hash,
                    f"{statement.id}: source hash mismatch", "conflict")
            position = re.fullmatch(r"lines:([1-9][0-9]*)-([1-9][0-9]*)", evidence.locator)
            require(position is not None, f"{statement.id}: unsupported source locator")
            start, end = map(int, position.groups())
            require(start <= end <= len(source_text.splitlines()),
                    f"{statement.id}: source locator out of bounds")

    obligations = {} if contract.plan is None else {
        item.id: item for item in validate_plan(contract.plan).obligations}
    bindings = {binding.obligation_id: binding for binding in contract.bindings}
    require(len(bindings) == len(contract.bindings), "duplicate task binding")
    require(set(bindings) == set(obligations), "task bindings must cover exactly the plan obligations")
    mapped = set()
    for key, binding in bindings.items():
        require(binding.obligation_version == obligations[key].version,
                "task obligation version mismatch", "conflict")
        require(bool(binding.statement_ids) and len(set(binding.statement_ids)) == len(binding.statement_ids),
                "empty or duplicate statement mapping")
        require(set(binding.statement_ids) <= statements.keys(), "mapping references missing statement")
        mapped.update(binding.statement_ids)

    unresolved = []
    required = [statement for statement in contract.statements if statement.required]
    if not required:
        unresolved.append("task has no declared required intent")
    for statement in required:
        reasons = []
        if statement.category != "intent":
            reasons.append("required goal is not an intent")
        if statement.confirmation != "confirmed":
            reasons.append(f"confirmation is {statement.confirmation}")
        if not statement.source_refs:
            reasons.append("source pending")
        if statement.id not in mapped:
            reasons.append("no mapped obligation")
        if statement.pending_reason is not None:
            reasons.append(statement.pending_reason)
        if reasons:
            unresolved.append(f"{statement.id}: " + "; ".join(reasons))
    if contract.plan is None:
        unresolved.append("no executable check plan")
    return PreparedTask(contract, expected_task_ref,
                        None if contract.plan is None else digest(contract.plan),
                        tuple(sorted(mapped)), tuple(unresolved))


def assess_task(prepared_task: PreparedTask, snapshot: Snapshot | None,
                checker: Checker) -> TaskAssessment:
    require(type(prepared_task) is PreparedTask, "expected prepared task")
    task = prepared_task.contract
    intent_status = "unresolved" if prepared_task.unresolved else "ready"
    if task.plan is None:
        require(snapshot is None, "no-plan assessment must not invent a candidate")
        require(prepared_task.plan_hash is None, "no-plan task has a plan hash", "conflict")
        return TaskAssessment("task-assessment/0.1", prepared_task.task_ref, None, None,
                              intent_status, "not_checked", prepared_task.mapped_statements,
                              prepared_task.unresolved)
    require(digest(task.plan) == prepared_task.plan_hash, "prepared plan changed", "conflict")
    snapshot = checked(snapshot, Snapshot)
    candidate = validate_snapshot_ref(ref(snapshot))
    require((candidate.project_id, candidate.model_id, candidate.metamodel, candidate.metamodel_hash) == (
        task.base.project_id, task.base.model_id, task.base.metamodel, task.base.metamodel_hash),
        "task candidate model/metamodel mismatch", "conflict")
    require(candidate.revision >= task.base.revision, "task candidate predates base", "conflict")
    if candidate.revision == task.base.revision:
        require(candidate == task.base, "task base revision content changed", "conflict")
    scope = select_scope(task.plan)
    require(callable(checker), "checker must be callable")
    report = validate_report(checker(snapshot, task.plan, scope), snapshot, task.plan, scope)
    statuses = {outcome.status for outcome in report.outcomes}
    goal_status = ("satisfied" if report.satisfied else "error" if "error" in statuses
                   else "violated" if "violated" in statuses else "unknown")
    return TaskAssessment("task-assessment/0.1", prepared_task.task_ref, candidate, report,
                          intent_status, goal_status, prepared_task.mapped_statements,
                          prepared_task.unresolved)
