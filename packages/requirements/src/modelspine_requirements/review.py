"""Pure finite review transitions. Actions record intent, never synthesize candidates."""
import base64
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Literal

from modelspine_protocols import ArtifactRef, ContractError, checked, decode, digest, dumps, require, to_data
from modelspine_protocols.domain_language import DomainDefinition, definition_ids
from modelspine_protocols.finite_execution import decode_definition
from modelspine_protocols.review import (
    MAX_PROPOSAL_BYTES, REVIEW_VERSION, WHOLE_CANDIDATE, ReviewAction, proposal_bytes, validate_action,
    ProjectSubmission, ProposalAdoption, validate_operation,
    ExternalClarification, RevisionProposal,
)
from modelspine_requirements.domain_modeling import ModelingRequest, validate_request
from modelspine_requirements.typed_domain import inspect_typed_candidate


MAX_ACTIONS = 64


@dataclass(frozen=True)
class ReviewSession:
    schema_version: Literal["model-review/0.1"]
    id: str
    request: ModelingRequest
    candidate_base64: str
    actions: tuple[ReviewAction | ProjectSubmission | ProposalAdoption | ExternalClarification | RevisionProposal, ...]


def _ref(session, name, revision, content_hash):
    return ArtifactRef(session.request.source.project_id, session.id + "/" + name, str(revision), content_hash)


def review_ref(session: ReviewSession) -> ArtifactRef:
    return _ref(session, "review", len(session.actions), digest(session))


def create_session(request: ModelingRequest, raw: bytes, *, session_id: str) -> ReviewSession:
    request = validate_request(request)
    require(type(session_id) is str and bool(session_id.strip()) and len(session_id) <= 256,
            "invalid session ID")
    require(type(raw) is bytes, "candidate must be original bytes")
    require(len(raw) <= MAX_PROPOSAL_BYTES, "candidate byte limit", "unsupported")
    encoded = base64.b64encode(raw).decode("ascii")
    proposal_bytes(encoded)
    session = ReviewSession(REVIEW_VERSION, session_id, request, encoded, ())
    try:
        dumps(session).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ContractError("invalid", "session ID is not UTF-8 representable") from exc
    return session


def _inspection(request, raw, context=None):
    try:
        if context is None:
            result = inspect_typed_candidate(request, raw)
        else:
            from modelspine_requirements.typed_revision import inspect_revision_candidate
            result = inspect_revision_candidate(request, raw, context)
    except ValueError as exc:
        # ContractError is a ValueError; JSON's integer digit limit also raises
        # ValueError before the typed decoder. Both are rejected input, not unknown.
        return {"status": "rejected", "diagnostics": [{"code": exc.code if isinstance(exc, ContractError) else "invalid",
                                                         "message": str(exc)}],
                "requirement_fidelity": "not_checked", "instance_conformance": "not_run"}, None
    return {"status": "valid", "diagnostics": [], "checks": to_data(result),
            "requirement_fidelity": "not_checked", "instance_conformance": "not_run"}, result.candidate


def _initial_view(session, candidate_revision=1, context=None):
    raw = proposal_bytes(session.candidate_base64)
    inspection, candidate = _inspection(session.request, raw, context)
    request_ref = _ref(session, "request", 1, digest(session.request))
    candidate_ref = _ref(session, "candidate", candidate_revision, sha256(raw).hexdigest())
    questions = []
    issues = to_data(candidate.issues) if candidate else []
    for issue in issues:
        if issue["question"] is not None:
            body = {"candidate_ref": to_data(candidate_ref), "source_ref": to_data(session.request.source),
                    "issue_id": issue["id"], "text": issue["question"]}
            questions.append({"id": issue["id"], "text": issue["question"], "kind": "candidate_issue",
                              "ref": to_data(_ref(session, "question/" + digest(body), 1, digest(body))),
                              "status": "open", "resolution": "unresolved"})
    if candidate is None:
        body = {"candidate_ref": to_data(candidate_ref), "source_ref": to_data(session.request.source),
                "diagnostics": inspection["diagnostics"]}
        questions.append({"id": "invalid-candidate", "text": "请说明候选的修正意图；原件未通过检查。",
                          "kind": "inspection_diagnostic",
                          "ref": to_data(_ref(session, "question/" + digest(body), 1, digest(body))),
                          "status": "open", "resolution": "unresolved"})
    definition = to_data(candidate.definition) if candidate else None
    return {"schema_version": REVIEW_VERSION, "project_id": session.request.source.project_id,
            "session_id": session.id, "request_ref": to_data(request_ref),
            "source_ref": to_data(session.request.source), "source_text": session.request.text,
            "candidate_ref": to_data(candidate_ref), "candidate_base64": session.candidate_base64,
            "candidate_text": raw.decode("utf-8", errors="replace"),
            "text_rendering": "utf8_replacement_for_display_only",
            "definition_ref": (to_data(ArtifactRef(session.request.source.project_id, candidate.definition.id,
                               candidate.definition.version, digest(candidate.definition))) if candidate else None),
            "inspection": inspection, "terms": definition["entities"] if definition else [],
            "relations": definition["relations"] if definition else [],
            "rules": definition["constraints"] if definition else [],
            "residuals": definition["residuals"] if definition else [],
            "issues": issues, "traces": to_data(candidate.traces) if candidate else [],
            "questions": questions, "actions": [], "proposals": [], "confirmations": [],
            "revision_status": "not_run", "next_candidate_ref": None,
            "requirement_fidelity": "not_checked", "instance_conformance": "not_run",
            "capability_version": "model-review-local/0.3", "projects": [], "history": [],
            "revision_context": context,
            "parent_candidate_ref": None}


