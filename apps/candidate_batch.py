"""Pinned candidate payloads and host execution; no network or reference oracle."""
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Literal

from bounded_generation import BoundedTaskRun, _execute_construction, _prepare_construction
from dag_construction import DagEditSpace
from modelspine_generation.bounded import EditOption
from modelspine_protocols import (
    ArtifactRef, ContractError, EvidenceRef, Metamodel, Snapshot, TaskContract,
    checked, digest, dumps, loads, require,
)


@dataclass(frozen=True)
class CandidateLimits:
    max_catalog_options: int
    max_returned_options: int
    max_request_bytes: int
    max_response_bytes: int


@dataclass(frozen=True)
class SourceFragment:
    evidence: EvidenceRef
    text: str


@dataclass(frozen=True)
class CandidateRequest:
    schema_version: Literal["candidate-request/0.1"]
    request_id: str
    task_ref: ArtifactRef
    space_ref: ArtifactRef
    check_plan_hash: str
    catalog_hash: str
    task: TaskContract
    metamodel: Metamodel
    snapshot: Snapshot
    space: DagEditSpace
    source_fragments: tuple[SourceFragment, ...]
    options: tuple[EditOption, ...]
    limits: CandidateLimits


@dataclass(frozen=True)
class _SelectionPayload:
    schema_version: Literal["candidate-selection/0.1"]
    request_id: str
    option_ids: tuple[str, ...]


@dataclass(frozen=True)
class CandidateSelection:
    request_id: str
    request_hash: str
    response_hash: str
    response_text: str
    option_ids: tuple[str, ...]
    option_hashes: tuple[str, ...]


@dataclass(frozen=True)
class CandidateBatchRun:
    request_hash: str
    response_hash: str
    catalog_size: int
    returned_options: int
    max_considered_options: int
    exhaustion_scope: Literal["backend_batch"]
    app_result: BoundedTaskRun


def _limits(value):
    value = checked(value, CandidateLimits)
    require(value.max_catalog_options >= 0 and value.max_returned_options >= 0,
            "negative candidate limit")
    require(value.max_request_bytes > 0 and value.max_response_bytes > 0, "invalid payload byte limit")
    return value


def _utf8(raw, label):
    require(type(raw) is bytes, f"{label} requires original bytes")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("invalid", f"{label} requires UTF-8") from exc


def prepare_candidate_request(inputs, source_contents, *, request_id, limits):
    """Prepare unlabelled options and verified source excerpts before any request.

    Byte limits bound these host payloads, not provider token counts or charges.
    PreparedTask and this value are trusted local assembly, not credentials.
    """
    limits = _limits(limits)
    require(type(request_id) is str and bool(request_id.strip()), "missing request ID")
    space, constructor = _prepare_construction(inputs, max_catalog_options=limits.max_catalog_options)
    prepared, meta, snapshot, _, space_ref = inputs
    require(not prepared.unresolved, "candidate request requires resolved task intent", "conflict")
    require(isinstance(source_contents, Mapping), "expected explicit source contents")
    evidence = tuple(dict.fromkeys(e for statement in prepared.contract.statements for e in statement.source_refs))
    fragments = []
    for item in evidence:
        require(item.source in source_contents, "candidate source missing", "not_found")
        raw = source_contents[item.source]
        text = _utf8(raw, "source")
        require(sha256(raw).hexdigest() == item.source.content_hash, "candidate source hash mismatch", "conflict")
        position = re.fullmatch(r"lines:([1-9][0-9]*)-([1-9][0-9]*)", item.locator)
        require(position is not None, "unsupported source locator")
        start, end = map(int, position.groups())
        lines = text.splitlines()
        require(start <= end <= len(lines), "source locator out of bounds")
        fragments.append(SourceFragment(item, "\n".join(lines[start - 1:end])))
    request = CandidateRequest("candidate-request/0.1", request_id, prepared.task_ref, space_ref,
                               prepared.plan_hash, digest(constructor.options), prepared.contract, meta,
                               snapshot, space, tuple(fragments), constructor.options, limits)
    require(len(dumps(request).encode("utf-8")) <= limits.max_request_bytes,
            "candidate request exceeds byte limit", "unsupported")
    return request


def parse_candidate_selection(request, response_bytes):
    """Decode a complete payload; invalid members never yield partial execution."""
    request = checked(request, CandidateRequest)
    limits = _limits(request.limits)
    require(type(response_bytes) is bytes, "selection requires original bytes")
    require(len(response_bytes) <= limits.max_response_bytes, "candidate response exceeds byte limit", "unsupported")
    text = _utf8(response_bytes, "selection")
    payload = loads(_SelectionPayload, text)
    require(payload.request_id == request.request_id, "selection request ID mismatch", "conflict")
    require(len(payload.option_ids) <= limits.max_returned_options, "too many returned options")
    require(len(set(payload.option_ids)) == len(payload.option_ids), "duplicate returned option")
    catalog = {option.id: option for option in request.options}
    require(len(catalog) == len(request.options) and digest(request.options) == request.catalog_hash,
            "candidate catalog binding mismatch", "conflict")
    require(all(name in catalog for name in payload.option_ids), "returned option outside fixed catalog", "conflict")
    return CandidateSelection(request.request_id, digest(request), sha256(response_bytes).hexdigest(), text,
                              payload.option_ids, tuple(digest(catalog[name]) for name in payload.option_ids))


def run_candidate_selection(inputs, request, selection, *, controller=None, construction_plan=None):
    """Replay a pinned batch from these exact inputs, through complete acceptance."""
    request = checked(request, CandidateRequest)
    selection = checked(selection, CandidateSelection)
    limits = _limits(request.limits)
    space, constructor = _prepare_construction(inputs, max_catalog_options=limits.max_catalog_options)
    prepared, meta, snapshot, _, space_ref = inputs
    require((request.task_ref, request.task, request.metamodel, request.snapshot, request.space_ref,
             request.space, request.check_plan_hash, request.options, request.catalog_hash) ==
            (prepared.task_ref, prepared.contract, meta, snapshot, space_ref,
             space, prepared.plan_hash, constructor.options, digest(constructor.options)),
            "candidate request input/catalog binding mismatch", "conflict")
    require(len(dumps(request).encode("utf-8")) <= limits.max_request_bytes,
            "candidate request exceeds byte limit", "unsupported")
    expected = parse_candidate_selection(request, selection.response_text.encode("utf-8"))
    require(selection == expected, "candidate selection binding mismatch", "conflict")
    catalog = {option.id: option for option in constructor.options}
    options = tuple(catalog[name] for name in selection.option_ids)
    result = _execute_construction(inputs, space, constructor, options,
                                   controller=controller, construction_plan=construction_plan)
    return CandidateBatchRun(digest(request), selection.response_hash, len(constructor.options), len(options),
                             space.max_options, "backend_batch", result)
