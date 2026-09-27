"""Experimental finite-domain projection for the pinned BESSER Web target.

The caller supplies the audited BESSER checkout on sys.path. This module neither
installs dependencies nor evaluates ProjectModel instances. Generated applications
are diagnostic candidates, never a delivery or a replacement domain validator.
"""
from pathlib import Path

from modelspine_protocols import ArtifactRef, digest, dumps, require, to_data, validate_artifact_ref
from modelspine_protocols.domain_language import DomainDefinition, validate_definition

SOURCE_COMMIT = "9cf7a90928f44dabbe418dab69879014319ee38e"
TARGET = "besser.generators.web_app.web_app_generator.WebAppGenerator"


def project_definition(definition: DomainDefinition, reference: ArtifactRef):
    """Return (B-UML model, explicit support report); raise on invalid input.

    Names are generated from sorted IDs, with an explicit ID/name map. User text
    never becomes target code. Name mappings are local to this definition hash.
    Every rule/Residual retains its entire original payload in the report.
    """
    definition = validate_definition(definition)
    reference = validate_artifact_ref(reference)
    require((reference.artifact_id, reference.revision, reference.content_hash) ==
            (definition.id, definition.version, digest(definition)),
            "definition reference does not match actual input", "conflict")
    for relation in definition.relations:
        for bound in (relation.targets_per_source, relation.sources_per_target):
            require(bound.maximum != 0, "BESSER cannot represent maximum zero", "unsupported")
            require(not (bound.maximum == "unbounded" and bound.minimum > 9999),
                    "BESSER unlimited sentinel is below the requested minimum", "unsupported")

    from besser.BUML.metamodel.structural import (
        BinaryAssociation, Class, Constraint, DomainModel, Multiplicity, Property,
        BooleanType, IntegerType, StringType,
    )

    mapping = []
    classes, fields, associations, constraints = {}, {}, set(), set()
    types = {"boolean": BooleanType, "integer": IntegerType, "string": StringType}
    for index, entity in enumerate(sorted(definition.entities, key=lambda e: e.id)):
        cls = Class(name=f"Entity{index}", attributes=set())
        classes[entity.id] = cls
        mapping.append(dict(element=entity.id, target=cls.name, parse="exact", generate="lossy",
                            reason="Entity identity mapped; runtime identity/version/partial population are not implemented."))
        properties = set()
        for ordinal, field in enumerate(sorted(entity.fields, key=lambda f: f.id)):
            prop = Property(name=f"field{ordinal}", type=types[field.value_type],
                            multiplicity=Multiplicity(1 if field.required else 0, 1),
                            is_optional=field.nullable or not field.required)
            fields[field.id] = prop
            properties.add(prop)
            mapping.append(dict(element=field.id, target=f"{cls.name}.{prop.name}",
                                parse="exact" if field.required and not field.nullable else "lossy",
                                generate="lossy", reason="Target coercion, Int64 range and Missing/Unknown are not equivalent; optional and nullable share is_optional."))
        cls.attributes = properties
    for index, relation in enumerate(sorted(definition.relations, key=lambda r: r.id)):
        def multiplicity(bounds):
            return Multiplicity(bounds.minimum, "*" if bounds.maximum == "unbounded" else bounds.maximum)
        name = f"relation{index}"
        association = BinaryAssociation(name=name, ends={
            Property(name=name + "_source", type=classes[relation.source],
                     multiplicity=multiplicity(relation.sources_per_target)),
            Property(name=name + "_target", type=classes[relation.target],
                     multiplicity=multiplicity(relation.targets_per_source)),
        })
        associations.add(association)
        sentinel = any(b.maximum == "unbounded" or b.maximum >= 9999
                       for b in (relation.targets_per_source, relation.sources_per_target))
        mapping.append(dict(element=relation.id, target=name, parse="lossy" if sentinel else "exact",
                            generate="lossy", reason="Direction and bounded endpoints mapped; 9999/unbounded conflation when applicable. Both cardinalities, distinct tuples and closed population require external enforcement."))
    for index, rule in enumerate(sorted(definition.constraints, key=lambda r: r.id)):
        assertion = rule.assertion
        eligible = (rule.applies.op == "literal" and rule.applies.value is True
                    and rule.unless.op == "literal" and rule.unless.value is False
                    and assertion.op in ("le", "lt", "eq")
                    and assertion.args[0].op == "field" and assertion.args[1].op == "literal"
                    and type(assertion.args[1].value) is int)
        if eligible:
            field = next(f for e in definition.entities for f in e.fields if f.id == assertion.args[0].symbol)
            eligible = field.required and not field.nullable and field.value_type == "integer"
        expression = None
        if eligible:
            cls = classes[rule.context]
            operator = {"le": "<=", "lt": "<", "eq": "="}[assertion.op]
            expression = f"context {cls.name} inv rule{index}: self.{fields[field.id].name} {operator} {assertion.args[1].value}"
            constraints.add(Constraint(name=f"rule{index}", context=cls, expression=expression, language="OCL"))
        mapping.append(dict(element=rule.id, target=expression,
                            parse="exact" if eligible else "unsupported",
                            generate="lossy" if eligible else "unsupported",
                            scope="known signed-64-bit integer on Create only" if eligible else None,
                            reason="Partial values and update/transaction enforcement remain residual." if eligible
                            else "Conditional/count/null/logic rules retained verbatim; no speculative OCL translation."))
    for residual in definition.residuals:
        mapping.append(dict(element=residual.id, target=None, parse="unsupported", generate="unsupported",
                            reason="Explicit residual retained; required residual blocks delivery."))
    model = DomainModel(name="FiniteTrial", types=set(classes.values()),
                        associations=associations, constraints=constraints)
    structural = model.validate()
    report = dict(schema_version="besser-finite-trial/0.1", source_commit=SOURCE_COMMIT, target=TARGET,
                  definition_ref=to_data(reference), original=to_data(definition), mapping=mapping,
                  structural_validation=structural, instance_validation="not_run",
                  requirement_fidelity="not_checked", delivery_eligible=False,
                  residuals=[dict(element=m["element"], status="unknown", reason=m["reason"])
                             for m in mapping if m["generate"] != "exact"])
    return model, report


def generate_web_trial(definition: DomainDefinition, reference: ArtifactRef, output_dir: Path):
    """Write one diagnostic Web candidate into a NEW directory; never overwrite.

    Failure propagates and any partial output remains for inspection. Caller owns
    filesystem permissions, source attestation, command receipts and build/run.
    """
    model, report = project_definition(definition, reference)
    from besser.BUML.metamodel.gui import GUIModel, Module, Screen, Text
    from besser.generators.web_app import WebAppGenerator

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    report_path = output_dir / "modelspine-support.json"
    report["generation_status"] = "started"
    report_path.write_text(dumps(report), encoding="utf-8")
    screen = Screen(name="Trial", description="Diagnostic candidate with residual obligations",
                    view_elements={Text(name="warning", content="Diagnostic trial; business rules are incomplete.")},
                    is_main_page=True)
    gui = GUIModel(name="FiniteTrial", package="org.modelspine.trial", versionCode="1", versionName="0.1",
                   modules={Module(name="TrialModule", screens={screen})}, description="Source adaptation trial")
    WebAppGenerator(model=model, gui_model=gui, output_dir=str(output_dir)).generate()
    report["generation_status"] = "generated_not_validated"
    report_path.write_text(dumps(report), encoding="utf-8")
    return report
