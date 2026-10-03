"""Versioned finite set/time language. v0.1 DTOs and semantics remain unchanged."""
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Literal

from modelspine_protocols import Scalar, checked, decode, require
from modelspine_protocols.domain_language import (
    BinaryRelation, DomainDefinition as LegacyDefinition, Residual,
    MAX_DEPTH, MAX_ITEMS, MAX_NODES, _utf8, definition_ids, scalar_type, text,
)

PROFILE = "finite-domain/0.2"


@dataclass(frozen=True)
class Field:
    id: str
    name: str
    value_type: Literal["integer", "string", "boolean", "instant"]
    required: bool
    nullable: bool


@dataclass(frozen=True)
class EntityType:
    id: str
    name: str
    fields: tuple[Field, ...]


@dataclass(frozen=True)
class Expression:
    op: Literal["literal", "instant", "duration", "self", "var", "get", "navigate",
                "filter", "count", "eq", "lt", "le", "and", "or", "implies",
                "not", "is_null", "add", "sub"]
    args: tuple["Expression", ...]
    symbol: str | None
    value: Scalar | None


@dataclass(frozen=True)
class Constraint:
    id: str
    context: str
    scope: Literal["invariant", "eligibility"]
    operation: str | None
    applies: Expression
    assertion: Expression
    unless: Expression


@dataclass(frozen=True)
class DomainDefinition:
    schema_version: Literal["finite-domain/0.2"]
    id: str
    version: str
    entities: tuple[EntityType, ...]
    relations: tuple[BinaryRelation, ...]
    constraints: tuple[Constraint, ...]
    residuals: tuple[Residual, ...]


def decode_definition(data):
    require(type(data) is dict, "definition must be an object")
    kind = data.get("schema_version")
    require(kind in ("finite-domain/0.1", PROFILE), "unsupported definition profile", "unsupported")
    try:
        return decode(LegacyDefinition if kind == "finite-domain/0.1" else DomainDefinition, data)
    except RecursionError:
        require(False, "definition nesting exceeds parser limit", "unsupported")


def instant(value):
    require(type(value) is str and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value),
            "instant requires whole UTC seconds YYYY-MM-DDTHH:MM:SSZ")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        require(False, "invalid Gregorian UTC instant")


def int64(value):
    require(type(value) is int and -(2**63) <= value < 2**63, "integer outside signed 64-bit range")
    return value


