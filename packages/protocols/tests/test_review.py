import base64
from dataclasses import replace
import unittest

from modelspine_protocols import ArtifactRef, ContractError, decode, dumps, loads, to_data
from modelspine_protocols.review import ReviewAction, ProposalAdoption, ProjectSubmission, proposal_bytes, validate_action, validate_operation
from modelspine_protocols.domain_language import ProjectModel


class ReviewEnvelopeTests(unittest.TestCase):
    def test_instance_and_adoption_closed_envelopes(self):
        ref = ArtifactRef("p", "d", "1", "a" * 64)
        project = ProjectModel("finite-project/0.1", "instances", "1", ref, (), (), False)
        instance = ProjectSubmission("model-review-project/0.1", "save", "p", ref, ref, ref, "actor", "example", project)
        adopt = ProposalAdoption("model-review-adoption/0.1", "adopt", "p", ref, ref, ref, "actor", ref, "explicit")
        for operation in (instance, adopt):
            self.assertEqual(validate_operation(loads(type(operation), dumps(operation))), operation)
            with self.assertRaises(ContractError): validate_operation(replace(operation, actor=" "))
            with self.assertRaises(ContractError): validate_operation(replace(operation, project_id="other"))
            data = to_data(operation); data["extra"] = None
            with self.assertRaises(ContractError): decode(type(operation), data)
        with self.assertRaises(ContractError): validate_operation(replace(instance, purpose="default"))
        with self.assertRaises(ContractError): validate_operation(replace(adopt, text=""))
    def setUp(self):
        self.ref = ArtifactRef("p", "a", "1", "a" * 64)
        self.action = ReviewAction("model-review/0.1", "x", "p", self.ref, self.ref, self.ref,
                                   self.ref, "actor", "answer", "unknown", (), None)

    def test_strict_nested_envelope_and_roundtrip(self):
        self.assertEqual(loads(ReviewAction, dumps(self.action)), self.action)
        for field in ("schema_version", "kind"):
            data = to_data(self.action); data[field] = "not-supported"
            with self.assertRaises(ContractError): decode(ReviewAction, data)
        data = to_data(self.action); data["request_ref"]["extra"] = True
        with self.assertRaises(ContractError): decode(ReviewAction, data)

    def test_cross_project_and_malformed_refs(self):
        for ref in (replace(self.ref, project_id="other"), replace(self.ref, content_hash="wrong")):
            with self.assertRaises(ContractError): validate_action(replace(self.action, candidate_ref=ref))

    def test_kind_specific_fields_and_empty_unknown_decline(self):
        self.assertEqual(validate_action(self.action).text, "unknown")
        with self.assertRaises(ContractError): validate_action(replace(self.action, text=" \n"))
        self.assertEqual(validate_action(replace(self.action, kind="decline", text="")).text, "")
        for value in (replace(self.action, targets=("x",)), replace(self.action, actor=" "),
                      replace(self.action, question_ref=None), replace(self.action, text="\ud800")):
            with self.assertRaises(ContractError): validate_action(value)

    def test_raw_proposal_is_lossless_and_bounded(self):
        raw = b'not JSON\xff\r\n'
        encoded = base64.b64encode(raw).decode()
        action = replace(self.action, kind="propose_edit", question_ref=None, proposal_base64=encoded)
        self.assertEqual(proposal_bytes(validate_action(action).proposal_base64), raw)
        for bad in ("?", "Zg===", "Zh==", base64.b64encode(b'x' * (256 * 1024 + 1)).decode()):
            with self.assertRaises(ContractError): proposal_bytes(bad)


if __name__ == "__main__": unittest.main()
