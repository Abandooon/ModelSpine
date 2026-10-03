"""Finite review action envelope; no candidate interpretation or persistence."""
import base64
import binascii
from dataclasses import dataclass
from typing import Literal

from modelspine_protocols import ArtifactRef, ContractError, checked, dumps, require, validate_artifact_ref
from modelspine_protocols.domain_language import ProjectModel


REVIEW_VERSION = "model-review/0.1"
WHOLE_CANDIDATE = "review:candidate"  # ':' is forbidden in finite definition IDs.
MAX_PROPOSAL_BYTES = 256 * 1024


@dataclass(frozen=True)
class ReviewAction:
    schema_version: Literal["model-review/0.1"]
    id: str
    project_id: str
    request_ref: ArtifactRef
    candidate_ref: ArtifactRef
    expected_review_ref: ArtifactRef
    question_ref: ArtifactRef | None
    actor: str
    kind: Literal["answer", "decline", "confirm", "propose_edit"]
    text: str
    targets: tuple[str, ...]
    proposal_base64: str | None


@dataclass(frozen=True)
class ProjectSubmission:
    schema_version: Literal["model-review-project/0.1"]
    id: str
    project_id: str
    request_ref: ArtifactRef
    candidate_ref: ArtifactRef
    expected_review_ref: ArtifactRef
    actor: str
    purpose: Literal["example", "counterexample", "project"]
    project: ProjectModel


@dataclass(frozen=True)
class ProposalAdoption:
    schema_version: Literal["model-review-adoption/0.1"]
    id: str
    project_id: str
    request_ref: ArtifactRef
    candidate_ref: ArtifactRef
    expected_review_ref: ArtifactRef
    actor: str
    proposal_ref: ArtifactRef
    text: str


@dataclass(frozen=True)
class ExternalClarification:
    """Host-attributed question/correction/response, not a candidate issue answer."""
    schema_version: Literal["model-review-clarification/0.1"]
    id: str
    project_id: str
    request_ref: ArtifactRef
    candidate_ref: ArtifactRef
    expected_review_ref: ArtifactRef
    question_text: str
    question_actor: str
    correction_text: str
    correction_actor: str
    response_kind: Literal["answer", "decline"]
    response_text: str
    actor: str
    interpretation_text: str
    interpretation_actor: str


@dataclass(frozen=True)
class RevisionProposal:
    schema_version: Literal["model-review-revision-proposal/0.1"]
    id: str
    project_id: str
    request_ref: ArtifactRef
    candidate_ref: ArtifactRef
    expected_review_ref: ArtifactRef
    actor: str
    action_refs: tuple[ArtifactRef, ...]
    revision_ref: ArtifactRef
    response_ref: ArtifactRef
    proposal_base64: str
    method_instructions: str


def validate_operation(value):
    if isinstance(value, ReviewAction):
        return validate_action(value)
    require(type(value) in (ProjectSubmission, ProposalAdoption, ExternalClarification, RevisionProposal), "unknown review operation")
    value = checked(value, type(value))
    require(all(s.strip() for s in (value.id, value.project_id, value.actor)), "empty operation identity/actor")
    refs = (value.request_ref, value.candidate_ref, value.expected_review_ref)
    if isinstance(value, ProjectSubmission): refs += (value.project.definition,)
    if isinstance(value, ProposalAdoption): refs += (value.proposal_ref,)
    if isinstance(value, RevisionProposal):
        refs += (value.revision_ref, value.response_ref, *value.action_refs)
        require(0 < len(value.action_refs) <= 64, "revision action count")
        proposal_bytes(value.proposal_base64)
        require(value.method_instructions.startswith("typed-domain-revision-proposal/")
                and len(value.method_instructions.encode("utf-8")) <= 64 * 1024,
                "missing/oversized frozen revision method")
    if isinstance(value, ExternalClarification):
        require(bool(value.question_text.strip()) and bool(value.question_actor.strip()), "external question required")
        require(value.response_kind == "decline" or bool(value.response_text.strip()), "empty external answer")
        require(not value.correction_text or bool(value.correction_actor.strip()), "correction owner required")
        require(not value.interpretation_text or bool(value.interpretation_actor.strip()), "interpretation owner required")
        require(all(len(s) <= 64 * 1024 for s in (value.question_text, value.correction_text, value.response_text,
                                                value.interpretation_text)), "clarification text limit", "unsupported")
    for ref in refs:
        validate_artifact_ref(ref)
        require(ref.project_id == value.project_id, "cross-project operation reference", "conflict")
    if isinstance(value, ProposalAdoption):
        require(bool(value.text.strip()) and len(value.text) <= 64 * 1024, "adoption reason required/too long")
    try:
        raw = dumps(value).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ContractError("invalid", "operation is not UTF-8 representable") from exc
    require(len(raw) <= 512 * 1024, "operation byte limit", "unsupported")
    return value


def proposal_bytes(encoded: str) -> bytes:
    require(type(encoded) is str and len(encoded) <= 4 * ((MAX_PROPOSAL_BYTES + 2) // 3),
            "proposal byte limit", "unsupported")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ContractError("invalid", "invalid proposal base64") from exc
    require(base64.b64encode(raw).decode("ascii") == encoded, "noncanonical base64")
    require(len(raw) <= MAX_PROPOSAL_BYTES, "proposal byte limit", "unsupported")
    return raw


def validate_action(value: ReviewAction) -> ReviewAction:
    value = checked(value, ReviewAction)
    require(all(s.strip() for s in (value.id, value.project_id, value.actor)), "empty action identity/actor")
    for ref in (value.request_ref, value.candidate_ref, value.expected_review_ref, value.question_ref):
        if ref is not None:
            validate_artifact_ref(ref)
            require(ref.project_id == value.project_id, "cross-project action reference", "conflict")
    require(len(set(value.targets)) == len(value.targets) and all(t.strip() for t in value.targets),
            "duplicate/empty target")
    require(len(value.targets) <= 256 and len(value.text) <= 64 * 1024, "action size limit", "unsupported")
    if value.kind in ("answer", "decline"):
        require(value.question_ref is not None and not value.targets and value.proposal_base64 is None,
                "answer/decline requires only question and text")
        require(value.kind == "decline" or bool(value.text.strip()), "empty answer")
    elif value.kind == "confirm":
        require(bool(value.targets) and value.question_ref is None and value.proposal_base64 is None,
                "confirm requires targets only")
    else:
        require(value.question_ref is None and not value.targets and value.proposal_base64 is not None,
                "propose_edit requires a complete candidate proposal")
        require(bool(value.text.strip()), "edit reason required")
        proposal_bytes(value.proposal_base64)
    try:
        raw = dumps(value).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ContractError("invalid", "action text is not UTF-8 representable") from exc
    require(len(raw) <= 512 * 1024, "action envelope byte limit", "unsupported")
    return value
