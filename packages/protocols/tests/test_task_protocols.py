"""Task wire contracts and shared report boundaries, without task interpretation."""
import json
import unittest
from dataclasses import replace

from fixtures import load_fixture
from modelspine_protocols import (
    ArtifactRef, ContractError, EvidenceRef, Outcome, ReportBinding, TaskAssessment,
    TaskBinding, TaskContract, TaskStatement, ValidationReport, digest, dumps, loads,
    ref, select_scope, to_data, validate_artifact_ref, validate_report, validate_snapshot_ref,
)


class TaskProtocolTests(unittest.TestCase):
    def setUp(self):
        self.meta, self.snapshot, self.plan = load_fixture()
        self.task_ref = ArtifactRef('project', 'task', '1', digest('task bytes fixture'))
        self.source_ref = EvidenceRef(
            ArtifactRef('project', 'source', '1', digest('source bytes fixture')),
            'lines:1-1', 'task-author')
        self.statement = TaskStatement('goal', 'Keep the declared goal', 'intent', 'confirmed',
                                       True, (self.source_ref,), None)
        self.task = TaskContract('task-contract/0.1', 'task', '1', ref(self.snapshot),
            (self.statement,), self.plan, tuple(
                TaskBinding(o.id, o.version, ('goal',)) for o in self.plan.obligations))

    def report(self, scope=None, status='satisfied'):
        scope = select_scope(self.plan, scope)
        return ValidationReport(ReportBinding(digest(self.snapshot), digest(self.plan), scope,
            self.plan.assumptions, 'wire-fixture', '1'), tuple(
                Outcome(o.id, o.version, status, ()) for o in self.plan.obligations if o.target in scope))

    def test_task_contract_roundtrip_retains_bindings_and_explicit_absence(self):
        pending = replace(self.task, statements=(replace(self.statement, confirmation='unresolved',
            source_refs=(), pending_reason='Source still required'),), plan=None, bindings=())
        for task in (self.task, pending):
            with self.subTest(task=task):
                restored = loads(TaskContract, dumps(task))
                self.assertEqual(restored, task)
                self.assertEqual(digest(restored), digest(task))

    def test_assessment_roundtrip_keeps_readiness_separate_from_goal_result(self):
        assessed = TaskAssessment('task-assessment/0.1', self.task_ref, ref(self.snapshot),
            self.report(), 'unresolved', 'satisfied', ('goal',), ('Another goal remains unresolved',))
        not_checked = replace(assessed, candidate=None, report=None, goal_status='not_checked',
                              mapped_statements=())
        for assessment in (assessed, not_checked):
            with self.subTest(assessment=assessment):
                self.assertEqual(loads(TaskAssessment, dumps(assessment)), assessment)
        self.assertFalse(hasattr(assessed, 'commit'))

    def test_task_contract_rejects_unknown_versions_fields_and_wrong_nested_types(self):
        good = to_data(self.task)
        wrong = [dict(good, schema_version='task-contract/2'), dict(good, extra='ignored'),
                 {key: value for key, value in good.items() if key != 'plan'}]
        for field, value in [('category', 'goal'), ('confirmation', True), ('required', 1),
                             ('source_refs', None), ('pending_reason', False)]:
            wrong.append(dict(good, statements=[dict(good['statements'][0], **{field: value})]))
        source = dict(good['statements'][0]['source_refs'][0], extra='ignored')
        wrong.append(dict(good, statements=[dict(good['statements'][0], source_refs=[source])]))
        wrong.append(dict(good, bindings=[dict(good['bindings'][0], statement_ids=[True])]))
        for value in wrong:
            with self.subTest(value=value), self.assertRaises(ContractError) as caught:
                loads(TaskContract, json.dumps(value))
            self.assertEqual(caught.exception.code, 'invalid')

    def test_assessment_rejects_unknown_status_and_embedded_submission(self):
        assessment = TaskAssessment('task-assessment/0.1', self.task_ref, None, None,
            'unresolved', 'not_checked', (), ('No executable plan',))
        good = to_data(assessment)
        wrong = [dict(good, schema_version='task-assessment/2'), dict(good, goal_status='passed'),
                 dict(good, intent_status='confirmed'), dict(good, commit={}),
                 dict(good, unresolved=[False]),
                 {key: value for key, value in good.items() if key != 'candidate'}]
        for value in wrong:
            with self.subTest(value=value), self.assertRaises(ContractError) as caught:
                loads(TaskAssessment, json.dumps(value))
            self.assertEqual(caught.exception.code, 'invalid')

    def test_reference_validators_reject_incomplete_identity_and_invalid_hashes(self):
        self.assertEqual(validate_artifact_ref(self.task_ref), self.task_ref)
        snapshot_ref = ref(self.snapshot)
        self.assertEqual(validate_snapshot_ref(snapshot_ref), snapshot_ref)
        artifacts = [replace(self.task_ref, **{field: ''})
                     for field in ('project_id', 'artifact_id', 'revision')]
        artifacts += [replace(self.task_ref, content_hash=value) for value in ('short', 'z' * 64)]
        for reference in artifacts:
            with self.subTest(reference=reference), self.assertRaises(ContractError) as caught:
                validate_artifact_ref(reference)
            self.assertEqual(caught.exception.code, 'invalid')
        snapshots = [replace(snapshot_ref, project_id=''), replace(snapshot_ref, model_id=''),
                     replace(snapshot_ref, revision=-1), replace(snapshot_ref, revision=True),
                     replace(snapshot_ref, metamodel=replace(snapshot_ref.metamodel, id='')),
                     replace(snapshot_ref, metamodel=replace(snapshot_ref.metamodel, version='')),
                     replace(snapshot_ref, metamodel_hash='wrong'),
                     replace(snapshot_ref, content_hash='A' * 64)]
        for reference in snapshots:
            with self.subTest(reference=reference), self.assertRaises(ContractError) as caught:
                validate_snapshot_ref(reference)
            self.assertEqual(caught.exception.code, 'invalid')

    def test_scope_is_selected_by_the_caller_and_rejects_invalid_subsets(self):
        full = tuple(sorted({o.target for o in self.plan.obligations}))
        self.assertEqual(select_scope(self.plan), full)
        self.assertEqual(select_scope(self.plan, tuple(reversed(full))), full)
        for scope in ((), (full[0], full[0]), ('missing',), (False,), list(full)):
            with self.subTest(scope=scope), self.assertRaises(ContractError) as caught:
                select_scope(self.plan, scope)
            self.assertEqual(caught.exception.code, 'invalid')

    def test_report_validation_preserves_unknown_instead_of_certifying_truth(self):
        report = self.report(status='unknown')
        result = validate_report(report, self.snapshot, self.plan, select_scope(self.plan))
        self.assertEqual(result, report)
        self.assertFalse(result.satisfied)
        self.assertEqual(result.residual, tuple(o.id for o in self.plan.obligations))

    def test_report_validation_rejects_wrong_candidate_plan_context_and_tool(self):
        good = self.report()
        changes = [dict(candidate_hash='0' * 64), dict(plan_hash='0' * 64),
                   dict(assumptions=('different',)), dict(tool=''), dict(tool_version='')]
        for change in changes:
            report = replace(good, binding=replace(good.binding, **change))
            with self.subTest(change=change), self.assertRaises(ContractError) as caught:
                validate_report(report, self.snapshot, self.plan, select_scope(self.plan))
            self.assertEqual(caught.exception.code, 'conflict')

    def test_report_validation_requires_exact_obligation_identity_version_and_coverage(self):
        good = self.report()
        outcomes = [(), good.outcomes[:-1], good.outcomes + good.outcomes[:1],
                    (replace(good.outcomes[0], obligation_id='other'), *good.outcomes[1:]),
                    (replace(good.outcomes[0], obligation_version='other'), *good.outcomes[1:])]
        for changed in outcomes:
            with self.subTest(changed=changed), self.assertRaises(ContractError) as caught:
                validate_report(replace(good, outcomes=changed), self.snapshot, self.plan,
                                select_scope(self.plan))
            self.assertEqual(caught.exception.code, 'conflict')
        with self.assertRaises(ContractError) as caught:
            validate_report({'binding': 'bad'}, self.snapshot, self.plan, select_scope(self.plan))
        self.assertEqual(caught.exception.code, 'invalid')

    def test_report_cannot_use_its_own_subset_as_complete_expected_scope(self):
        scope = (select_scope(self.plan)[0],)
        report = self.report(scope)
        self.assertEqual(validate_report(report, self.snapshot, self.plan, scope), report)
        with self.assertRaises(ContractError) as caught:
            validate_report(report, self.snapshot, self.plan, select_scope(self.plan))
        self.assertEqual(caught.exception.code, 'conflict')
        with self.assertRaises(ContractError) as caught:
            validate_report(report, self.snapshot, self.plan, None)
        self.assertEqual(caught.exception.code, 'invalid')


if __name__ == '__main__':
    unittest.main()