def _check_binding(view, action, expected):
    require(action.project_id == view["project_id"] and to_data(action.request_ref) == view["request_ref"]
            and to_data(action.candidate_ref) == view["candidate_ref"] and action.expected_review_ref == expected,
            "stale or mismatched review/request/candidate binding", "conflict")
    if not isinstance(action, ReviewAction):
        return
    if action.kind in ("answer", "decline"):
        require(any(q["ref"] == to_data(action.question_ref) for q in view["questions"]),
                "question does not belong to this candidate/source", "conflict")
    if action.kind == "confirm":
        ids = {WHOLE_CANDIDATE}
        checks = view["inspection"].get("checks")
        if checks:
            ids.update(definition_ids(decode_definition(checks["candidate"]["definition"])))
        require(set(action.targets) <= ids, "unknown confirmation target")


def _record(view, session, action):
    action_ref = _ref(session, "action/" + action.id, 1, digest(action))
    source = {"kind": "user_action", "actor": action.actor, "text": action.text,
              "action_ref": to_data(action_ref), "source_ref": view["source_ref"],
              "based_on_candidate_ref": view["candidate_ref"], "asserts_original_source": False}
    view["actions"].append({"action": to_data(action), "provenance": source})
    if action.kind in ("answer", "decline"):
        for question in view["questions"]:
            if question["ref"] == to_data(action.question_ref):
                question["status"] = "answer_recorded" if action.kind == "answer" else "declined"
                question["last_action_ref"] = to_data(action_ref)
        view["revision_status"] = "pending"
    elif action.kind == "confirm":
        view["confirmations"].append({"targets": list(action.targets), "provenance": source})
    else:
        raw = proposal_bytes(action.proposal_base64)
        inspection, _ = _inspection(session.request, raw)
        view["proposals"].append({"ref": to_data(_ref(session, "proposal/" + action.id, 1, sha256(raw).hexdigest())),
                                  "raw_base64": action.proposal_base64, "inspection": inspection,
                                  "text": raw.decode("utf-8", errors="replace"),
                                  "provenance": source, "adoption": "pending", "original_traces": "attribution_only",
                                  "based_on_review_ref": to_data(action.expected_review_ref)})
        view["revision_status"] = "pending"


