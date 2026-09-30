import base64
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import unittest

from modelspine_protocols import ArtifactRef, ContractError, decode, digest, dumps, to_data
from modelspine_protocols.review import ReviewAction
from modelspine_requirements.domain_modeling import prepare_request
from modelspine_requirements.review import apply_action, create_session, review_input, review_ref


def fixture():
    raw = b'Items have a flag; rules and limits are unresolved.'
    request = prepare_request(raw, ArtifactRef("p", "source", "1", sha256(raw).hexdigest()),
                              request_id="r", scope="review fixture")
    lit = lambda v: {"op": "literal", "args": [], "symbol": None, "value": v}
    span = {"start_line": 1, "end_line": 1, "quote": request.text}
    data = {"schema_version": "typed-domain-candidate/0.1", "request_hash": digest(request), "status": "unconfirmed",
            "definition": {"schema_version": "finite-domain/0.1", "id": "d", "version": "1",
                           "entities": [{"id": "item", "name": "Item", "fields": [
                               {"id": "flag", "name": "Flag", "value_type": "boolean", "required": True, "nullable": False}]}],
                           "relations": [], "constraints": [{"id": "rule", "context": "item", "applies": lit(True),
                               "assertion": {"op": "and", "args": [lit(True), lit(False)], "symbol": None, "value": None},
                               "unless": lit(False)}],
                           "residuals": [{"id": "limit", "family": "quantity", "text": "limit unresolved", "required": True}]},
            "traces": [{"element": i, "evidence": [span]} for i in ("item", "flag", "rule", "limit")],
            "issues": [{"id": i, "kind": "missing_information", "text": "unresolved", "related_ids": ["limit"],
                        "question": "What limit?", "evidence": [span]} for i in ("q1", "q2")]}
    return request, data


def action_for(view, *, identity="a1", kind="answer", text="unknown", question=0, targets=(), raw=None):
    return ReviewAction("model-review/0.1", identity, view["project_id"], decode(ArtifactRef, view["request_ref"]),
                        decode(ArtifactRef, view["candidate_ref"]), decode(ArtifactRef, view["review_ref"]),
                        decode(ArtifactRef, view["questions"][question]["ref"]) if kind in ("answer", "decline") else None,
                        "reader", kind, text, targets, base64.b64encode(raw).decode() if raw is not None else None)


