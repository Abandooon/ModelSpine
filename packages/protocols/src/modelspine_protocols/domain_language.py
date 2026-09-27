"""Finite language values and static typing; no domain vocabulary or execution."""
from dataclasses import dataclass
from typing import Literal

from modelspine_protocols import ArtifactRef, Scalar, checked, dumps, require

PROFILE = "finite-domain/0.1"
MAX_ITEMS = 256
MAX_DEPTH = 24
MAX_NODES = 512
ScalarType = Literal["integer", "string", "boolean"]


@dataclass(frozen=True)
class Field:
    id: str
    name: str
    value_type: ScalarType
    required: bool
    nullable: bool


@dataclass(frozen=True)
class EntityType:
    id: str
    name: str
    fields: tuple[Field, ...]


@dataclass(frozen=True)
class Bounds:
    minimum: int
    maximum: int | Literal["unbounded"]


@dataclass(frozen=True)
class BinaryRelation:
    id: str
    name: str
    source: str
    target: str
    targets_per_source: Bounds
    sources_per_target: Bounds


@dataclass(frozen=True)
class Expression:
    op: Literal["literal", "field", "count", "eq", "lt", "le", "and", "or", "not", "implies", "is_null"]
    args: tuple["Expression", ...]
    symbol: str | None
    value: Scalar | None


@dataclass(frozen=True)
class Constraint:
    id: str
    context: str
    applies: Expression
    assertion: Expression
    unless: Expression


@dataclass(frozen=True)
class Residual:
    id: str
    family: str
    text: str
    required: bool


@dataclass(frozen=True)
class DomainDefinition:
    schema_version: Literal["finite-domain/0.1"]
    id: str
    version: str
    entities: tuple[EntityType, ...]
    relations: tuple[BinaryRelation, ...]
    constraints: tuple[Constraint, ...]
    residuals: tuple[Residual, ...]


@dataclass(frozen=True)
class Slot:
    field: str
    state: Literal["known", "null", "unknown"]
    value: Scalar | None


@dataclass(frozen=True)
class Instance:
    id: str
    entity: str
    slots: tuple[Slot, ...]


@dataclass(frozen=True)
class Link:
    relation: str
    source: str
    target: str


@dataclass(frozen=True)
class ProjectModel:
    schema_version: Literal["finite-project/0.1"]
    id: str
    version: str
    definition: ArtifactRef
    objects: tuple[Instance, ...]
    links: tuple[Link, ...]
    population_complete: bool


def text(value, label):
    require(type(value) is str and bool(value.strip()), f"empty {label}")


def _utf8(value):
    try:
        dumps(value).encode("utf-8")
    except UnicodeEncodeError:
        require(False, "payload is not UTF-8 encodable")


def scalar_type(value):
    return {int: "integer", str: "string", bool: "boolean"}.get(type(value))


def definition_ids(value):
    return tuple(x.id for x in (*value.entities,
                 *(f for e in value.entities for f in e.fields),
                 *value.relations, *value.constraints, *value.residuals))


def expression_type(expr, entity, relations, depth=0, budget=None):
    """Return (type, nullable); enforce bounded trees before evaluation."""
    budget = [MAX_NODES] if budget is None else budget
    budget[0] -= 1
    require(depth <= MAX_DEPTH and budget[0] >= 0, "expression budget exceeded", "unsupported")
    op = expr.op
    arity = {"literal": 0, "field": 0, "count": 0, "is_null": 1, "not": 1,
             "eq": 2, "lt": 2, "le": 2, "and": 2, "or": 2, "implies": 2}
    require(op in arity and len(expr.args) == arity[op], "invalid operator/arity")
    if op == "literal":
        require(expr.symbol is None and scalar_type(expr.value) is not None, "invalid literal")
        if type(expr.value) is int:
            require(-(2**63) <= expr.value < 2**63, "integer outside signed 64-bit range")
        return scalar_type(expr.value), False
    require(expr.value is None, "non-literal has a value")
    if op == "field":
        fields = {f.id: f for f in entity.fields}
        require(expr.symbol in fields, "field is outside constraint context")
        field = fields[expr.symbol]
        return field.value_type, field.nullable
    if op == "count":
        # Direction is explicit; self relations are not ambiguous.
        require(type(expr.symbol) is str and expr.symbol.endswith((":out", ":in")), "count needs relation:out/in")
        key, direction = expr.symbol.rsplit(":", 1)
        require(key in relations, "unknown count relation")
        relation = relations[key]
        require(entity.id == (relation.source if direction == "out" else relation.target),
                "count relation is outside context")
        return "integer", False
    require(expr.symbol is None, "operator has unexpected symbol")
    args = [expression_type(a, entity, relations, depth + 1, budget) for a in expr.args]
    if op == "is_null":
        return "boolean", False
    if op in ("eq", "lt", "le"):
        require(args[0][0] == args[1][0], "comparison type mismatch")
        require(op == "eq" or args[0][0] == "integer", "ordering requires integer")
    else:
        require(all(t == "boolean" and not nullable for t, nullable in args), "logic requires nonnullable booleans")
    return "boolean", False


def validate_definition(value: DomainDefinition) -> DomainDefinition:
    try:
        value = checked(value, DomainDefinition)
    except RecursionError:
        require(False, "definition nesting exceeds parser limit", "unsupported")
    _utf8(value)
    text(value.id, "definition ID")
    text(value.version, "definition version")
    ids = definition_ids(value)
    require(0 < len(ids) <= MAX_ITEMS and len(ids) == len(set(ids)), "empty/oversized/duplicate definition IDs")
    for key in ids:
        text(key, "element ID")
        require(":" not in key, "local IDs cannot contain colon")
    entities = {e.id: e for e in value.entities}
    relations = {r.id: r for r in value.relations}
    for entity in value.entities:
        text(entity.name, "entity name")
        require(len({f.name for f in entity.fields}) == len(entity.fields), "duplicate field name")
        for field in entity.fields:
            text(field.name, "field name")
    for relation in value.relations:
        text(relation.name, "relation name")
        require(relation.source in entities and relation.target in entities, "dangling relation endpoint")
        for bounds in (relation.targets_per_source, relation.sources_per_target):
            require(bounds.minimum >= 0, "negative cardinality")
            require(bounds.maximum == "unbounded" or bounds.maximum >= bounds.minimum, "inverted cardinality")
    for rule in value.constraints:
        require(rule.context in entities, "unknown constraint context")
        for expr in (rule.applies, rule.assertion, rule.unless):
            require(expression_type(expr, entities[rule.context], relations) == ("boolean", False),
                    "constraint predicate must be nonnullable boolean")
    for residual in value.residuals:
        text(residual.family, "residual family")
        text(residual.text, "residual source meaning")
    return value
