import hashlib
import unittest
from dataclasses import replace

from fixtures import load_fixture
from modelspine_assurance import check
from modelspine_assurance.tasks import prepare_task, assess_task
from modelspine_protocols import (
    ArtifactRef, ContractError, EvidenceRef, TaskBinding, TaskContract, TaskStatement,
    dumps, ref, Property,
)


class TaskAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.meta, self.snapshot, self.plan = load_fixture()
        self.source = b"Author confirms the declared field constraints.\nA pending extension.\n"
        self.source_ref = ArtifactRef(self.snapshot.project_id, "source", "1",
                                      hashlib.sha256(self.source).hexdigest())
        statement = TaskStatement("intent", "Preserve declared constraints", "intent", "confirmed", True,
                                  (EvidenceRef(self.source_ref, "lines:1-1", "task-author"),), None)
        self.contract = TaskContract("task-contract/0.1", "task", "1", ref(self.snapshot),
                                     (statement,), self.plan,
                                     tuple(TaskBinding(o.id, o.version, ("intent",)) for o in self.plan.obligations))

    def prepare(self, contract=None):
        contract = self.contract if contract is None else contract
        raw = dumps(contract).encode()
        expected = ArtifactRef(self.snapshot.project_id, contract.id, contract.version, hashlib.sha256(raw).hexdigest())
        return prepare_task(raw, expected, {self.source_ref: self.source})

    def test_ready_means_declared_mapped_intent_only(self):
        prepared = self.prepare()
        assessment = assess_task(prepared, self.snapshot, check)
        self.assertEqual((assessment.intent_status, assessment.goal_status), ("ready", "satisfied"))
        self.assertEqual(assessment.mapped_statements, ("intent",))
        self.assertEqual(assessment.candidate, ref(self.snapshot))

    def test_raw_bytes_and_external_identity_are_both_pinned(self):
        prepared = self.prepare()
        raw = dumps(self.contract).encode()
        for changed, expected in ((raw+b"\n", prepared.task_ref),
                                  (raw, replace(prepared.task_ref, revision="2")),
                                  (raw, replace(prepared.task_ref, artifact_id="other"))):
            with self.subTest(expected=expected), self.assertRaises(ContractError):
                prepare_task(changed, expected, {self.source_ref: self.source})

    def test_missing_changed_or_unlocatable_source_is_error(self):
        raw, expected = dumps(self.contract).encode(), self.prepare().task_ref
        for sources in ({}, {self.source_ref: self.source+b"changed"}):
            with self.assertRaises(ContractError):
                prepare_task(raw, expected, sources)
        for locator in ("lines:0-1", "lines:2-1", "lines:1-3", "characters:1-3"):
            evidence = replace(self.contract.statements[0].source_refs[0], locator=locator)
            statement = replace(self.contract.statements[0], source_refs=(evidence,))
            with self.subTest(locator=locator), self.assertRaises(ContractError):
                self.prepare(replace(self.contract, statements=(statement,)))

    def test_invalid_json_and_utf8_remain_errors(self):
        for raw in (b'{}', b'{"id":"a","id":"b"}', b'\xff'):
            expected = replace(self.prepare().task_ref, content_hash=hashlib.sha256(raw).hexdigest())
            with self.assertRaises(ContractError):
                prepare_task(raw, expected, {})

    def test_required_unresolved_conflicted_fact_and_hypothesis_never_become_ready(self):
        statement = self.contract.statements[0]
        for modified in (replace(statement, confirmation="unresolved", pending_reason="author response pending"),
                         replace(statement, confirmation="conflicted", pending_reason="incompatible statements"),
                         replace(statement, category="fact"), replace(statement, category="hypothesis"),
                         replace(statement, source_refs=(), pending_reason="source pending")):
            with self.subTest(statement=modified):
                assessment = assess_task(self.prepare(replace(self.contract, statements=(modified,))), self.snapshot, check)
                self.assertEqual(assessment.intent_status, "unresolved")
                self.assertEqual(assessment.goal_status, "satisfied")
                self.assertTrue(assessment.unresolved)

    def test_partial_mapping_preserves_known_report_and_unresolved_goal(self):
        pending = replace(self.contract.statements[0], id="unmapped")
        prepared = self.prepare(replace(self.contract, statements=self.contract.statements+(pending,)))
        assessment = assess_task(prepared, self.snapshot, check)
        self.assertEqual((assessment.intent_status, assessment.goal_status), ("unresolved", "satisfied"))
        self.assertIn("unmapped", assessment.unresolved[0])

    def test_no_plan_is_not_an_empty_pass(self):
        prepared = self.prepare(replace(self.contract, plan=None, bindings=()))
        def forbidden(*args):
            self.fail("no-plan task called checker")
        assessment = assess_task(prepared, None, forbidden)
        self.assertEqual((assessment.intent_status, assessment.goal_status), ("unresolved", "not_checked"))
        self.assertIsNone(assessment.report)
        self.assertIsNone(assessment.candidate)
        with self.assertRaises(ContractError):
            assess_task(prepared, self.snapshot, forbidden)

    def test_empty_required_set_and_missing_reason_do_not_vacuously_pass(self):
        prepared = self.prepare(replace(self.contract, statements=(replace(self.contract.statements[0], required=False),)))
        self.assertEqual(assess_task(prepared, self.snapshot, check).intent_status, "unresolved")
        with self.assertRaises(ContractError):
            self.prepare(replace(self.contract, statements=(replace(self.contract.statements[0], source_refs=()),)))

    def test_mapping_errors_reject_duplicates_dangling_and_wrong_versions(self):
        bindings = self.contract.bindings
        variants = (bindings[:-1], bindings+(bindings[0],),
                    (replace(bindings[0], statement_ids=("missing",)),)+bindings[1:],
                    (replace(bindings[0], obligation_version="new"),)+bindings[1:],
                    (replace(bindings[0], statement_ids=()),)+bindings[1:])
        for variant in variants:
            with self.subTest(bindings=variant), self.assertRaises(ContractError):
                self.prepare(replace(self.contract, bindings=variant))
        with self.assertRaises(ContractError):
            self.prepare(replace(self.contract, statements=self.contract.statements*2))

    def test_candidate_plan_scope_and_report_crossbinding_are_rejected(self):
        prepared = self.prepare()
        for snapshot in (replace(self.snapshot, model_id="other"), replace(self.snapshot, metamodel_hash="f"*64),
                         replace(self.snapshot, metamodel=replace(self.snapshot.metamodel, version="new")),
                         replace(self.snapshot, elements=tuple(replace(e, name="Changed") for e in self.snapshot.elements))):
            with self.subTest(snapshot=snapshot), self.assertRaises(ContractError):
                assess_task(prepared, snapshot, check)
        with self.assertRaises(ContractError):
            assess_task(replace(prepared, contract=replace(self.contract, plan=replace(self.plan, version="2"))), self.snapshot, check)
        report = check(self.snapshot, self.plan)
        bad_reports = (replace(report, outcomes=report.outcomes[:-1]),
                       replace(report, binding=replace(report.binding, plan_hash="f"*64)),
                       replace(report, binding=replace(report.binding, candidate_hash="f"*64)),
                       replace(report, binding=replace(report.binding, scope=("unexpected",))))
        for bad in bad_reports:
            with self.subTest(report=bad), self.assertRaises(ContractError):
                assess_task(prepared, self.snapshot, lambda *_: bad)

    def test_unknown_and_checker_exception_are_not_replaced(self):
        obligation = replace(self.plan.obligations[0], kind="future-task-rule", parameters=())
        contract = replace(self.contract, plan=replace(self.plan, obligations=(obligation,)),
                           bindings=(self.contract.bindings[0],))
        assessment = assess_task(self.prepare(contract), self.snapshot, check)
        self.assertEqual(assessment.goal_status, "unknown")
        def broken(*args):
            raise RuntimeError("backend failure")
        with self.assertRaisesRegex(RuntimeError, "backend failure"):
            assess_task(self.prepare(), self.snapshot, broken)


if __name__ == "__main__":
    unittest.main()