def expression_type(expr, context, entities, relations, env=None, depth=0, budget=None):
    env = {} if env is None else env
    budget = [MAX_NODES] if budget is None else budget
    budget[0] -= 1
    require(depth <= MAX_DEPTH and budget[0] >= 0, "expression budget exceeded", "unsupported")
    arity = {"literal": 0, "instant": 0, "duration": 0, "self": 0, "var": 0,
             "get": 1, "navigate": 1, "filter": 2, "count": 1, "is_null": 1, "not": 1,
             "eq": 2, "lt": 2, "le": 2, "and": 2, "or": 2, "implies": 2, "add": 2, "sub": 2}
    op = expr.op
    require(op in arity and len(expr.args) == arity[op], "invalid operator/arity")
    if op in ("literal", "instant", "duration"):
        require(expr.symbol is None, "literal has symbol")
        if op == "instant":
            instant(expr.value)
            return "instant", False
        if op == "duration":
            int64(expr.value)
            return "duration", False
        kind = scalar_type(expr.value)
        require(kind is not None, "invalid literal")
        if kind == "integer": int64(expr.value)
        return kind, False
    require(expr.value is None, "nonliteral has value")
    if op == "self":
        require(expr.symbol is None, "self has symbol")
        return "object:" + context, False
    if op == "var":
        require(expr.symbol in env, "unbound filter variable")
        return env[expr.symbol], False
    def infer(arg, bindings=env):
        return expression_type(arg, context, entities, relations, bindings, depth + 1, budget)
    if op in ("get", "navigate"):
        obj, nullable = infer(expr.args[0])
        require(obj.startswith("object:") and not nullable, "object operand required")
        entity_id = obj.split(":", 1)[1]
        if op == "get":
            fields = {f.id: f for f in entities[entity_id].fields}
            require(expr.symbol in fields, "field outside object type")
            field = fields[expr.symbol]
            return field.value_type, field.nullable
        require(type(expr.symbol) is str and expr.symbol.endswith((":out", ":in")), "navigate needs relation:out/in")
        key, direction = expr.symbol.rsplit(":", 1)
        require(key in relations, "unknown navigate relation")
        relation = relations[key]
        require(entity_id == (relation.source if direction == "out" else relation.target), "navigate endpoint mismatch")
        return "set:" + (relation.target if direction == "out" else relation.source), False
    if op == "filter":
        collection, nullable = infer(expr.args[0])
        require(collection.startswith("set:") and not nullable, "filter requires collection")
        text(expr.symbol, "filter variable")
        require(expr.symbol not in env, "filter variable shadowing is unsupported", "unsupported")
        require(infer(expr.args[1], {**env, expr.symbol: collection.replace("set:", "object:", 1)}) == ("boolean", False),
                "filter requires nonnullable Boolean predicate")
        return collection, False
    require(expr.symbol is None, "unexpected operator symbol")
    args = [infer(a) for a in expr.args]
    if op == "count":
        require(args[0][0].startswith("set:"), "count requires collection")
        return "integer", False
    if op == "is_null": return "boolean", False
    if op in ("eq", "lt", "le"):
        require(args[0][0] == args[1][0] and args[0][0] in ("integer", "string", "boolean", "instant", "duration"),
                "comparison requires same scalar type")
        require(op == "eq" or args[0][0] in ("integer", "instant", "duration"), "invalid ordered type")
    elif op in ("add", "sub"):
        kinds = tuple(a[0] for a in args)
        if kinds == ("instant", "duration"): return "instant", False
        if op == "sub" and kinds == ("instant", "instant"): return "duration", False
        require(kinds in (("integer", "integer"), ("duration", "duration")), "invalid arithmetic dimensions")
        return kinds[0], False
    else:
        require(all(a == ("boolean", False) for a in args), "logic requires nonnullable booleans")
    return "boolean", False


def validate_definition(value):
    try:
        value = checked(value, DomainDefinition)
    except RecursionError:
        require(False, "definition nesting exceeds parser limit", "unsupported")
    _utf8(value)
    text(value.id, "definition ID")
    text(value.version, "definition version")
    ids = definition_ids(value)
    require(len(ids) <= MAX_ITEMS, "definition resource limit", "unsupported")
    require(ids and len(ids) == len(set(ids)), "empty/duplicate definition IDs")
    for key in ids:
        text(key, "element ID")
        require(":" not in key, "local IDs cannot contain colon")
    entities = {e.id: e for e in value.entities}
    relations = {r.id: r for r in value.relations}
    for entity in value.entities:
        text(entity.name, "entity name")
        require(len({f.name for f in entity.fields}) == len(entity.fields), "duplicate field name")
        for field in entity.fields: text(field.name, "field name")
    for relation in value.relations:
        text(relation.name, "relation name")
        require(relation.source in entities and relation.target in entities, "dangling endpoint")
        for bound in (relation.targets_per_source, relation.sources_per_target):
            require(bound.minimum >= 0 and (bound.maximum == "unbounded" or bound.maximum >= bound.minimum), "invalid cardinality")
    for rule in value.constraints:
        require(rule.context in entities, "unknown rule context")
        if rule.scope == "invariant": require(rule.operation is None, "invariant has operation")
        else: text(rule.operation, "eligibility operation label")
        for expr in (rule.applies, rule.assertion, rule.unless):
            require(expression_type(expr, rule.context, entities, relations) == ("boolean", False), "rule requires Boolean")
    for residual in value.residuals:
        text(residual.family, "residual family")
        text(residual.text, "residual text")
    return value
