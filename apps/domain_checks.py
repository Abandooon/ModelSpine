"""Explicit finite-domain/0.1 checker adapter; pure offline evaluation, no writes."""
from dataclasses import dataclass

from modelspine_protocols import checked, digest, dumps, require, validate_artifact_ref
from modelspine_protocols.domain_language import (
    DomainDefinition, ProjectModel, scalar_type, text, validate_definition,
)

CHECKER = "finite-domain-checker/0.1"


@dataclass(frozen=True)
class Result:
    obligation: str
    target: str
    status: str
    reason: str


@dataclass(frozen=True)
class DomainReport:
    definition_hash: str
    project_hash: str
    checker: str
    outcomes: tuple[Result, ...]
    requirement_fidelity: str = "not_checked"


@dataclass(frozen=True)
class Value:
    state: str
    value: object = None


def _evaluate(expr, obj, links, complete):
    op = expr.op
    if op == "literal":
        return Value("known", expr.value)
    if op == "field":
        slot = next((s for s in obj.slots if s.field == expr.symbol), None)
        # Slot absence is structural input information. Reading it produces an
        # epistemic unknown; required/optional diagnostics belong to check_project.
        return Value("unknown") if slot is None else Value(slot.state, slot.value)
    if op == "count":
        if not complete:
            return Value("unknown")
        relation, direction = expr.symbol.rsplit(":", 1)
        return Value("known", sum(link.relation == relation and
                     (link.source if direction == "out" else link.target) == obj.id for link in links))
    args = [_evaluate(a, obj, links, complete) for a in expr.args]
    if op == "is_null":
        return Value("known", args[0].state == "null") if args[0].state in ("known", "null") else args[0]
    if any(a.state == "error" for a in args):
        return Value("error")
    if op in ("and", "or", "implies"):
        left, right = args
        if op == "implies":
            left = Value("known", not left.value) if left.state == "known" else left
            op = "or"
        decisive = op == "or"
        if any(a.state == "known" and a.value is decisive for a in (left, right)):
            return Value("known", decisive)
        if any(a.state != "known" for a in (left, right)):
            return Value("unknown")
        return Value("known", not decisive)
    if any(a.state == "null" for a in args):
        # An illegal business null remains an error even beside an unknown read.
        return Value("error")
    if any(a.state == "unknown" for a in args):
        return Value("unknown")
    if op == "not":
        return Value("known", not args[0].value)
    left, right = (a.value for a in args)
    return Value("known", {"eq": lambda: left == right,
                           "lt": lambda: left < right, "le": lambda: left <= right}[op]())


def check_project(definition: DomainDefinition, project: ProjectModel, *, project_id: str) -> DomainReport:
    definition = validate_definition(definition)
    project = checked(project, ProjectModel)
    try:
        dumps(project).encode("utf-8")
    except UnicodeEncodeError:
        require(False, "project is not UTF-8 encodable")
    validate_artifact_ref(project.definition)
    require((project.definition.project_id, project.definition.artifact_id,
             project.definition.revision, project.definition.content_hash) ==
            (project_id, definition.id, definition.version, digest(definition)),
            "project definition identity/version/hash mismatch", "conflict")
    text(project.id, "project model ID")
    text(project.version, "project model version")
    require(len(project.objects) <= 256 and len(project.links) <= 4096, "project size limit", "unsupported")
    objects = {o.id: o for o in project.objects}
    require(len(objects) == len(project.objects), "duplicate instance ID")
    entities = {e.id: e for e in definition.entities}
    relations = {r.id: r for r in definition.relations}
    require(len(set(project.links)) == len(project.links), "duplicate relation tuple")
    outcomes = []
    invalid_objects = set()
    for obj in project.objects:
        text(obj.id, "instance ID")
        require(obj.entity in entities, "unknown instance entity")
        fields = {f.id: f for f in entities[obj.entity].fields}
        slots = {s.field: s for s in obj.slots}
        require(len(slots) == len(obj.slots) and slots.keys() <= fields.keys(), "unknown/duplicate instance field")
        for field in fields.values():
            slot = slots.get(field.id)
            status, reason = "satisfied", "known value"
            if slot is None:
                status, reason = ("violated", "required field missing") if field.required else ("not_applicable", "optional field absent")
            elif slot.state == "unknown":
                require(slot.value is None, "unknown slot carries a value")
                status, reason = "unknown", "value unknown"
            elif slot.state == "null":
                require(slot.value is None, "null slot carries a value")
                status, reason = ("satisfied", "nullable value") if field.nullable else ("violated", "nonnullable field is null")
            elif scalar_type(slot.value) != field.value_type:
                status, reason = "violated", "field type mismatch"
            elif type(slot.value) is int and not -(2**63) <= slot.value < 2**63:
                status, reason = "violated", "integer outside signed 64-bit range"
            if status == "violated":
                invalid_objects.add(obj.id)
            outcomes.append(Result(field.id, obj.id, status, reason))
    for link in project.links:
        require(link.relation in relations and link.source in objects and link.target in objects, "dangling relation tuple")
        relation = relations[link.relation]
        require(objects[link.source].entity == relation.source and objects[link.target].entity == relation.target,
                "relation tuple endpoint type mismatch")
    for relation in definition.relations:
        for direction, entity, bounds in (("out", relation.source, relation.targets_per_source),
                                          ("in", relation.target, relation.sources_per_target)):
            for obj in project.objects:
                if obj.entity != entity:
                    continue
                count = sum(link.relation == relation.id and
                            (link.source if direction == "out" else link.target) == obj.id for link in project.links)
                if bounds.maximum != "unbounded" and count > bounds.maximum:
                    status = "violated"
                elif not project.population_complete:
                    status = "unknown"
                else:
                    status = "satisfied" if count >= bounds.minimum else "violated"
                outcomes.append(Result(relation.id + ":" + direction, obj.id, status,
                                       f"observed count={count}; population_complete={project.population_complete}"))
    for rule in definition.constraints:
        for obj in project.objects:
            if obj.entity != rule.context:
                continue
            if obj.id in invalid_objects:
                outcomes.append(Result(rule.id, obj.id, "error", "invalid context instance"))
                continue
            applies = _evaluate(rule.applies, obj, project.links, project.population_complete)
            unless = _evaluate(rule.unless, obj, project.links, project.population_complete)
            if "error" in (applies.state, unless.state):
                status, reason = "error", "invalid applicability/exception evaluation"
            elif (applies.state == "known" and applies.value is False) or (unless.state == "known" and unless.value is True):
                status, reason = "not_applicable", "false applicability or true exception"
            elif applies.state != "known" or unless.state != "known":
                status, reason = "unknown", "applicability/exception unknown"
            else:
                result = _evaluate(rule.assertion, obj, project.links, project.population_complete)
                status = ("satisfied" if result.value else "violated") if result.state == "known" else result.state
                reason = "assertion evaluated"
            outcomes.append(Result(rule.id, obj.id, status, reason))
        if not any(o.entity == rule.context for o in project.objects):
            outcomes.append(Result(rule.id, project.id, "not_applicable" if project.population_complete else "unknown",
                                   "no observed context instances; not a non-vacuous rule witness"))
    for residual in definition.residuals:
        outcomes.append(Result(residual.id, definition.id, "unknown", "unsupported execution: " + residual.family))
    if not project.population_complete:
        outcomes.append(Result("population", project.id, "unknown", "unobserved instances may violate rules"))
    return DomainReport(digest(definition), digest(project), CHECKER, tuple(outcomes))
