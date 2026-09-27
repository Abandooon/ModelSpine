"""Public contract probes, not natural-language or heldout acceptance."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "adapters"))
from modelspine_protocols import ArtifactRef, ContractError, decode, digest
from modelspine_protocols.domain_language import DomainDefinition
from besser_finite import generate_web_trial, project_definition

EXAMPLES = json.loads((ROOT / "packages/protocols/contracts/finite-domain-examples.json").read_text(encoding="utf-8"))


def definition(data=None):
    return decode(DomainDefinition, data or EXAMPLES["definition"])


def reference(value):
    return ArtifactRef("engineering", value.id, value.version, digest(value))


class BoundaryTests(unittest.TestCase):
    def test_empty_project_identity_rejected_before_source_import(self):
        value = definition()
        ref = ArtifactRef("", value.id, value.version, digest(value))
        with self.assertRaises(ContractError) as error:
            project_definition(value, ref)
        self.assertEqual(error.exception.code, "invalid")
        self.assertEqual(str(error.exception), "incomplete artifact reference")

    def test_wrong_binding_rejected_before_source_import(self):
        value = definition()
        for ref in (ArtifactRef("engineering", value.id, "wrong", digest(value)),
                    ArtifactRef("engineering", value.id, value.version, "0" * 64)):
            with self.assertRaises(ContractError) as error:
                project_definition(value, ref)
            self.assertEqual(error.exception.code, "conflict")

    def test_dangling_endpoint_rejected(self):
        data = deepcopy(EXAMPLES["definition"])
        data["relations"][0]["target"] = "missing-type"
        value = definition(data)
        with self.assertRaises(ContractError):
            project_definition(value, reference(value))

    def test_zero_maximum_not_silently_widened(self):
        data = deepcopy(EXAMPLES["definition"])
        data["relations"][0]["targets_per_source"] = {"minimum": 0, "maximum": 0}
        value = definition(data)
        with self.assertRaises(ContractError) as error:
            project_definition(value, reference(value))
        self.assertEqual(error.exception.code, "unsupported")


@unittest.skipUnless(importlib.util.find_spec("besser"), "pinned external BESSER checkout not installed")
class BesserProjectionTests(unittest.TestCase):
    def test_direction_and_sentinel_are_reported(self):
        value = definition()
        model, report = project_definition(value, reference(value))
        association, = model.associations
        ends = {end.name: end for end in association.ends}
        self.assertEqual(ends["relation0_target"].type.name, "Entity0")  # part sorted before unit
        self.assertEqual((ends["relation0_target"].multiplicity.min, ends["relation0_target"].multiplicity.max), (1, 2))
        self.assertEqual(ends["relation0_source"].multiplicity.max, 9999)
        row = next(m for m in report["mapping"] if m["element"] == "uses")
        self.assertEqual(row["parse"], "lossy")
        self.assertFalse(report["delivery_eligible"])

    def test_public_rule_and_residual_are_not_erased(self):
        value = definition(EXAMPLES["residual_definition"])
        model, report = project_definition(value, reference(value))
        self.assertFalse(model.constraints)
        for element in ("active-cap", "time-window"):
            row = next(m for m in report["mapping"] if m["element"] == element)
            self.assertEqual(row["generate"], "unsupported")
            self.assertIn(element, [r["element"] for r in report["residuals"]])
        self.assertEqual(report["original"], EXAMPLES["residual_definition"])

    def test_optional_nullable_and_names_stay_explicit(self):
        data = deepcopy(EXAMPLES["scalar_projection_positive"])
        field = data["entities"][0]["fields"][0]
        field.update(required=False, nullable=False, name="'\nunsafe display")
        value = definition(data)
        model, report = project_definition(value, reference(value))
        cls = next(t for t in model.types if t.name == "Entity0")
        prop, = cls.attributes
        self.assertEqual(prop.name, "field0")
        self.assertTrue(prop.is_optional)
        self.assertEqual(report["mapping"][1]["parse"], "lossy")
        self.assertEqual(report["original"], data)

    def test_unconditional_integer_rule_translation(self):
        data = deepcopy(EXAMPLES["definition"])
        data["relations"] = []
        data["entities"] = [data["entities"][0]]
        data["entities"][0]["fields"][0]["value_type"] = "integer"
        rule = data["constraints"][0]
        rule["applies"] = {"op": "literal", "args": [], "symbol": None, "value": True}
        rule["assertion"]["args"][0] = {"op": "field", "args": [], "symbol": "enabled", "value": None}
        value = definition(data)
        model, report = project_definition(value, reference(value))
        constraint, = model.constraints
        self.assertEqual(constraint.expression, "context Entity0 inv rule0: self.field0 <= 1")
        self.assertEqual(report["mapping"][-1]["generate"], "lossy")

    def test_generation_refuses_existing_output(self):
        value = definition()
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "human.txt"
            marker.write_text("unchanged", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                generate_web_trial(value, reference(value), Path(temporary))
            self.assertEqual(marker.read_text(encoding="utf-8"), "unchanged")

    def test_missing_is_null_and_nullable_comparison_remain_residual(self):
        for operator in ("is_null", "eq"):
            data = deepcopy(EXAMPLES["scalar_projection_positive"])
            field = data["entities"][0]["fields"][0]
            field.update(required=False, nullable=True, value_type="integer")
            read = {"op":"field", "args":[], "symbol":"enabled", "value":None}
            args = [read] if operator == "is_null" else [read, read]
            data["constraints"] = [{"id":"partial", "context":"unit",
                "applies":{"op":"literal", "args":[], "symbol":None, "value":True},
                "unless":{"op":"literal", "args":[], "symbol":None, "value":False},
                "assertion":{"op":operator, "args":args, "symbol":None, "value":None}}]
            value = definition(data)
            model, report = project_definition(value, reference(value))
            self.assertFalse(model.constraints)
            self.assertEqual(report["mapping"][-1]["generate"], "unsupported")
            self.assertEqual(report["original"]["constraints"], data["constraints"])


if __name__ == "__main__":
    unittest.main()
