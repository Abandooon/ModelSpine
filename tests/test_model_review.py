import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))
import model_review as app
from modelspine_protocols import ArtifactRef, ContractError, decode, dumps
from modelspine_protocols.review import ReviewAction


def action(view, identity="next", text="暂不确定"):
    return ReviewAction("model-review/0.1", identity, view["project_id"], decode(ArtifactRef, view["request_ref"]),
                        decode(ArtifactRef, view["candidate_ref"]), decode(ArtifactRef, view["review_ref"]),
                        decode(ArtifactRef, view["questions"][0]["ref"]), "reviewer", "answer", text, (), None)


class ReviewStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.view = app.engineering_demo(self.root)["reopened"]

    def test_reopen_actions_refs_source_and_duplicate_receipt(self):
        response = action(self.view, text="仅当前项目\n保留原回答")
        receipt = app.submit_action(self.root, response)
        saved_bytes = (self.root / app.STATE).read_bytes()
        reloaded = app.read_review(self.root, expected_review_ref=decode(ArtifactRef, receipt["review_ref"]))
        self.assertEqual(reloaded["actions"][-1]["action"]["text"], response.text)
        self.assertEqual(reloaded["candidate_base64"], self.view["candidate_base64"])
        self.assertEqual(reloaded["source_text"], self.view["source_text"])
        self.assertEqual(app.submit_action(self.root, response)["status"], "already_recorded")
        self.assertEqual((self.root / app.STATE).read_bytes(), saved_bytes)
        with self.assertRaises(ContractError):
            app.read_review(self.root, expected_review_ref=decode(ArtifactRef, self.view["review_ref"]))

    def test_old_window_and_id_reuse_do_not_write(self):
        response = action(self.view)
        app.submit_action(self.root, response)
        original = (self.root / app.STATE).read_bytes()
        for wrong in (replace(response, id="old-window"), replace(response, text="changed"),
                      replace(response, candidate_ref=replace(response.candidate_ref, revision="2"))):
            with self.assertRaises(ContractError): app.submit_action(self.root, wrong)
            self.assertEqual((self.root / app.STATE).read_bytes(), original)

    def test_failed_flush_or_replace_never_returns_recorded_or_cached_success(self):
        original = (self.root / app.STATE).read_bytes()
        for operation in ("fsync", "replace"):
            with self.subTest(operation=operation):
                with patch.object(app.os, operation, side_effect=OSError("injected write failure")):
                    with self.assertRaises(OSError): app.submit_action(self.root, action(self.view))
                self.assertEqual((self.root / app.STATE).read_bytes(), original)
                self.assertTrue((self.root / app.PENDING).exists())
                self.assertFalse((self.root / app.LOCK).exists())
                with self.assertRaises(ContractError) as error: app.read_review(self.root)
                self.assertEqual(error.exception.code, "incomplete_write")
                # Test-host recovery only, not an application automatic fallback.
                (self.root / app.PENDING).unlink()

    def test_corrupt_truncated_or_chain_mismatch_does_not_recover_old_state(self):
        initial = (self.root / app.STATE).read_bytes()
        changes = []
        changed = json.loads(initial); changed["session"]["actions"] = []; changes.append(dumps(changed).encode())
        changed = json.loads(initial); changed["head"]["content_hash"] = "0" * 64; changes.append(dumps(changed).encode())
        changed = json.loads(initial); changed["session"]["candidate_base64"] = base64.b64encode(b'{}').decode()
        changes.append(dumps(changed).encode())
        changes.extend((initial[:len(initial) // 2], b'', b'{"head":' + b'9' * 5000 + b'}'))
        for raw in changes:
            with self.subTest(raw=raw[:20]):
                (self.root / app.STATE).write_bytes(raw)
                with self.assertRaises(ContractError) as error: app.read_review(self.root)
                self.assertEqual(error.exception.code, "corrupt")
                with self.assertRaises(ContractError): app.submit_action(self.root, action(self.view))
        (self.root / app.STATE).write_bytes(initial)

    def test_proposal_survives_reopen_without_replacing_candidate(self):
        raw = b'{"definition":{"unsupported":"default=1"}}\xff'
        edit = replace(action(self.view), kind="propose_edit", question_ref=None,
                       text="我要求移除原限制并采用默认值", proposal_base64=base64.b64encode(raw).decode())
        app.submit_action(self.root, edit)
        view = app.read_review(self.root)
        self.assertEqual(view["candidate_ref"], self.view["candidate_ref"])
        self.assertEqual(base64.b64decode(view["proposals"][0]["raw_base64"]), raw)
        self.assertEqual(view["proposals"][0]["inspection"]["status"], "rejected")
        self.assertEqual(view["proposals"][0]["provenance"]["text"], edit.text)

    def test_create_rejected_raw_and_exclusive_existing_store(self):
        stored = app._load(self.root)
        other = self.root / "other"; other.mkdir()
        raw = b'broken input\xff'
        view = app.create_review(other, stored.request, raw, session_id="../../identity-is-not-a-path")
        self.assertEqual(view["inspection"]["status"], "rejected")
        self.assertEqual(base64.b64decode(app.read_review(other)["candidate_base64"]), raw)
        with self.assertRaises(FileExistsError): app.create_review(other, stored.request, b'{}', session_id="x")
        self.assertEqual({p.name for p in other.iterdir()}, {app.STATE})

    def test_explicit_path_permissions_and_lock_failures(self):
        with self.assertRaises(ContractError): app.read_review(Path("relative"))
        (self.root / app.LOCK).write_bytes(b'stale lock')
        with self.assertRaises(ContractError) as error: app.read_review(self.root)
        self.assertEqual(error.exception.code, "busy")
        self.assertEqual((self.root / app.LOCK).read_bytes(), b'stale lock')
        (self.root / app.LOCK).unlink()
        with patch.object(app.os, "open", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError): app.submit_action(self.root, action(self.view))

    def test_competing_writers_cannot_lose_an_action(self):
        gate = threading.Barrier(2)
        def attempt(identity):
            gate.wait()
            try: return app.submit_action(self.root, action(self.view, identity))["status"]
            except ContractError as exc: return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, ("one", "two")))
        self.assertEqual(results.count("recorded"), 1)
        self.assertTrue(set(results) <= {"recorded", "busy", "conflict"})
        self.assertEqual(len(app.read_review(self.root)["actions"]), 2)  # demo + one winner

    def test_cli_reopens_in_another_process_and_reports_truncation(self):
        command = [sys.executable, "-B", "-I", str(Path(app.__file__)), "show", "--project-dir", str(self.root)]
        result = subprocess.run(command, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["review_ref"], self.view["review_ref"])
        (self.root / app.STATE).write_bytes(b'{')
        result = subprocess.run(command, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)["code"], "corrupt")
        self.assertEqual(result.stdout, b'')


if __name__ == "__main__": unittest.main()
