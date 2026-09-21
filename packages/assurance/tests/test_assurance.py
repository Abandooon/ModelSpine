import unittest
from dataclasses import replace

from offline import load_fixture
from modelspine_assurance import check
from modelspine_protocols import ContractError, Obligation, Property


class AssuranceTests(unittest.TestCase):
    def setUp(self):
        self.meta,self.snapshot,self.plan=load_fixture()

    def test_unsupported_and_missing_targets_do_not_pass(self):
        for kind,target,status in [('arbitrary_temporal_logic','approval-policy','unknown'),
                                   ('equals','absent','error')]:
            obligation=Obligation('new','1',kind,target,'role',(Property('value','manager'),))
            report=check(self.snapshot,replace(self.plan,obligations=(obligation,)))
            self.assertEqual(report.outcomes[0].status,status)
            self.assertFalse(report.satisfied)
            self.assertEqual(report.residual,('new',))

    def test_malformed_supported_rule_is_error(self):
        obligation=replace(self.plan.obligations[0],parameters=(Property('min',5),Property('max',1)))
        report=check(self.snapshot,replace(self.plan,obligations=(obligation,)))
        self.assertEqual(report.outcomes[0].status,'error')

    def test_empty_checks_duplicate_obligations_and_empty_scope_rejected(self):
        for plan in [replace(self.plan,obligations=()),replace(self.plan,obligations=self.plan.obligations*2)]:
            with self.assertRaises(ContractError):
                check(self.snapshot,plan)
        with self.assertRaises(ContractError):
            check(self.snapshot,self.plan,())

    def test_report_pass_is_not_business_approval(self):
        report=check(self.snapshot,self.plan)
        self.assertTrue(report.satisfied)
        self.assertFalse(hasattr(report,'approved'))
        self.assertEqual(self.snapshot.revision,0)


if __name__=='__main__':
    unittest.main()