def _transition(view, session, operation):
    if isinstance(operation, ReviewAction):
        _record(view, session, operation)
    elif isinstance(operation, ExternalClarification):
        body = {"candidate_ref": view["candidate_ref"], "source_ref": view["source_ref"],
                "question_text": operation.question_text, "correction_text": operation.correction_text,
                "operation_id": operation.id}
        question_ref = to_data(_ref(session, "external-question/" + digest(body), 1, digest(body)))
        action_ref = to_data(_ref(session, "action/" + operation.id, 1, digest(operation)))
        provenance = {"kind": "external_clarification", "actor": operation.actor, "action_ref": action_ref,
                      "source_ref": view["source_ref"], "based_on_candidate_ref": view["candidate_ref"],
                      "asserts_original_source": False, "authentication": "host_attributed_not_authenticated"}
        view["actions"].append({"action": to_data(operation), "question_ref": question_ref, "provenance": provenance})
        view["questions"].append({"id": operation.id, "text": operation.question_text, "correction": operation.correction_text,
                                  "kind": "external_clarification", "ref": question_ref,
                                  "status": "answer_recorded" if operation.response_kind == "answer" else "declined",
                                  "resolution": "unresolved", "last_action_ref": action_ref})
        view["revision_status"] = "pending"
    elif isinstance(operation, RevisionProposal):
        from modelspine_requirements.revision_request import execution_context
        # Persistent history binds the actual proposal-time method bytes, not
        # whichever prompt happens to be installed when the project is reopened.
        context = execution_context(session.request, view, operation.action_refs,
                                    method_instructions=operation.method_instructions)
        require(to_data(operation.revision_ref) == context["ref"], "wrong revision context binding", "conflict")
        raw = proposal_bytes(operation.proposal_base64)
        inspection, _ = _inspection(session.request, raw, context)
        provenance = {"kind": "generated_revision_proposal", "actor": operation.actor,
                      "action_ref": to_data(_ref(session, "action/" + operation.id, 1, digest(operation))),
                      "response_ref": to_data(operation.response_ref), "generation_provenance": "not_verified",
                      "based_on_candidate_ref": view["candidate_ref"], "asserts_original_source": False}
        view["actions"].append({"action": to_data(operation), "provenance": provenance})
        view["proposals"].append({"ref": to_data(_ref(session, "proposal/" + operation.id, 1, sha256(raw).hexdigest())),
                                  "raw_base64": operation.proposal_base64, "inspection": inspection,
                                  "text": raw.decode("utf-8", errors="replace"), "provenance": provenance,
                                  "adoption": "pending", "revision_context": context,
                                  "based_on_review_ref": to_data(operation.expected_review_ref)})
        view["revision_status"] = "pending"
    elif isinstance(operation, ProjectSubmission):
        require(view["inspection"]["status"] == "valid", "invalid candidate cannot accept executable instances")
        require(to_data(operation.project.definition) == view["definition_ref"], "wrong project definition", "conflict")
        require(len(operation.project.objects) <= 256 and len(operation.project.links) <= 4096,
                "project size limit", "unsupported")
        view["projects"].append({"ref": to_data(_ref(session, "project/" + operation.id, 1, digest(operation.project))),
                                "project": to_data(operation.project), "purpose": operation.purpose,
                                "actor": operation.actor, "request_ref": view["request_ref"],
                                "candidate_ref": view["candidate_ref"], "definition_ref": view["definition_ref"],
                                "based_on_review_ref": to_data(operation.expected_review_ref)})
    else:
        proposal = next((p for p in view["proposals"] if p["ref"] == to_data(operation.proposal_ref)), None)
        require(proposal is not None, "proposal is not saved under current candidate", "conflict")
        raw = proposal_bytes(proposal["raw_base64"])
        context = proposal.get("revision_context")
        inspection, _ = _inspection(session.request, raw, context)
        require(inspection["status"] == "valid", "cannot adopt rejected proposal")
        parent = {k: v for k, v in view.items() if k != "history"}
        successor = _initial_view(create_session(session.request, raw, session_id=session.id),
                                  int(view["candidate_ref"]["revision"]) + 1, context=context)
        successor["parent_candidate_ref"] = view["candidate_ref"]
        successor["history"] = view["history"] + [{"view": parent, "adoption": to_data(operation)}]
        view = successor
    return view


def review_input(session: ReviewSession) -> dict:
    """Replay and verify the entire chain; returned view is detached from session."""
    session = checked(session, ReviewSession)
    base = create_session(session.request, proposal_bytes(session.candidate_base64), session_id=session.id)
    require(len(session.actions) <= MAX_ACTIONS, "review action limit", "unsupported")
    view = _initial_view(base)
    view["review_ref"] = to_data(review_ref(base))
    seen = set()
    for action in session.actions:
        action = validate_operation(action)
        require(action.id not in seen, "duplicate action in stored chain", "conflict")
        _check_binding(view, action, review_ref(base))
        view = _transition(view, base, action)
        base = replace(base, actions=base.actions + (action,))
        view["review_ref"] = to_data(review_ref(base))
        seen.add(action.id)
    view["review_ref"] = to_data(review_ref(base))
    return view


def _receipt(session, recorded, action, status):
    view = review_input(session)
    recorded_view = review_input(recorded)
    result = {"status": status, "action_ref": to_data(_ref(session, "action/" + action.id, 1, digest(action))),
              "review_ref": view["review_ref"], "recorded_review_ref": recorded_view["review_ref"],
              "next_candidate_ref": recorded_view["candidate_ref"] if isinstance(action, ProposalAdoption) else None,
              "revision_status": view["revision_status"]}
    if isinstance(action, ProjectSubmission):
        result["project_ref"] = recorded_view["projects"][-1]["ref"]
    return result


def apply_action(session: ReviewSession, action: ReviewAction | ProjectSubmission | ProposalAdoption) -> tuple[ReviewSession, dict]:
    view = review_input(session)
    action = validate_operation(action)
    for index, old in enumerate(session.actions):
        if old.id == action.id:
            require(old == action, "action ID reused with different content", "conflict")
            recorded = replace(session, actions=session.actions[:index + 1])
            return session, _receipt(session, recorded, action, "already_recorded")
    require(len(session.actions) < MAX_ACTIONS, "review action limit", "unsupported")
    _check_binding(view, action, review_ref(session))
    _transition(view, session, action)
    successor = replace(session, actions=session.actions + (action,))
    return successor, _receipt(successor, successor, action, "recorded")
