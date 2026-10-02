from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))
import model_review as review
import revision_request as app
from modelspine_protocols import ArtifactRef, ContractError, decode, dumps
from modelspine_protocols.review import ReviewAction


class RevisionExportTests(unittest.TestCase):
    def test_original_answer_decline_deterministic_export_and_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); view = review.engineering_demo(root)["reopened"]
            decline = ReviewAction("model-review/0.1", "decline", view["project_id"], decode(ArtifactRef, view["request_ref"]),
                                   decode(ArtifactRef, view["candidate_ref"]), decode(ArtifactRef, view["review_ref"]),
                                   decode(ArtifactRef, view["questions"][0]["ref"]), "other actor", "decline", "", (), None)
            review.submit_action(root, decline); view = review.read_review(root)
            refs = tuple(decode(ArtifactRef, a["provenance"]["action_ref"]) for a in view["actions"])
            head = decode(ArtifactRef, view["review_ref"])
            result = app.export_revision_request(root, root / "revision.json", expected_review_ref=head, action_refs=refs)
            self.assertEqual(app.read_revision_request(root / "revision.json"), result)
            self.assertEqual(result["context"]["original_source_text"], view["source_text"])
            self.assertEqual([r["action"]["kind"] for r in result["context"]["responses"]], ["answer", "decline"])
            self.assertIsNone(result["context"]["derived_modeling_request"])
            self.assertIsNone(result["context"]["next_candidate_ref"])
            self.assertEqual(result["context"]["generation_status"], "not_run")
            again = app.export_revision_request(root, root / "again.json", expected_review_ref=head, action_refs=refs)
            self.assertEqual(result, again)
            for bad in (replace(head, revision="wrong"), replace(head, content_hash="0" * 64)):
                with self.assertRaises(ContractError): app.export_revision_request(root, root / "bad.json", expected_review_ref=bad, action_refs=refs)
            with self.assertRaises(FileExistsError): app.export_revision_request(root, root / "revision.json", expected_review_ref=head, action_refs=refs)
            tampered = json.loads((root / "revision.json").read_bytes()); tampered["prompt"] += " edited"
            (root / "revision.json").write_text(dumps(tampered), encoding="utf-8")
            with self.assertRaises(ContractError): app.read_revision_request(root / "revision.json")
            with patch.object(app.os, "fsync", side_effect=OSError("failure")):
                with self.assertRaises(OSError): app.export_revision_request(root, root / "failed.json", expected_review_ref=head, action_refs=refs)
            self.assertTrue((root / "failed.json").exists())


if __name__ == "__main__": unittest.main()
