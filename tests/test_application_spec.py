"""Hand-authored engineering examples only; no generated business requirements."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))
import application_spec as app
import model_review as review
from modelspine_protocols import ArtifactRef, ContractError, decode, digest, dumps, to_data
from modelspine_protocols.application import (LocalWebSpec, EditScope, WebTask, WebView, LocalStorage, LocalAccess,
    ConfigEvidence, PublicAcceptance, ExpectedOutcome, acceptance_digest, spec_content_hash, assess_application)
from modelspine_protocols.domain_language import ProjectModel, Instance, Slot
from modelspine_protocols.review import ReviewAction, ProjectSubmission, WHOLE_CANDIDATE
from modelspine_requirements.domain_modeling import prepare_request


def engineering_fixture(root, *, confirm=True):
    raw = (b'Items have a Boolean flag. Explicit local single-user loopback editor with session token; '
           b'edit/check/save/load, JSON data/project.json, retain all versions. Start with no user data. '
           b'Public acceptance: set flag true, check, save and reload.')
    request = prepare_request(raw, ArtifactRef("web-engineering", "source", "1", sha256(raw).hexdigest()),
                              request_id="request", scope="hand_authored_engineering_only")
    candidate = {"schema_version": "typed-domain-candidate/0.1", "request_hash": digest(request), "status": "unconfirmed",
                 "definition": {"schema_version": "finite-domain/0.1", "id": "d", "version": "1", "entities": [
                    {"id": "item", "name": "Item", "fields": [{"id": "flag", "name": "Flag", "value_type": "boolean", "required": True, "nullable": False}]}],
                    "relations": [], "constraints": [], "residuals": []},
                 "traces": [{"element": name, "evidence": [{"start_line": 1, "end_line": 1, "quote": request.text}]} for name in ("item", "flag")],
                 "issues": []}
    view = review.create_review(root, request, dumps(candidate).encode(), session_id="web")
    project = ProjectModel("finite-project/0.1", "public-example", "1", decode(ArtifactRef, view["definition_ref"]),
                           (Instance("i", "item", (Slot("flag", "known", True),)),), (), True)
    case = PublicAcceptance(ArtifactRef(view["project_id"], "acceptance/flag", "1", "0" * 64),
                            "Set flag, check then persist and reload the identical project", True,
                            ("edit", "check", "save", "load"), project, (ExpectedOutcome("flag", "i", "satisfied"),))
    case = replace(case, ref=replace(case.ref, content_hash=acceptance_digest(case)))
    evidence = tuple(ConfigEvidence(area, request.source, request.text, "Explicit engineering requirement for " + area)
                     for area in ("initial_project", "edit_scope", "tasks", "views", "storage", "access", "acceptance"))
    spec = LocalWebSpec("local-project-web/0.1", "web", "1", view["project_id"], decode(ArtifactRef, view["request_ref"]),
                       request.source, decode(ArtifactRef, view["definition_ref"]), decode(ArtifactRef, view["candidate_ref"]),
                       decode(ArtifactRef, view["review_ref"]), None, "User explicitly starts with no data",
                       EditScope(("item",), ("flag",), ()),
                       tuple(WebTask(name, name, "editor") for name in ("edit", "check", "save", "load")),
                       (WebView("editor", "Items", ("item",), ("flag",), ()),),
                       LocalStorage("local_json", "data/project.json", "retain_all_versions"),
                       LocalAccess("127.0.0.1", "single_local_user", "session_token", ("edit", "check", "save", "load")),
                       evidence, (case,), (), (), ())
    if confirm:
        action = ReviewAction("model-review/0.1", "approve", view["project_id"], spec.request_ref, spec.candidate_ref,
                              spec.review_ref, None, "engineering-user", "confirm",
                              "approve-local-web-spec:" + spec_content_hash(spec), (WHOLE_CANDIDATE,), None)
        receipt = review.submit_action(root, action)
        spec = replace(spec, review_ref=decode(ArtifactRef, receipt["review_ref"]),
                       confirmation_refs=(decode(ArtifactRef, receipt["action_ref"]),))
        view = review.read_review(root)
    return spec, view


class ApplicationSpecTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.spec, self.view = engineering_fixture(self.root)

    def assess(self, spec=None, view=None):
        return assess_application(spec or self.spec, view or self.view, checker=app.check_project)

    def test_ready_exact_confirmation_and_durable_version_chain(self):
        self.assertTrue(self.assess()["generation_ready"])
        result = app.save_spec(self.root, self.spec)
        self.assertEqual(app.read_spec(self.root)["spec_ref"], result["spec_ref"])
        self.assertEqual(app.save_spec(self.root, self.spec)["status"], "already_recorded")
        changed = replace(self.spec, version="2", no_initial_data_reason="Changed explicit decision")
        with self.assertRaises(ContractError): app.save_spec(self.root, changed)
        saved = app.save_spec(self.root, changed, expected_spec_ref=decode(ArtifactRef, result["spec_ref"]))
        self.assertFalse(saved["assessment"]["generation_ready"])
        self.assertIn("spec_confirmation_binding", saved["assessment"]["blockers"])
        self.assertEqual(app.read_spec(self.root)["history_refs"], [result["spec_ref"]])

    def test_drafts_missing_config_sources_confirmation_acceptance_and_unsafe_paths(self):
        variants = [replace(self.spec, storage=None), replace(self.spec, access=None), replace(self.spec, edit_scope=None),
                    replace(self.spec, tasks=()), replace(self.spec, views=()), replace(self.spec, evidence=()),
                    replace(self.spec, acceptance_cases=()), replace(self.spec, confirmation_refs=()),
                    replace(self.spec, required_unresolved=("unknown policy",)),
                    replace(self.spec, unsupported_requirements=("remote integration",)),
                    replace(self.spec, no_initial_data_reason=None),
                    replace(self.spec, initial_project_ref=self.spec.candidate_ref),
                    replace(self.spec, evidence=(replace(self.spec.evidence[0], quote="fabricated"), *self.spec.evidence[1:]))]
        for path in ("../secret.json", "/abs.json", "C:/secret.json", "data\\x.json", "data//x.json", "CON.json", "data/\x00.json", "data/*.json"):
            variants.append(replace(self.spec, storage=replace(self.spec.storage, relative_path=path)))
        for spec in variants:
            with self.subTest(spec=spec): self.assertFalse(self.assess(spec)["generation_ready"])
        draft = app.save_spec(self.root, replace(self.spec, storage=None))
        self.assertEqual(draft["assessment"]["status"], "draft")
        self.assertIn("acceptance_not_checked", assess_application(self.spec, self.view)["blockers"])

    def test_acceptance_hash_and_actual_checker_outcomes_not_claimed_success(self):
        case = self.spec.acceptance_cases[0]
        self.assertIn("duplicate_public_acceptance", self.assess(replace(self.spec, acceptance_cases=(case, case)))["blockers"])
        bad = replace(case, expected_outcomes=(ExpectedOutcome("flag", "i", "violated"),))
        self.assertIn("public_acceptance_binding", self.assess(replace(self.spec, acceptance_cases=(bad,)))["blockers"])
        bad = replace(bad, ref=replace(bad.ref, content_hash=acceptance_digest(bad)))
        self.assertIn("acceptance_outcome_mismatch", self.assess(replace(self.spec, acceptance_cases=(bad,)))["blockers"])
        wrong = replace(case, project=replace(case.project, definition=replace(case.project.definition, revision="wrong")))
        wrong = replace(wrong, ref=replace(wrong.ref, content_hash=acceptance_digest(wrong)))
        self.assertIn("invalid_acceptance_project", self.assess(replace(self.spec, acceptance_cases=(wrong,)))["blockers"])
        hidden = replace(case, public=False)
        hidden = replace(hidden, ref=replace(hidden.ref, content_hash=acceptance_digest(hidden)))
        self.assertIn("public_acceptance_binding", self.assess(replace(self.spec, acceptance_cases=(hidden,)))["blockers"])

    def test_wrong_binding_stale_review_and_required_residual_block(self):
        with self.assertRaises(ContractError):
            app.save_spec(self.root, replace(self.spec, candidate_ref=replace(self.spec.candidate_ref, content_hash="a" * 64)))
        app.save_spec(self.root, self.spec)
        action = ReviewAction("model-review/0.1", "later", self.view["project_id"], self.spec.request_ref,
                              self.spec.candidate_ref, self.spec.review_ref, None, "actor", "confirm", "seen", (WHOLE_CANDIDATE,), None)
        review.submit_action(self.root, action)
        self.assertIn("binding:review_ref", app.read_spec(self.root)["assessment"]["blockers"])
        changed_view = {**self.view, "residuals": [{"required": True}], "issues": [{"text": "unresolved"}]}
        blocked = self.assess(view=changed_view)["blockers"]
        self.assertIn("required_domain_residual", blocked)
        self.assertIn("unresolved_candidate_issues", blocked)

    def test_successful_public_case_required_and_initial_instance_actually_checked(self):
        good = self.spec.acceptance_cases[0]
        definition = review._definition(self.view)
        for state, value, complete in (("unknown", None, True), ("known", 7, True), ("known", True, False)):
            project = replace(good.project, objects=(Instance("i", "item", (Slot("flag", state, value),)),), population_complete=complete)
            report = app.check_project(definition, project, project_id=self.spec.project_id)
            expected = tuple(ExpectedOutcome(x.obligation, x.target, x.status) for x in report.outcomes)
            case = replace(good, project=project, expected_outcomes=expected)
            case = replace(case, ref=replace(case.ref, content_hash=acceptance_digest(case)))
            assessment = self.assess(replace(self.spec, acceptance_cases=(case,)))
            self.assertNotIn("acceptance_outcome_mismatch", assessment["blockers"])
            self.assertIn("missing_successful_public_acceptance", assessment["blockers"])
            view = review.read_review(self.root)
            submission = ProjectSubmission("model-review-project/0.1", f"initial-{state}-{value}-{complete}", view["project_id"],
                                           decode(ArtifactRef, view["request_ref"]), decode(ArtifactRef, view["candidate_ref"]),
                                           decode(ArtifactRef, view["review_ref"]), "actor", "project", project)
            receipt = review.save_project(self.root, submission)
            view = review.read_review(self.root)
            spec = replace(self.spec, initial_project_ref=decode(ArtifactRef, receipt["project_ref"]), no_initial_data_reason=None,
                           review_ref=decode(ArtifactRef, view["review_ref"]))
            self.assertIn("initial_project_not_successful", self.assess(spec, view)["blockers"])
            self.assertIn("initial_project_not_checked", assess_application(spec, view)["blockers"])
        # A successful initial model can pass this gate; it still needs its own exact spec approval.
        view = review.read_review(self.root)
        submission = replace(submission, id="good-initial", expected_review_ref=decode(ArtifactRef, view["review_ref"]), project=good.project)
        receipt = review.save_project(self.root, submission)
        view = review.read_review(self.root)
        spec = replace(self.spec, initial_project_ref=decode(ArtifactRef, receipt["project_ref"]), no_initial_data_reason=None,
                       review_ref=decode(ArtifactRef, view["review_ref"]))
        self.assertNotIn("initial_project_not_successful", self.assess(spec, view)["blockers"])
        self.assertIn("spec_confirmation_binding", self.assess(spec, view)["blockers"])
        approval = ReviewAction("model-review/0.1", "approve-initial", view["project_id"], spec.request_ref, spec.candidate_ref,
                                spec.review_ref, None, "actor", "confirm", "approve-local-web-spec:" + spec_content_hash(spec),
                                (WHOLE_CANDIDATE,), None)
        confirmed = review.submit_action(self.root, approval)
        spec = replace(spec, review_ref=decode(ArtifactRef, confirmed["review_ref"]),
                       confirmation_refs=(decode(ArtifactRef, confirmed["action_ref"]),))
        self.assertTrue(self.assess(spec, review.read_review(self.root))["generation_ready"])

    def test_write_failure_and_truncated_store_never_ready(self):
        with patch.object(app.os, "replace", side_effect=OSError("engineering write failure")):
            with self.assertRaises(OSError): app.save_spec(self.root, self.spec)
        with self.assertRaises(ContractError) as caught: app.read_spec(self.root)
        self.assertEqual(caught.exception.code, "incomplete_write")
        (self.root / app.PENDING).unlink()  # Explicit test-host recovery only.
        app.save_spec(self.root, self.spec)
        (self.root / app.STATE).write_bytes(b'{')
        with self.assertRaises(ContractError) as caught: app.read_spec(self.root)
        self.assertEqual(caught.exception.code, "corrupt")


if __name__ == "__main__": unittest.main()
