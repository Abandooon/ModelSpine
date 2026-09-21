"""Shared v0.1 values and strict, canonical JSON. Standard library only."""
from __future__ import annotations

import hashlib
import json
import types
from dataclasses import dataclass, fields, is_dataclass
from typing import Literal, Protocol, Union, get_args, get_origin, get_type_hints


class ContractError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def require(condition: bool, message: str, code: str = "invalid") -> None:
    if not condition:
        raise ContractError(code, message)


Scalar = str | int | bool


@dataclass(frozen=True)
class MetamodelRef:
    id: str
    version: str


@dataclass(frozen=True)
class ArtifactRef:
    project_id: str
    artifact_id: str
    revision: str
    content_hash: str


@dataclass(frozen=True)
class EvidenceRef:
    source: ArtifactRef
    locator: str
    origin: str


@dataclass(frozen=True)
class Property:
    name: str
    value: Scalar


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: Literal["integer", "string", "boolean"]


@dataclass(frozen=True)
class KindSpec:
    name: str
    fields: tuple[FieldSpec, ...]


@dataclass(frozen=True)
class Metamodel:
    ref: MetamodelRef
    kinds: tuple[KindSpec, ...]


@dataclass(frozen=True)
class Element:
    id: str
    kind: str
    name: str
    parent: str | None
    properties: tuple[Property, ...]
    dependencies: tuple[str, ...]
    dependencies_complete: bool
    category: Literal["intent", "fact", "hypothesis"]
    confirmed: bool
    sources: tuple[EvidenceRef, ...]


@dataclass(frozen=True)
class Snapshot:
    project_id: str
    model_id: str
    revision: int
    metamodel: MetamodelRef
    metamodel_hash: str
    elements: tuple[Element, ...]


@dataclass(frozen=True)
class SnapshotRef:
    project_id: str
    model_id: str
    revision: int
    metamodel: MetamodelRef
    metamodel_hash: str
    content_hash: str


@dataclass(frozen=True)
class ElementRef:
    snapshot: SnapshotRef
    element_id: str


@dataclass(frozen=True)
class Rename:
    op: Literal["rename"]
    target: str
    name: str


@dataclass(frozen=True)
class SetProperty:
    op: Literal["set_property"]
    target: str
    field: str
    value: Scalar


@dataclass(frozen=True)
class SetDependencies:
    op: Literal["set_dependencies"]
    target: str
    dependencies: tuple[str, ...]
    complete: bool


@dataclass(frozen=True)
class AddElement:
    op: Literal["add_element"]
    element: Element


@dataclass(frozen=True)
class RemoveElement:
    op: Literal["remove_element"]
    target: str


@dataclass(frozen=True)
class Confirm:
    op: Literal["confirm"]
    target: str
    confirmed: bool


Operation = Rename | SetProperty | SetDependencies | AddElement | RemoveElement | Confirm


@dataclass(frozen=True)
class ChangeProposal:
    api_version: Literal["0.1"]
    proposal_id: str
    base: SnapshotRef
    operations: tuple[Operation, ...]
    intent_refs: tuple[EvidenceRef, ...]


@dataclass(frozen=True)
class ImpactSet:
    changed: tuple[str, ...]
    affected: tuple[str, ...]
    unknown: tuple[str, ...]


@dataclass(frozen=True)
class Preview:
    proposal_hash: str
    candidate_hash: str
    candidate: Snapshot
    impact: ImpactSet


@dataclass(frozen=True)
class Obligation:
    id: str
    version: str
    kind: str
    target: str
    field: str
    parameters: tuple[Property, ...]


@dataclass(frozen=True)
class CheckPlan:
    id: str
    version: str
    rule_version: str
    assumptions: tuple[str, ...]
    obligations: tuple[Obligation, ...]


@dataclass(frozen=True)
class ReportBinding:
    candidate_hash: str
    plan_hash: str
    scope: tuple[str, ...]
    assumptions: tuple[str, ...]
    tool: str
    tool_version: str


