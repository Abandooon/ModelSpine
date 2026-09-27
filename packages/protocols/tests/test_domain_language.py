"""Finite language syntax/typing boundaries; public engineering data only."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from modelspine_protocols import ContractError, decode
from modelspine_protocols.domain_language import DomainDefinition, validate_definition


class DomainLanguageTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((Path(__file__).parents[1] / "contracts/finite-domain-examples.json").read_text(encoding="utf-8"))

    def validate(self, data):
        return validate_definition(decode(DomainDefinition, data))

    def test_public_definition_and_residual_are_well_formed(self):
        self.validate(self.data["definition"])
        self.validate(self.data["residual_definition"])

    def test_reference_arity_context_and_type_errors_rejected(self):
        original = self.data["definition"]
        mutations = [
            lambda d: d["relations"][0].update(target="missing"),
            lambda d: d["constraints"][0]["assertion"].update(args=[]),
            lambda d: d["constraints"][0]["applies"].update(symbol="not-a-field"),
            lambda d: d["constraints"][0]["assertion"]["args"][1].update(value="1"),
            lambda d: d["relations"][0]["targets_per_source"].update(minimum=True),
            lambda d: d["relations"][0]["targets_per_source"].update(maximum=0),
            lambda d: d["entities"][1].update(id="unit"),
            lambda d: d.update(imports=[]),
            lambda d: d["entities"][0].update(name="\ud800"),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                data = deepcopy(original)
                mutate(data)
                with self.assertRaises(ContractError):
                    self.validate(data)

    def test_depth_and_integer_limits(self):
        data = deepcopy(self.data["definition"])
        expr = data["constraints"][0]["applies"]
        for _ in range(26):
            expr = dict(op="not", args=[expr], symbol=None, value=None)
        data["constraints"][0]["applies"] = expr
        with self.assertRaises(ContractError) as caught:
            self.validate(data)
        self.assertEqual(caught.exception.code, "unsupported")
        data = deepcopy(self.data["definition"])
        data["constraints"][0]["assertion"]["args"][1]["value"] = 2**63
        with self.assertRaises(ContractError):
            self.validate(data)
