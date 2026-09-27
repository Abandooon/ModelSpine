"""Projection rejects semantic loss instead of weakening the scalar kernel."""
from dataclasses import replace
import unittest

from modelspine_protocols import ContractError
from modelspine_protocols.domain_language import DomainDefinition, EntityType, Field, Residual
from modelspine_kernel.domain_projection import to_scalar_metamodel


class DomainProjectionTests(unittest.TestCase):
    def setUp(self):
        self.field = Field("enabled", "Display name", "boolean", True, False)
        self.definition = DomainDefinition("finite-domain/0.1", "demo", "1",
            (EntityType("item", "Renamable name", (self.field,)),), (), (), ())

    def test_stable_keys_and_no_commit(self):
        result = to_scalar_metamodel(self.definition)
        self.assertEqual(result.kinds[0].name, "item")
        self.assertEqual(result.kinds[0].fields[0].name, "enabled")

    def test_optional_nullable_and_residual_rejected(self):
        for field in (replace(self.field, required=False), replace(self.field, nullable=True)):
            with self.assertRaises(ContractError) as caught:
                to_scalar_metamodel(replace(self.definition, entities=(EntityType("item", "Item", (field,)),)))
            self.assertEqual(caught.exception.code, "unsupported")
        with self.assertRaises(ContractError):
            to_scalar_metamodel(replace(self.definition, residuals=(Residual("r", "time", "Within 24h", True),)))
