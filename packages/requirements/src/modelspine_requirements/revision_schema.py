"""Fixed generation shape for RevisionCandidate; not a semantic validator.

No DTO reflection or general schema framework. Local strict inspection remains
authoritative for references, types, evidence, resource bounds and residuals.
"""

VERSION = "revision-output-schema/0.1"


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
    scalar = {"anyOf": [integer, string, boolean]}
    # The argument recursion and discriminated leaves cover every Expression op.
    # Operand types/scope and arithmetic compatibility still require the checker.
    def expression(ops, arity, symbol=null, value=null):
        return obj(op=enum(*ops), args=array(ref("Expression"), minItems=arity, maxItems=arity),
                   symbol=symbol, value=value)

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
        "Expression": {"anyOf": [
            expression(("literal",), 0, value=scalar),
            expression(("instant",), 0, value=string),
            expression(("duration",), 0, value=integer),
            expression(("self",), 0),
            expression(("var",), 0, symbol=string),
            expression(("get", "navigate"), 1, symbol=string),
            expression(("filter",), 2, symbol=string),
            expression(("count", "not", "is_null"), 1),
            expression(("eq", "lt", "le", "and", "or", "implies", "add", "sub"), 2),
        ]},
        "Constraint": {"anyOf": [
            obj(id=string, context=string, scope=enum("invariant"), operation=null,
                applies=ref("Expression"), assertion=ref("Expression"), unless=ref("Expression")),
            obj(id=string, context=string, scope=enum("eligibility"), operation=string,
                applies=ref("Expression"), assertion=ref("Expression"), unless=ref("Expression")),
        ]},
        "DomainDefinition": obj(schema_version=enum("finite-domain/0.2"), id=string, version=string,
                                entities=array(ref("EntityType")), relations=array(ref("BinaryRelation")),
                                constraints=array(ref("Constraint")), residuals=array(ref("Residual"))),
    }
    schema = obj(schema_version=enum("typed-domain-revision/0.1"), request_hash=string,
                 revision_ref=ref("ArtifactRef"), status=enum("unconfirmed"),
                 definition=ref("DomainDefinition"), traces=array(ref("Trace")), issues=array(ref("Issue")))
    schema["$defs"] = definitions
    return {"type": "json_schema", "name": "modelspine_revision_01", "strict": True, "schema": schema}
