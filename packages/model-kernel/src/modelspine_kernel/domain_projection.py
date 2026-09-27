"""Explicit lossless definition projection only; never commits a model."""
from modelspine_protocols import FieldSpec, KindSpec, Metamodel, MetamodelRef, require
from modelspine_protocols.domain_language import validate_definition


def to_scalar_metamodel(definition):
    definition = validate_definition(definition)
    require(not definition.relations and not definition.constraints and not definition.residuals,
            "scalar kernel cannot preserve relations, predicates or residuals", "unsupported")
    require(bool(definition.entities), "scalar metamodel needs entity types")
    require(all(f.required and not f.nullable for e in definition.entities for f in e.fields),
            "scalar kernel requires all fields present and nonnullable", "unsupported")
    # IDs, not editable display names, become the legacy kind and field keys.
    return Metamodel(MetamodelRef(definition.id, definition.version), tuple(
        KindSpec(e.id, tuple(FieldSpec(f.id, f.value_type) for f in e.fields)) for e in definition.entities))