@dataclass(frozen=True)
class Outcome:
    obligation_id: str
    obligation_version: str
    status: Literal["satisfied", "violated", "unknown", "not_applicable", "error"]
    findings: tuple[str, ...]


@dataclass(frozen=True)
class ValidationReport:
    binding: ReportBinding
    outcomes: tuple[Outcome, ...]

    @property
    def residual(self) -> tuple[str, ...]:
        return tuple(o.obligation_id for o in self.outcomes if o.status != "satisfied")

    @property
    def satisfied(self) -> bool:
        return bool(self.outcomes) and not self.residual


class Checker(Protocol):
    """Synchronous, deterministic checks without model writes; exceptions propagate.

    Implementations own checking semantics. Consumers validate report bindings and
    coverage; this protocol does not establish the checker's semantic correctness.
    Scope identifies checked objects, not an inferred read set. The injecting
    caller must declare all checker reads as model dependencies, or mark
    dependencies_complete=False when their completeness cannot be established.
    """

    def __call__(self, snapshot: Snapshot, plan: CheckPlan,
                 scope: tuple[str, ...] | None = None) -> ValidationReport: ...


@dataclass(frozen=True)
class Decision:
    token: str
    proposal_hash: str
    candidate_hash: str
    report_hash: str
    binding: ReportBinding
    actor: str
    policy: Literal["satisfied-save", "checked-save"]


@dataclass(frozen=True)
class DependencyFingerprint:
    element_id: str
    content_hash: str


@dataclass(frozen=True)
class EvidenceRecord:
    id: str
    snapshot: SnapshotRef
    report: ValidationReport
    dependencies: tuple[DependencyFingerprint, ...]
    complete: bool


@dataclass(frozen=True)
class Applicability:
    evidence_id: str
    status: Literal["current", "stale", "unknown"]
    reason: str


@dataclass(frozen=True)
class Commit:
    proposal_id: str
    snapshot: SnapshotRef
    report: ValidationReport
    policy: str
    impact: ImpactSet
    evidence_status: tuple[Applicability, ...]


@dataclass(frozen=True)
class GenerationControl:
    obligation_id: str
    obligation_version: str
    fragment: str
    stage: str
    mechanism: str
    remaining: str


@dataclass(frozen=True)
class GenerationPlan:
    check_plan_hash: str
    controls: tuple[GenerationControl, ...]
    residual: tuple[str, ...]


@dataclass(frozen=True)
class RepairComparison:
    status: Literal["rejected", "repair_progress"]
    reason: str
    remaining: tuple[str, ...]


@dataclass(frozen=True)
class RunReceipt:
    run_id: str
    input_hashes: tuple[str, ...]
    output_hashes: tuple[str, ...]
    tools: tuple[str, ...]
    elapsed_ms: int
    terminal_status: str


