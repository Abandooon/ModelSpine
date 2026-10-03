"""Fixed generation shape for RevisionCandidate; not a semantic validator.

No DTO reflection or general schema framework. Local strict inspection remains
authoritative for references, types, evidence, resource bounds and residuals.
"""

VERSION = "revision-output-schema/0.2"


def response_format():
    """Return a fresh closed Responses format, so callers cannot mutate a singleton."""
    def obj(**properties):
        return {"type": "object", "properties": properties, "required": list(properties),
                "additionalProperties": False}

    def ref(name):
        return {"$ref": "#/$defs/" + name}

    def array(item, **bounds):
        return {"type": "array", "items": item, **bounds}

    def enum(*values):
        return {"type": "string", "enum": list(values)}

    string = {"type": "string"}
    integer = {"type": "integer"}
    boolean = {"type": "boolean"}
    null = {"type": "null"}
    nullable_string = {"type": ["string", "null"]}
    def expression(ops, arity, items="AnyExpr", symbol=null, value=null):
        return obj(op=enum(*ops), args=array(ref(items) if isinstance(items, str) else items,
                                           minItems=arity, maxItems=arity),
                   symbol=symbol, value=value)

    # Known return categories only, not a second type checker. Get's declaration,
    # nullable flag and lexical variables must still be checked against the model.
    # Homogeneous JSON array items cannot constrain heterogeneous operand positions:
    # Filter and Instant arithmetic intentionally overapproximate the legal pairs.
    mixed_filter = {"anyOf": [ref("SetExpr"), ref("BoolExpr")]}
    mixed_time = {"anyOf": [ref("InstantExpr"), ref("DurationExpr")]}

    definitions = {
        "ArtifactRef": obj(project_id=string, artifact_id=string, revision=string, content_hash=string),
        "SourceSpan": obj(start_line=integer, end_line=integer, quote=string),
        "SourceEvidence": obj(kind=enum("source"), source_ref=ref("ArtifactRef"), span=ref("SourceSpan")),
        "ActionEvidence": obj(kind=enum("action"), question_ref=ref("ArtifactRef"), action_ref=ref("ArtifactRef"),
                              part=enum("question", "correction", "answer", "decline"), quote=string),
        "Evidence": {"anyOf": [ref("SourceEvidence"), ref("ActionEvidence")]},
        "Trace": obj(element=string, evidence=array(ref("Evidence"))),
        "Issue": obj(id=string, kind=enum("ambiguity", "conflict", "missing_information", "unsupported"),
                     text=string, related_ids=array(string), question=nullable_string, evidence=array(ref("Evidence"))),
        "Field": obj(id=string, name=string, value_type=enum("integer", "string", "boolean", "instant"),
                     required=boolean, nullable=boolean),
        "EntityType": obj(id=string, name=string, fields=array(ref("Field"))),
        "Cardinality": obj(minimum=integer, maximum={"anyOf": [integer, enum("unbounded")]}),
        "BinaryRelation": obj(id=string, name=string, source=string, target=string,
                              targets_per_source=ref("Cardinality"), sources_per_target=ref("Cardinality")),
        "Residual": obj(id=string, family=string, text=string, required=boolean),
        "ObjectExpr": {"anyOf": [
            expression(("self",), 0),
            expression(("var",), 0, symbol=string),
        ]},
        "GetExpr": expression(("get",), 1, "ObjectExpr", symbol=string),
        "SetExpr": {"anyOf": [
            expression(("navigate",), 1, "ObjectExpr", symbol=string),
            expression(("filter",), 2, mixed_filter, symbol=string),
        ]},
        "IntExpr": {"anyOf": [
            expression(("literal",), 0, value=integer), ref("GetExpr"),
            expression(("count",), 1, "SetExpr"),
            expression(("add", "sub"), 2, "IntExpr"),
        ]},
        "StringExpr": {"anyOf": [expression(("literal",), 0, value=string), ref("GetExpr")]},
        "BoolExpr": {"anyOf": [
            expression(("literal",), 0, value=boolean), ref("GetExpr"),
            expression(("and", "or", "implies"), 2, "BoolExpr"),
            expression(("not",), 1, "BoolExpr"),
            expression(("is_null",), 1, "AnyExpr"),
            *[expression(("eq",), 2, kind) for kind in ("BoolExpr", "StringExpr")],
            *[expression(("eq", "lt", "le"), 2, kind) for kind in ("IntExpr", "InstantExpr", "DurationExpr")],
        ]},
        "InstantExpr": {"anyOf": [
            expression(("instant",), 0, value=string), ref("GetExpr"),
            expression(("add", "sub"), 2, mixed_time),
        ]},
        "DurationExpr": {"anyOf": [
            expression(("duration",), 0, value=integer),
            expression(("add", "sub"), 2, "DurationExpr"),
            expression(("sub",), 2, "InstantExpr"),
        ]},
        "AnyExpr": {"anyOf": [ref(kind) for kind in
                              ("ObjectExpr", "SetExpr", "IntExpr", "StringExpr", "BoolExpr", "InstantExpr", "DurationExpr")]},
        "Constraint": {"anyOf": [
            obj(id=string, context=string, scope=enum("invariant"), operation=null,
                applies=ref("BoolExpr"), assertion=ref("BoolExpr"), unless=ref("BoolExpr")),
            obj(id=string, context=string, scope=enum("eligibility"), operation=string,
                applies=ref("BoolExpr"), assertion=ref("BoolExpr"), unless=ref("BoolExpr")),
        ]},
        "DomainDefinition": obj(schema_version=enum("finite-domain/0.2"), id=string, version=string,
                                entities=array(ref("EntityType")), relations=array(ref("BinaryRelation")),
                                constraints=array(ref("Constraint")), residuals=array(ref("Residual"))),
    }
    schema = obj(schema_version=enum("typed-domain-revision/0.1"), request_hash=string,
                 revision_ref=ref("ArtifactRef"), status=enum("unconfirmed"),
                 definition=ref("DomainDefinition"), traces=array(ref("Trace")), issues=array(ref("Issue")))
    schema["$defs"] = definitions
    return {"type": "json_schema", "name": "modelspine_revision_02", "strict": True, "schema": schema}
