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


def validate_operation(value):
    if isinstance(value, ReviewAction):
        return validate_action(value)
    require(type(value) in (ProjectSubmission, ProposalAdoption), "unknown review operation")
    value = checked(value, type(value))
    require(all(s.strip() for s in (value.id, value.project_id, value.actor)), "empty operation identity/actor")
    refs = (value.request_ref, value.candidate_ref, value.expected_review_ref,
            value.project.definition if isinstance(value, ProjectSubmission) else value.proposal_ref)
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