def to_data(value):
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_data(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, tuple):
        return [to_data(v) for v in value]
    if isinstance(value, dict):
        require(all(type(k) is str for k in value), "JSON keys must be strings")
        return {k: to_data(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_data(v) for v in value]
    require(value is None or type(value) in (str, int, bool), "unsupported JSON value")
    return value


def dumps(value) -> str:
    return json.dumps(to_data(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value) -> str:
    return hashlib.sha256(dumps(value).encode("utf-8")).hexdigest()


def decode(cls, value):
    """Strict at every nested field; also used at public in-process boundaries."""
    origin, args = get_origin(cls), get_args(cls)
    if origin in (Union, types.UnionType):
        for alternative in args:
            try:
                return decode(alternative, value)
            except ContractError:
                pass
        raise ContractError("invalid", f"value does not match {cls}: {value!r}")
    if origin is Literal:
        require(any(type(value) is type(a) and value == a for a in args), f"invalid literal: {value!r}")
        return value
    if origin is tuple:
        require(type(value) is list, "expected array")
        require(len(args) == 2 and args[1] is Ellipsis, "unsupported tuple schema")
        return tuple(decode(args[0], v) for v in value)
    if is_dataclass(cls):
        require(type(value) is dict, f"expected object for {cls.__name__}")
        hints = get_type_hints(cls)
        require(set(value) == set(hints), f"unexpected/missing fields for {cls.__name__}")
        return cls(**{k: decode(t, value[k]) for k, t in hints.items()})
    require(type(value) is cls, f"expected {cls}, got {type(value).__name__}")
    return value


def checked(value, cls):
    return decode(cls, to_data(value))


def loads(cls, text: str):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject(value):
        raise ContractError("invalid", f"non-integer JSON number: {value}")

    try:
        data = json.loads(text, object_pairs_hook=pairs, parse_float=reject, parse_constant=reject)
    except json.JSONDecodeError as exc:
        raise ContractError("invalid", f"invalid JSON: {exc.msg}") from exc
    return decode(cls, data)


def ref(snapshot: Snapshot) -> SnapshotRef:
    return SnapshotRef(snapshot.project_id, snapshot.model_id, snapshot.revision,
                       snapshot.metamodel, snapshot.metamodel_hash, digest(snapshot))


def properties(items: tuple[Property, ...]) -> dict[str, Scalar]:
    require(len({p.name for p in items}) == len(items), "duplicate property")
    require(all(p.name for p in items), "empty property name")
    return {p.name: p.value for p in items}


def validate_model(snapshot: Snapshot, metamodel: Metamodel) -> None:
    snapshot, metamodel = checked(snapshot, Snapshot), checked(metamodel, Metamodel)
    require(snapshot.metamodel == metamodel.ref and snapshot.metamodel_hash == digest(metamodel),
            "metamodel version/content mismatch", "conflict")
    require(bool(snapshot.project_id and snapshot.model_id) and snapshot.revision >= 0,
            "invalid model identity/revision")
    require(bool(metamodel.ref.id and metamodel.ref.version), "invalid metamodel identity")
    kinds = {k.name: k for k in metamodel.kinds}
    require(bool(kinds) and len(kinds) == len(metamodel.kinds), "duplicate/empty kinds")
    for kind in kinds.values():
        require(kind.name and len({f.name for f in kind.fields}) == len(kind.fields), "duplicate kind fields")
    elements = {e.id: e for e in snapshot.elements}
    require(len(elements) == len(snapshot.elements), "duplicate element ID")
    types_by_name = {"integer": int, "string": str, "boolean": bool}
    for element in snapshot.elements:
        require(bool(element.id and element.name), "empty identity/name")
        require(element.category != "fact" or bool(element.sources), "implementation fact needs provenance")
        for source in element.sources:
            require(bool(source.locator and source.origin and source.source.project_id
                         and source.source.artifact_id and source.source.revision), "incomplete source reference")
            require(len(source.source.content_hash) == 64
                    and all(c in "0123456789abcdef" for c in source.source.content_hash), "invalid source SHA-256")
        require(element.kind in kinds, f"unsupported kind {element.kind}", "unsupported")
        values = properties(element.properties)
        spec = {f.name: f.type for f in kinds[element.kind].fields}
        require(set(values) == set(spec), f"invalid fields for {element.id}")
        for key, value in values.items():
            require(type(value) is types_by_name[spec[key]], f"invalid type for {element.id}.{key}")
            if type(value) is int:
                require(-(2**63) <= value < 2**63, "integer outside signed 64-bit range")
        require(len(set(element.dependencies)) == len(element.dependencies), "duplicate dependency")
        require(all(d in elements for d in element.dependencies), "dangling semantic dependency")
        require(element.parent is None or element.parent in elements, "dangling parent")
        visited, current = set(), element
        while current.parent is not None:
            require(current.id not in visited, "containment cycle")
            visited.add(current.id)
            current = elements[current.parent]


def validate_plan(plan: CheckPlan) -> CheckPlan:
    plan = checked(plan, CheckPlan)
    require(bool(plan.id and plan.version and plan.rule_version and plan.obligations), "empty check plan")
    require(len({o.id for o in plan.obligations}) == len(plan.obligations), "duplicate obligation")
    for obligation in plan.obligations:
        require(bool(obligation.id and obligation.version and obligation.target and obligation.field), "empty obligation identity")
        properties(obligation.parameters)
    return plan