class ReviewTransitionTests(unittest.TestCase):
    def setUp(self):
        self.request, self.data = fixture()
        self.session = create_session(self.request, dumps(self.data).encode(), session_id="s")
        self.view = review_input(self.session)

    def test_same_definition_different_issue_trace_or_original_bytes_changes_candidate(self):
        for mutate in (lambda d: d["issues"][0].update(text="different"),
                       lambda d: d["traces"].reverse()):
            data = deepcopy(self.data); mutate(data)
            view = review_input(create_session(self.request, dumps(data).encode(), session_id="s"))
            self.assertEqual(view["definition_ref"], self.view["definition_ref"])
            self.assertNotEqual(view["candidate_ref"], self.view["candidate_ref"])
        raw = b' \n' + dumps(self.data).encode()
        view = review_input(create_session(self.request, raw, session_id="s"))
        self.assertNotEqual(view["candidate_ref"], self.view["candidate_ref"])
        self.assertEqual(base64.b64decode(view["candidate_base64"]), raw)

    def test_review_revision_changes_even_when_candidate_does_not(self):
        action = action_for(self.view)
        session, receipt = apply_action(self.session, action)
        view = review_input(session)
        self.assertEqual(view["candidate_ref"], self.view["candidate_ref"])
        self.assertNotEqual(view["review_ref"], self.view["review_ref"])
        self.assertIsNone(receipt["next_candidate_ref"])
        self.assertEqual(view["revision_status"], "pending")
        with self.assertRaises(ContractError) as error:
            apply_action(session, replace(action, id="stale-window"))
        self.assertEqual(error.exception.code, "conflict")

    def test_all_binding_dimensions_and_same_text_questions(self):
        action = action_for(self.view)
        self.assertNotEqual(self.view["questions"][0]["ref"], self.view["questions"][1]["ref"])
        changes = {"project_id": "other", "request_ref": replace(action.request_ref, revision="2"),
                   "candidate_ref": replace(action.candidate_ref, content_hash="0" * 64),
                   "expected_review_ref": replace(action.expected_review_ref, revision="1"),
                   "question_ref": replace(action.question_ref, content_hash="b" * 64)}
        for name, value in changes.items():
            with self.subTest(name=name), self.assertRaises(ContractError):
                apply_action(self.session, replace(action, **{name: value}))
        _, data2 = fixture(); data2["issues"][0]["text"] = "changed"
        other = review_input(create_session(self.request, dumps(data2).encode(), session_id="s"))
        with self.assertRaises(ContractError):
            apply_action(self.session, replace(action, question_ref=decode(ArtifactRef, other["questions"][0]["ref"])))

    def test_answers_declines_and_confirmation_never_discharge_issues(self):
        session, _ = apply_action(self.session, action_for(self.view, kind="decline", text="不愿回答"))
        view = review_input(session)
        self.assertEqual(view["questions"][0]["status"], "declined")
        session, _ = apply_action(session, action_for(view, identity="a2", text="不知道"))
        view = review_input(session)
        self.assertEqual(view["questions"][0]["resolution"], "unresolved")
        session, _ = apply_action(session, action_for(view, identity="c", kind="confirm", targets=("rule", "limit")))
        view = review_input(session)
        self.assertEqual(view["issues"], self.view["issues"])
        self.assertEqual(view["residuals"], self.view["residuals"])
        self.assertEqual(view["inspection"], self.view["inspection"])
        self.assertEqual(view["requirement_fidelity"], "not_checked")
        self.assertEqual(view["actions"][0]["provenance"]["text"], "不愿回答")
        self.assertFalse(view["actions"][1]["provenance"]["asserts_original_source"])
        with self.assertRaises(ContractError): apply_action(session, action_for(view, identity="empty", text=" "))

    def test_duplicate_action_id_is_idempotent_only_for_identical_payload(self):
        action = action_for(self.view)
        session, receipt = apply_action(self.session, action)
        session2, repeated = apply_action(session, action)
        self.assertEqual(session2, session)
        self.assertEqual(repeated["status"], "already_recorded")
        self.assertEqual(receipt["recorded_review_ref"], repeated["recorded_review_ref"])
        with self.assertRaises(ContractError): apply_action(session, replace(action, text="new answer"))

    def test_whole_candidate_confirmation_cannot_alias_a_legal_element_id(self):
        data = deepcopy(self.data)
        data["definition"]["entities"][0]["id"] = "$candidate"
        data["definition"]["constraints"][0]["context"] = "$candidate"
        data["traces"][0]["element"] = "$candidate"
        session = create_session(self.request, dumps(data).encode(), session_id="s")
        view = review_input(session)
        self.assertEqual(view["inspection"]["status"], "valid")
        session, _ = apply_action(session, action_for(view, kind="confirm", targets=("$candidate",)))
        view = review_input(session)
        session, _ = apply_action(session, action_for(view, identity="whole", kind="confirm", targets=("review:candidate",)))
        confirmations = review_input(session)["confirmations"]
        self.assertEqual(confirmations[0]["targets"], ["$candidate"])
        self.assertEqual(confirmations[1]["targets"], ["review:candidate"])
        with self.assertRaises(ContractError):
            apply_action(session, action_for(review_input(session), identity="bad", kind="confirm", targets=("review:flag",)))

    def test_edits_retain_removed_rules_residuals_and_logic_changes_as_proposals(self):
        edits = []
        removed = deepcopy(self.data); removed["definition"]["constraints"] = []; removed["definition"]["residuals"] = []
        removed["traces"] = [t for t in removed["traces"] if t["element"] not in ("rule", "limit")]
        removed["issues"] = []; edits.append((removed, "valid"))
        logic = deepcopy(self.data); logic["definition"]["constraints"][0]["assertion"]["op"] = "or"; edits.append((logic, "valid"))
        default = deepcopy(self.data); default["definition"]["entities"][0]["fields"][0]["default"] = True
        edits.append((default, "rejected"))
        session = self.session
        for i, (data, status) in enumerate(edits):
            view = review_input(session); raw = dumps(data).encode()
            session, receipt = apply_action(session, action_for(view, identity=f"edit{i}", kind="propose_edit",
                                                                text="用户明确改变需求", raw=raw))
            view = review_input(session); proposal = view["proposals"][-1]
            self.assertEqual(base64.b64decode(proposal["raw_base64"]), raw)
            self.assertEqual(proposal["inspection"]["status"], status)
            self.assertEqual(proposal["adoption"], "pending")
            self.assertEqual(view["candidate_ref"], self.view["candidate_ref"])
            self.assertEqual(view["issues"], self.view["issues"])
            self.assertIsNone(receipt["next_candidate_ref"])

    def test_rejected_original_can_still_be_reviewed(self):
        unsupported = deepcopy(self.data); unsupported["definition"]["constraints"][0]["assertion"]["op"] = "execute"
        for raw in (b'broken JSON\xff', dumps(unsupported).encode(), b'{"n":' + b'9' * 5000 + b'}'):
            with self.subTest(raw=raw[:20]):
                session = create_session(self.request, raw, session_id="invalid")
                view = review_input(session)
                self.assertEqual(view["inspection"]["status"], "rejected")
                self.assertEqual(base64.b64decode(view["candidate_base64"]), raw)
                self.assertTrue(view["inspection"]["diagnostics"])
                session, _ = apply_action(session, action_for(view))
                self.assertEqual(len(review_input(session)["actions"]), 1)

    def test_changed_source_and_tampered_chain_rejected(self):
        action = action_for(self.view)
        session, _ = apply_action(self.session, action)
        with self.assertRaises(ContractError): review_input(replace(session, actions=(replace(action, text="changed"), action)))
        with self.assertRaises(ContractError): review_input(replace(session, request=replace(self.request, text="changed")))
        self.assertEqual(review_ref(session).revision, "1")


if __name__ == "__main__": unittest.main()
