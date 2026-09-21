import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from threading import Barrier

from offline import demo, load_fixture
from modelspine_assurance import TOOL, VERSION, check
from modelspine_generation import construct
from modelspine_kernel import ModelKernel, applicability, impact
from modelspine_protocols import (
    AddElement, ChangeProposal, Confirm, ContractError, ElementRef, RemoveElement, Rename,
    SetDependencies, SetProperty, ref,
)


class KernelTests(unittest.TestCase):
    def setUp(self):
        self.meta, self.snapshot, self.plan = load_fixture()
        self.kernel = ModelKernel(self.snapshot, self.meta, self.plan, check, frozenset({'editor'}))

    def proposal(self, *operations, id='p'):
        return ChangeProposal('0.1', id, ref(self.kernel.snapshot()), operations, ())

    def decision(self, proposal, policy='satisfied-save'):
        return self.kernel.decide(proposal, check(self.kernel.preview(proposal).candidate,self.plan), 'editor', policy)

    def test_preview_rename_identity_and_frozen_snapshots(self):
        proposal = self.proposal(Rename('rename','order','Purchase'))
        preview = self.kernel.preview(proposal)
        self.assertEqual(self.kernel.snapshot(), self.snapshot)
        self.assertEqual(preview.candidate.elements[1].id, 'order')
        with self.assertRaises(FrozenInstanceError):
            preview.candidate.elements[1].name = 'leak'
        self.kernel.apply(proposal, self.decision(proposal), 'editor')
        self.assertEqual(self.kernel.snapshot().elements[1].name, 'Purchase')
        self.assertEqual(self.kernel.resolve(ElementRef(ref(self.snapshot),'order')).name, 'order')

    def test_qualified_reference_rejects_other_project_model_meta_or_hash(self):
        base = ref(self.snapshot)
        for changed in [replace(base,project_id='other'), replace(base,model_id='other'),
                        replace(base,metamodel=replace(base.metamodel,version='2')),
                        replace(base,content_hash='wrong')]:
            with self.subTest(changed=changed), self.assertRaises(ContractError):
                self.kernel.resolve(ElementRef(changed,'order'))

    def test_invalid_batch_leaves_no_partial_state(self):
        for tail in [Rename('rename','missing','X'), RemoveElement('remove_element','order'),
                     SetProperty('set_property','approval-policy','role',7)]:
            proposal = self.proposal(Rename('rename','weather','Climate'),tail)
            with self.subTest(tail=tail), self.assertRaises(ContractError):
                self.kernel.preview(proposal)
            self.assertEqual(self.kernel.snapshot(),self.snapshot)

    def test_add_remove_and_duplicate_id_are_atomic(self):
        added=replace(self.snapshot.elements[4],id='second-weather',name='Second weather')
        proposal=self.proposal(AddElement('add_element',added))
        self.kernel.apply(proposal,self.decision(proposal),'editor')
        self.assertEqual(self.kernel.resolve(ElementRef(ref(self.kernel.snapshot()),added.id)),added)
        duplicate=self.proposal(AddElement('add_element',added),id='duplicate')
        with self.assertRaises(ContractError):
            self.kernel.preview(duplicate)
        remove=self.proposal(RemoveElement('remove_element',added.id),id='remove')
        self.kernel.apply(remove,self.decision(remove),'editor')
        self.assertEqual(self.kernel.snapshot().elements,self.snapshot.elements)

    def test_failed_evidence_registration_does_not_change_records(self):
        current=check(self.snapshot,self.plan,('weather',))
        with self.assertRaises(ContractError):
            self.kernel.record_evidence(replace(current,binding=replace(current.binding,candidate_hash='wrong')))
        self.assertEqual(self.kernel.evidence_status(),())

    def test_notes_cannot_mutate_model(self):
        self.kernel.add_note('{"revision":99,"elements":[]}')
        with self.assertRaises(ContractError):
            self.kernel.add_note(lambda state: state.clear())
        self.assertEqual(self.kernel.snapshot(),self.snapshot)

    def test_confirmation_preserves_hypothesis_and_provenance(self):
        proposal = self.proposal(Confirm('confirm','order',False))
        self.kernel.apply(proposal,self.decision(proposal),'editor')
        proposal = self.proposal(Confirm('confirm','order',True), id='confirm-again')
        self.kernel.apply(proposal,self.decision(proposal),'editor')
        result = self.kernel.snapshot().elements[1]
        self.assertEqual(result.category,'hypothesis')
        self.assertEqual(result.sources,self.snapshot.elements[1].sources)

    def test_old_base_cannot_overwrite_and_retry_is_idempotent(self):
        first = self.proposal(Rename('rename','order','A'),id='a')
        second = self.proposal(Rename('rename','order','B'),id='b')
        d1,d2 = self.decision(first),self.decision(second)
        committed = self.kernel.apply(first,d1,'editor')
        with self.assertRaises(ContractError):
            self.kernel.apply(second,d2,'editor')
        self.assertEqual(self.kernel.apply(first,d1,'editor'),committed)
        with self.assertRaises(ContractError):
            self.kernel.apply(replace(first,operations=second.operations),d1,'editor')
        self.assertEqual(self.kernel.snapshot().revision,1)

    def test_two_concurrent_threads_exactly_one_commit(self):
        proposals = [self.proposal(Rename('rename','order',str(i)),id=str(i)) for i in range(2)]
        decisions = [self.decision(p) for p in proposals]
        barrier = Barrier(2)
        def submit(i):
            barrier.wait(timeout=5)
            try:
                self.kernel.apply(proposals[i],decisions[i],'editor')
                return 'committed'
            except ContractError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit,range(2)))
        self.assertCountEqual(results,['committed','conflict'])
        self.assertEqual(self.kernel.snapshot().revision,1)

    def test_different_candidate_scope_forgery_and_actor_rejected(self):
        p1 = self.proposal(Rename('rename','order','A'),id='a')
        p2 = self.proposal(Rename('rename','order','B'),id='b')
        decision = self.decision(p1)
        for p,d,a in [(p2,decision,'editor'),(p1,replace(decision,token='made-up'),'editor'),
                      (p1,replace(decision,policy='checked-save'),'editor'),(p1,decision,'intruder')]:
            with self.subTest(p=p,d=d,a=a), self.assertRaises(ContractError):
                self.kernel.apply(p,d,a)
        preview = self.kernel.preview(p1)
        report = check(preview.candidate,self.plan,('weather',))
        with self.assertRaises(ContractError):
            self.kernel.decide(p1,report,'editor')
        self.assertEqual(self.kernel.snapshot(),self.snapshot)

    def test_tampered_pass_report_cannot_authorize_illegal_candidate(self):
        proposal = self.proposal(SetProperty('set_property','approval-policy','threshold_minor',-1))
        report = check(self.kernel.preview(proposal).candidate,self.plan)
        forged = replace(report,outcomes=tuple(replace(o,status='satisfied',findings=()) for o in report.outcomes))
        with self.assertRaises(ContractError):
            self.kernel.decide(proposal,forged,'editor')
        with self.assertRaises(ContractError):
            self.kernel.decide(proposal,report,'editor')
        decision = self.kernel.decide(proposal,report,'editor','checked-save')
        commit = self.kernel.apply(proposal,decision,'editor')
        self.assertIn('amount-domain',commit.report.residual)
        self.assertEqual(commit.policy,'checked-save')

    def test_related_stale_unrelated_current_and_unknown_separate_from_report(self):
        records = {key:self.kernel.record_evidence(check(self.snapshot,self.plan,(key,)))
                   for key in ['approval-policy','weather','external-signal']}
        proposal = construct(self.snapshot,self.plan,'p','approval-policy','threshold_minor',200000)
        commit = self.kernel.apply(proposal,self.decision(proposal),'editor')
        statuses = {s.evidence_id:s.status for s in commit.evidence_status}
        self.assertEqual([statuses[records[k].id] for k in records],['stale','current','unknown'])
        self.assertTrue(records['approval-policy'].report.satisfied)
        self.assertIn('approve-command',commit.impact.affected)
        self.assertNotIn('weather',commit.impact.affected)
        self.assertIn('external-signal',commit.impact.unknown)

    def test_rule_tool_and_assumption_changes_invalidate_evidence(self):
        evidence = self.kernel.record_evidence(check(self.snapshot,self.plan,('weather',)))
        for plan,tool,version in [(replace(self.plan,rule_version='2'),TOOL,VERSION),
                                  (replace(self.plan,assumptions=('new',)),TOOL,VERSION),
                                  (self.plan,TOOL,'2')]:
            result = applicability(evidence,self.snapshot,plan,tool,version)
            self.assertEqual(result.status,'stale')

    def test_old_dependency_graph_is_used_after_removal(self):
        # Removing a dependency from a node deleted in the batch must not erase its old downstream impact.
        proposal = self.proposal(SetDependencies('set_dependencies','approve-command',(),True),
                                 RemoveElement('remove_element','approval-policy'))
        preview = self.kernel.preview(proposal)
        self.assertIn('approve-command',preview.impact.affected)
        self.assertIn('approval-policy',preview.impact.changed)
        # Direct graph probe isolates the changed predecessor from incidental node edits.
        after = replace(self.snapshot,elements=tuple(e for e in self.snapshot.elements if e.id!='approval-policy'))
        self.assertIn('approve-command',impact(self.snapshot,after).affected)

    def test_changed_dependency_fingerprint_invalidates_transitive_evidence(self):
        # A check on an approval command also depends on the policy even when its own field is unchanged.
        from modelspine_protocols import Obligation, Property
        plan = replace(self.plan,obligations=self.plan.obligations+(
            Obligation('command-role','1','equals','approve-command','permission',(Property('value','manager'),)),))
        kernel = ModelKernel(self.snapshot,self.meta,plan,check,frozenset({'editor'}))
        record = kernel.record_evidence(check(self.snapshot,plan,('approve-command',)))
        p = construct(self.snapshot,plan,'p','approval-policy','threshold_minor',200000)
        d = kernel.decide(p,check(kernel.preview(p).candidate,plan),'editor')
        commit = kernel.apply(p,d,'editor')
        self.assertEqual(commit.evidence_status[0].status,'stale')
        self.assertTrue(record.report.satisfied)

    def test_offline_chain_is_real_and_does_not_approve_business_order(self):
        result = demo()
        self.assertEqual(result['stored_revision_before_commit'],0)
        self.assertEqual(result['commit']['snapshot']['revision'],1)
        self.assertEqual(result['evidence_applicability']['weather']['status'],'current')
        self.assertEqual(result['unsupported_residual'],('runtime-approval',))
        self.assertEqual(result['repair_comparison']['status'],'repair_progress')


if __name__ == '__main__':
    unittest.main()
