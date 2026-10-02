from dataclasses import replace
from hashlib import sha256
import unittest
from modelspine_protocols import ArtifactRef, ContractError, decode
from modelspine_protocols.review import ReviewAction
from modelspine_requirements.domain_modeling import prepare_request
from modelspine_requirements.review import create_session, apply_action, review_input, review_ref
from modelspine_requirements.revision_request import prepare_revision_request, verify_revision_request


class RevisionContextTests(unittest.TestCase):
    def test_rejected_parent_is_retained_and_wrong_actions_rejected(self):
        raw = b'Original requirements.'
        request = prepare_request(raw, ArtifactRef("p", "source", "1", sha256(raw).hexdigest()), request_id="r", scope="engineering")
        session = create_session(request, b'{broken', session_id="s")
        view = review_input(session)
        action = ReviewAction("model-review/0.1", "answer", "p", decode(ArtifactRef, view["request_ref"]),
                              decode(ArtifactRef, view["candidate_ref"]), review_ref(session), decode(ArtifactRef, view["questions"][0]["ref"]),
                              "actor", "answer", "Change requirement; unknown details remain", (), None)
        session, receipt = apply_action(session, action)
        ref = decode(ArtifactRef, receipt["action_ref"])
        result = prepare_revision_request(session, expected_review_ref=review_ref(session), action_refs=(ref,))
        self.assertEqual(verify_revision_request(result), result)
        self.assertEqual(result["context"]["original_source_text"], raw.decode())
        self.assertEqual(result["context"]["parent_candidate_base64"], view["candidate_base64"])
        for refs in ((), (ref, ref), (replace(ref, content_hash="0" * 64),)):
            with self.assertRaises(ContractError): prepare_revision_request(session, expected_review_ref=review_ref(session), action_refs=refs)
