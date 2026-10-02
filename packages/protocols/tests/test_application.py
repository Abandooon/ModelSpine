from dataclasses import replace
import unittest
from modelspine_protocols import ArtifactRef, ContractError, decode, to_data
from modelspine_protocols.application import LocalWebSpec, LocalAccess, EditScope, spec_content_hash, validate_spec


class ApplicationContractTests(unittest.TestCase):
    def test_closed_draft_and_approval_hash_binding(self):
        ref = ArtifactRef("p", "x", "1", "a" * 64)
        spec = LocalWebSpec("local-project-web/0.1", "app", "1", "p", ref, ref, ref, ref, ref,
                           None, None, None, (), (), None, None, (), (), (), (), ())
        self.assertEqual(validate_spec(decode(LocalWebSpec, to_data(spec))), spec)
        self.assertEqual(spec_content_hash(spec), spec_content_hash(replace(spec, review_ref=replace(ref, revision="2"), confirmation_refs=(ref,))))
        self.assertNotEqual(spec_content_hash(spec), spec_content_hash(replace(spec, edit_scope=EditScope(("x",), (), ()))))
        data = to_data(spec); data["default_policy"] = "allow"
        with self.assertRaises(ContractError): decode(LocalWebSpec, data)
        with self.assertRaises(ContractError): validate_spec(replace(spec, project_id="wrong"))
        with self.assertRaises(ContractError):
            validate_spec(replace(spec, access=LocalAccess("0.0.0.0", "single_local_user", "session_token", ())))
