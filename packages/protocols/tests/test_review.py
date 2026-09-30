import base64
from dataclasses import replace
import unittest

from modelspine_protocols import ArtifactRef, ContractError, decode, dumps, loads, to_data
from modelspine_protocols.review import ReviewAction, proposal_bytes, validate_action


class ReviewEnvelopeTests(unittest.TestCase):
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
