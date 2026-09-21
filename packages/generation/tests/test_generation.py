import unittest
from dataclasses import replace

from offline import load_fixture
from modelspine_assurance import check
from modelspine_generation import compare_reports,construct,plan
from modelspine_kernel import ModelKernel
from modelspine_protocols import (
    ChangeProposal, ContractError, Obligation, Outcome, ReportBinding, SetProperty,
    ValidationReport, ref,
)


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.meta,self.snapshot,self.checks=load_fixture()

    def test_constructor_excludes_illegal_values_terminal_check_catches_bypass(self):
        for field,value in [('threshold_minor',-1),('threshold_minor',True),('role','anyone'),
                            ('invalidate_on_change',False)]:
            with self.subTest(field=field,value=value), self.assertRaises(ContractError):
                construct(self.snapshot,self.checks,'bad','approval-policy',field,value)
        kernel=ModelKernel(self.snapshot,self.meta,self.checks,check,frozenset({'editor'}))
        illegal=ChangeProposal('0.1','illegal',ref(self.snapshot),
            (SetProperty('set_property','approval-policy','threshold_minor',-1),),())
        report=check(kernel.preview(illegal).candidate,self.checks)
        self.assertEqual(report.outcomes[0].status,'violated')

    def test_boundary_values_and_unhandled_obligations_are_explicit(self):
        for value in [0,100000000]:
            construct(self.snapshot,self.checks,'boundary','approval-policy','threshold_minor',value)
        expanded=replace(self.checks,obligations=self.checks.obligations+(
            Obligation('open','1','runtime_trace','approval-policy','role',()),))
        self.assertEqual(plan(expanded).residual,('open',))
        self.assertEqual(plan(expanded).controls[-1].stage,'terminal-only')
        self.assertIn('open',check(self.snapshot,expanded).residual)

    def report(self, domain, states):
        return ValidationReport(ReportBinding('candidate','fixed-plan',(domain,),('fixture-only',),'fixture','1'),
            tuple(Outcome(f'{domain}:{i}','1',status,tuple(findings)) for i,status,findings in states))

    def test_p0_mechanism_rejects_new_errors_despite_lower_count(self):
        for domain in ['AUTOSAR-report-fixture','order-report-fixture']:
            before=self.report(domain,[(1,'violated',['a','b']),(2,'satisfied',[])])
            after=self.report(domain,[(1,'satisfied',[]),(2,'violated',['c'])])
            self.assertEqual(compare_reports(before,after).status,'rejected')

    def test_p0_mechanism_rejects_coverage_loss_and_becoming_unknown(self):
        for domain in ['AUTOSAR-report-fixture','order-report-fixture']:
            before=self.report(domain,[(1,'violated',['a']),(2,'satisfied',[])])
            for after in [self.report(domain,[(2,'satisfied',[])]),
                          self.report(domain,[(1,'unknown',[]),(2,'satisfied',[])]),
                          self.report(domain,[(1,'not_applicable',[]),(2,'satisfied',[])])]:
                self.assertEqual(compare_reports(before,after).status,'rejected')

    def test_p0_strict_improvement_still_failure_is_only_progress(self):
        for domain in ['AUTOSAR-report-fixture','order-report-fixture']:
            before=self.report(domain,[(1,'violated',['a']),(2,'violated',['b'])])
            after=self.report(domain,[(1,'satisfied',[]),(2,'violated',['b'])])
            decision=compare_reports(before,after)
            self.assertEqual(decision.status,'repair_progress')
            self.assertEqual(decision.remaining,(f'{domain}:2',))
            self.assertFalse(after.satisfied)
            self.assertEqual(compare_reports(before,before).status,'rejected')

    def test_changed_rule_scope_or_tool_is_incomparable(self):
        before=self.report('order',[(1,'violated',['a'])])
        after=self.report('order',[(1,'satisfied',[])])
        for change in [{'plan_hash':'different'},{'scope':('other',)},{'tool_version':'2'}, {'assumptions':()}]:
            self.assertEqual(compare_reports(before,replace(after,binding=replace(after.binding,**change))).status,'rejected')

    def test_error_relabelled_unknown_is_not_progress(self):
        before=self.report('order',[(1,'error',['checker-unavailable'])])
        after=self.report('order',[(1,'unknown',[])])
        self.assertEqual(compare_reports(before,after).status,'rejected')


if __name__=='__main__':
    unittest.main()
