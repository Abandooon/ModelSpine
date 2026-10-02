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
from modelspine_protocols.review import ReviewAction, ProjectSubmission, ProposalAdoption
from modelspine_protocols.domain_language import ProjectModel, Instance, Slot


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

    def project_submission(self, view, identity="instance", *, slots=(), complete=False):
        project = ProjectModel("finite-project/0.1", "instances", "1", decode(ArtifactRef, view["definition_ref"]),
                               (Instance("d1", "device", slots),), (), complete)
        return ProjectSubmission("model-review-project/0.1", identity, view["project_id"],
                                 decode(ArtifactRef, view["request_ref"]), decode(ArtifactRef, view["candidate_ref"]),
                                 decode(ArtifactRef, view["review_ref"]), "instance-author", "example", project)

    def saved_proposal(self, root=None, raw=None):
        root = root or self.root
        view = app.read_review(root)
        raw = raw if raw is not None else b" \n" + base64.b64decode(view["candidate_base64"])
        proposal = replace(action(view, "proposal"), kind="propose_edit", question_ref=None,
                           text="explicit engineering edit", proposal_base64=base64.b64encode(raw).decode())
        app.submit_action(root, proposal)
        view = app.read_review(root)
        adoption = ProposalAdoption("model-review-adoption/0.1", "adopt", view["project_id"],
                                    decode(ArtifactRef, view["request_ref"]), decode(ArtifactRef, view["candidate_ref"]),
                                    decode(ArtifactRef, view["review_ref"]), "adopter",
                                    decode(ArtifactRef, view["proposals"][-1]["ref"]), "adopt this saved proposal")
        return view, adoption

    def test_instances_binding_states_and_actual_checker_readonly(self):
        for index, (purpose, slots, complete, status) in enumerate((
                ("example", (), False, "violated"),
                ("counterexample", (Slot("ready", "unknown", None),), True, "unknown"),
                ("project", (Slot("ready", "known", True),), True, "satisfied"))):
            view = app.read_review(self.root)
            submission = replace(self.project_submission(view, str(index), slots=slots, complete=complete), purpose=purpose)
            receipt = app.save_project(self.root, submission)
            ref = decode(ArtifactRef, receipt["project_ref"])
            head = decode(ArtifactRef, receipt["review_ref"])
            original = (self.root / app.STATE).read_bytes()
            self.assertEqual(app.save_project(self.root, submission)["status"], "already_recorded")
            entry = app.read_project(self.root, ref, expected_review_ref=head)
            self.assertEqual(entry["purpose"], purpose)
            report = app.check_saved_project(self.root, ref, expected_review_ref=head)
            self.assertIn({"obligation": "open-count", "target": "engineering", "status": "unknown",
                           "reason": "unsupported execution: cardinality"}, report["report"]["outcomes"])
            self.assertEqual(report["required_residuals"], ["open-count"])
            outcomes = {x["obligation"]: x["status"] for x in report["report"]["outcomes"]}
            self.assertEqual(outcomes["ready"], status)
            if not complete:
                self.assertEqual(outcomes["population"], "unknown")
            self.assertEqual((self.root / app.STATE).read_bytes(), original)
        view = app.read_review(self.root)
        bad = self.project_submission(view, "bad-definition")
        with self.assertRaises(ContractError):
            app.save_project(self.root, replace(bad, project=replace(bad.project, definition=replace(bad.project.definition, revision="wrong"))))

    def test_optional_missing_is_not_rule_pass(self):
        old = app._load(self.root)
        data = json.loads(base64.b64decode(self.view["candidate_base64"]))
        data["definition"]["entities"][0]["fields"][0]["required"] = False
        root = self.root / "optional"; root.mkdir()
        view = app.create_review(root, old.request, dumps(data).encode(), session_id="optional")
        receipt = app.save_project(root, self.project_submission(view, complete=True))
        report = app.check_saved_project(root, decode(ArtifactRef, receipt["project_ref"]),
                                         expected_review_ref=decode(ArtifactRef, receipt["review_ref"]))
        outcomes = {x["obligation"]: x["status"] for x in report["report"]["outcomes"]}
        self.assertEqual(outcomes["ready"], "not_applicable")
        self.assertEqual(outcomes["ready-rule"], "unknown")

    def test_adoption_reopens_parent_bytes_answers_and_resets_current_evidence(self):
        receipt = app.save_project(self.root, self.project_submission(self.view, slots=(Slot("ready", "known", True),)))
        project_ref = decode(ArtifactRef, receipt["project_ref"])
        prior_report = app.check_saved_project(self.root, project_ref, expected_review_ref=decode(ArtifactRef, receipt["review_ref"]))
        view = app.read_review(self.root)
        app.submit_action(self.root, replace(action(view, "confirm"), kind="confirm", question_ref=None, targets=("device",)))
        parent, adoption = self.saved_proposal()
        receipt = app.adopt_proposal(self.root, adoption)
        view = app.read_review(self.root)
        self.assertEqual(view["history"][-1]["view"]["candidate_base64"], parent["candidate_base64"])
        self.assertEqual(view["history"][-1]["view"]["actions"], parent["actions"])
        self.assertEqual(view["history"][-1]["view"]["questions"], parent["questions"])
        self.assertEqual(view["history"][-1]["adoption"]["actor"], "adopter")
        self.assertEqual(view["definition_ref"], parent["definition_ref"])
        self.assertNotEqual(view["candidate_ref"]["content_hash"], parent["candidate_ref"]["content_hash"])
        self.assertEqual(view["candidate_ref"]["revision"], "2")
        self.assertEqual(view["candidate_ref"], receipt["next_candidate_ref"])
        self.assertEqual(view["parent_candidate_ref"], parent["candidate_ref"])
        for field in ("confirmations", "projects", "proposals", "actions"):
            self.assertEqual(view[field], [])
        self.assertEqual(view["requirement_fidelity"], "not_checked")
        self.assertEqual(view["instance_conformance"], "not_run")
        self.assertNotEqual(prior_report["candidate_ref"], view["candidate_ref"])
        head = decode(ArtifactRef, view["review_ref"])
        self.assertEqual(app.read_project(self.root, project_ref, expected_review_ref=head)["candidate_ref"], parent["candidate_ref"])
        with self.assertRaises(ContractError): app.check_saved_project(self.root, project_ref, expected_review_ref=head)
        raw = (self.root / app.STATE).read_bytes()
        self.assertEqual(app.adopt_proposal(self.root, adoption)["status"], "already_recorded")
        for changed in (replace(adoption, id="old-window"), replace(adoption, text="different")):
            with self.assertRaises(ContractError): app.adopt_proposal(self.root, changed)
        self.assertEqual((self.root / app.STATE).read_bytes(), raw)
        new = app.save_project(self.root, self.project_submission(view, "new-instances", slots=(Slot("ready", "known", True),)))
        current = app.check_saved_project(self.root, decode(ArtifactRef, new["project_ref"]), expected_review_ref=decode(ArtifactRef, new["review_ref"]))
        self.assertEqual(current["candidate_ref"], view["candidate_ref"])

    def test_adoption_wrong_binding_rejected_proposal_and_invalid_candidate(self):
        _, adoption = self.saved_proposal()
        before = (self.root / app.STATE).read_bytes()
        for field in ("request_ref", "candidate_ref", "expected_review_ref", "proposal_ref"):
            bad = replace(adoption, **{field: replace(getattr(adoption, field), content_hash="f" * 64)})
            with self.subTest(field=field), self.assertRaises(ContractError): app.adopt_proposal(self.root, bad)
        with self.assertRaises(ContractError): app.adopt_proposal(self.root, replace(adoption, project_id="wrong"))
        self.assertEqual((self.root / app.STATE).read_bytes(), before)
        root = self.root / "bad-proposal"; root.mkdir(); app.engineering_demo(root)
        _, bad = self.saved_proposal(root, b'{}')
        with self.assertRaises(ContractError): app.adopt_proposal(root, bad)
        root = self.root / "bad-candidate"; root.mkdir()
        view = app.create_review(root, app._load(self.root).request, b'broken', session_id="bad")
        submission = self.project_submission(self.view)
        submission = replace(submission, candidate_ref=decode(ArtifactRef, view["candidate_ref"]),
                             request_ref=decode(ArtifactRef, view["request_ref"]), expected_review_ref=decode(ArtifactRef, view["review_ref"]))
        with patch.object(app, "check_project") as checker:
            with self.assertRaises(ContractError): app.save_project(root, submission)
            checker.assert_not_called()

    def test_new_writes_failed_replace_preserve_old_head_and_pending(self):
        for name in ("instance", "adoption"):
            root = self.root / name; root.mkdir(); view = app.engineering_demo(root)["reopened"]
            if name == "instance":
                operation = self.project_submission(view)
                function = app.save_project
            else:
                _, operation = self.saved_proposal(root)
                function = app.adopt_proposal
            before = (root / app.STATE).read_bytes()
            with patch.object(app.os, "replace", side_effect=OSError("engineering failure")):
                with self.assertRaises(OSError): function(root, operation)
            self.assertEqual((root / app.STATE).read_bytes(), before)
            self.assertTrue((root / app.PENDING).exists())
            with self.assertRaises(ContractError) as caught: app.read_review(root)
            self.assertEqual(caught.exception.code, "incomplete_write")

    def test_adoption_competing_heads_and_successor_chain(self):
        _, adoption = self.saved_proposal()
        gate = threading.Barrier(2)
        def adopt(identity):
            gate.wait()
            try: return app.adopt_proposal(self.root, replace(adoption, id=identity))["status"]
            except ContractError as exc: return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(adopt, ("left", "right")))
        self.assertEqual(results.count("recorded"), 1)
        self.assertTrue(set(results) <= {"recorded", "busy", "conflict"})
        view = app.read_review(self.root)
        raw = base64.b64decode(view["candidate_base64"]) + b"\n"
        proposal = replace(action(view, "second-proposal"), kind="propose_edit", question_ref=None,
                           proposal_base64=base64.b64encode(raw).decode())
        app.submit_action(self.root, proposal)
        view = app.read_review(self.root)
        second = replace(adoption, id="second-adoption", candidate_ref=decode(ArtifactRef, view["candidate_ref"]),
                         expected_review_ref=decode(ArtifactRef, view["review_ref"]), proposal_ref=decode(ArtifactRef, view["proposals"][0]["ref"]))
        app.adopt_proposal(self.root, second)
        view = app.read_review(self.root)
        self.assertEqual((view["candidate_ref"]["revision"], len(view["history"])), ("3", 2))
        self.assertEqual([x["view"]["candidate_ref"]["revision"] for x in view["history"]], ["1", "2"])


if __name__ == "__main__": unittest.main()
