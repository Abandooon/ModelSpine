"""Finite graph and automaton consumers exercise the same public model boundary."""
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from boundary_examples import run_profile
from finite_models import check_automaton, check_structure
from fixtures import load_case
from modelspine_kernel import ModelKernel
from modelspine_protocols import (
    AddElement, ChangeProposal, ContractError, Element, Obligation, Property,
    Rename, SetDependencies, SetProperty, ref,
)

PROFILES = ("structural-graph", "finite-automaton")
CASES = Path(__file__).resolve().parents[1] / "domain-packs"


class FoundationBoundaryTests(unittest.TestCase):
    def case(self, profile):
        meta, snapshot, plan = load_case(CASES / profile)
        checker = check_structure if profile == "structural-graph" else check_automaton
        kernel = ModelKernel(snapshot, meta, plan, checker, frozenset({"editor"}))
        return kernel, checker

    def proposal(self, kernel, *operations, proposal_id="change"):
        return ChangeProposal("0.1", proposal_id, ref(kernel.snapshot()), operations, ())

    def assert_uncommitted(self, kernel, original):
        self.assertEqual(kernel.snapshot(), original)
        with self.assertRaises(ContractError) as caught:
            kernel.snapshot(1)
        self.assertEqual(caught.exception.code, "not_found")

    def assert_rejected(self, profile, operations, status, finding):
        kernel, checker = self.case(profile)
        original = kernel.snapshot()
        proposal = self.proposal(kernel, *operations)
        report = checker(kernel.preview(proposal).candidate, kernel.plan)
        self.assertIn(status, {outcome.status for outcome in report.outcomes})
        self.assertTrue(any(finding in item for outcome in report.outcomes for item in outcome.findings))
        with self.assertRaises(ContractError):
            kernel.decide(proposal, report, "editor")
        self.assert_uncommitted(kernel, original)

    def test_both_configuration_consumers_load_preview_check_and_commit(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                output = run_profile(profile)
                self.assertEqual(output["commit"]["snapshot"]["revision"], 1)
                self.assertTrue(all(o["status"] == "satisfied" for o in output["commit"]["report"]["outcomes"]))
                self.assertEqual(output["initial_evidence_applicability"][0]["status"], "unknown")
                self.assertEqual(output["commit"]["evidence_status"][0]["status"], "stale")

    def test_structural_semantics_reject_cycle_dangling_and_wrong_kind_endpoints(self):
        variants = [
            ((SetProperty("set_property", "edge-bc", "target", "node-a"),
              SetDependencies("set_dependencies", "edge-bc", ("node-b", "node-a"), True)), "directed_cycle"),
            ((SetProperty("set_property", "edge-bc", "target", "absent"),), "invalid_endpoint"),
            ((SetProperty("set_property", "edge-bc", "target", "graph"),), "invalid_endpoint"),
        ]
        for operations, finding in variants:
            with self.subTest(finding=finding, operations=operations):
                self.assert_rejected("structural-graph", operations, "violated", finding)

    def test_automaton_rejects_nondeterminism_and_dangling_endpoints(self):
        self.assert_rejected("finite-automaton", (
            SetProperty("set_property", "step-b", "source", "s0"),
            SetProperty("set_property", "step-b", "symbol", "a"),
            SetDependencies("set_dependencies", "step-b", ("s0", "s2"), True),
        ), "violated", "nondeterministic")
        self.assert_rejected("finite-automaton", (
            SetProperty("set_property", "step-b", "target", "absent"),
        ), "violated", "invalid_endpoint")

    def test_trace_is_executed_and_rejected_when_transition_or_acceptance_changes(self):
        variants = [
            ((SetProperty("set_property", "step-b", "symbol", "a"),), "trace_blocked"),
            ((SetProperty("set_property", "machine", "trace", "a"),), "trace_not_accepted"),
            ((SetProperty("set_property", "s2", "accepting", False),), "trace_not_accepted"),
            ((SetProperty("set_property", "machine", "trace", "ac"),), "trace_outside_alphabet"),
        ]
        for operations, finding in variants:
            with self.subTest(finding=finding, operations=operations):
                self.assert_rejected("finite-automaton", operations, "violated", finding)

    def test_empty_trace_uses_initial_state_acceptance_and_epsilon_is_not_supported(self):
        kernel, checker = self.case("finite-automaton")
        proposal = self.proposal(kernel,
            SetProperty("set_property", "machine", "trace", ""),
            SetProperty("set_property", "s0", "accepting", True))
        report = checker(kernel.preview(proposal).candidate, kernel.plan)
        self.assertTrue(report.satisfied)
        kernel.apply(proposal, kernel.decide(proposal, report, "editor"), "editor")
        self.assert_rejected("finite-automaton", (
            SetProperty("set_property", "step-b", "symbol", ""),
        ), "violated", "invalid_finite_symbol")

    def test_unicode_codepoints_work_but_multi_codepoint_tokens_do_not(self):
        kernel, checker = self.case("finite-automaton")
        operations = (
            SetProperty("set_property", "machine", "alphabet", "甲乙"),
            SetProperty("set_property", "machine", "trace", "甲乙"),
            SetProperty("set_property", "step-a", "symbol", "甲"),
            SetProperty("set_property", "step-b", "symbol", "乙"),
        )
        proposal = self.proposal(kernel, *operations)
        report = checker(kernel.preview(proposal).candidate, kernel.plan)
        self.assertTrue(report.satisfied)
        kernel.apply(proposal, kernel.decide(proposal, report, "editor"), "editor")
        self.assert_rejected("finite-automaton", operations[:-1] + (
            SetProperty("set_property", "step-b", "symbol", "甲乙"),
        ), "violated", "invalid_finite_symbol")

    def test_unknown_kind_and_missing_target_are_distinct_and_cannot_authorize_save(self):
        for profile in PROFILES:
            meta, snapshot, plan = load_case(CASES / profile)
            checker = check_structure if profile == "structural-graph" else check_automaton
            for target, expected in [(plan.obligations[0].target, "unknown"), ("missing", "error")]:
                with self.subTest(profile=profile, target=target):
                    expanded = replace(plan, obligations=plan.obligations + (
                        Obligation("unimplemented", "1", "temporal_logic", target, "future", ()),))
                    kernel = ModelKernel(snapshot, meta, expanded, checker, frozenset({"editor"}))
                    proposal = self.proposal(kernel, Rename("rename", plan.obligations[0].target, "renamed"))
                    report = checker(kernel.preview(proposal).candidate, expanded)
                    self.assertEqual(report.outcomes[-1].status, expected)
                    self.assertIn("unimplemented", report.residual)
                    with self.assertRaises(ContractError):
                        kernel.decide(proposal, report, "editor")
                    self.assert_uncommitted(kernel, snapshot)

    def test_complete_membership_claim_is_error_for_both_whole_model_checkers(self):
        for profile in PROFILES:
            kernel, _ = self.case(profile)
            root = kernel.snapshot().elements[0]
            with self.subTest(profile=profile):
                self.assert_rejected(profile, (
                    SetDependencies("set_dependencies", root.id, root.dependencies, True),
                ), "error", "membership_completeness_not_supported")

    def test_known_reads_must_be_declared_even_when_membership_is_incomplete(self):
        for profile in PROFILES:
            kernel, _ = self.case(profile)
            root = kernel.snapshot().elements[0]
            with self.subTest(profile=profile):
                self.assert_rejected(profile, (
                    SetDependencies("set_dependencies", root.id, root.dependencies[:-1], False),
                ), "error", "member_read_dependencies_missing")
        self.assert_rejected("structural-graph", (
            SetDependencies("set_dependencies", "edge-bc", ("node-b",), True),
        ), "error", "endpoint_read_dependencies_missing")

    def test_nested_relations_are_rejected_instead_of_silently_ignored(self):
        nested = (
            ("structural-graph", Element("hidden-loop", "edge", "hidden-loop", "node-a", (
                Property("source", "node-a"), Property("target", "node-a")),
                ("node-a",), True, "hypothesis", True, ())),
            ("finite-automaton", Element("hidden-step", "transition", "hidden-step", "s0", (
                Property("source", "s0"), Property("target", "s2"), Property("symbol", "a")),
                ("s0", "s2"), True, "hypothesis", True, ())),
        )
        for profile, element in nested:
            with self.subTest(profile=profile):
                self.assert_rejected(profile, (AddElement("add_element", element),),
                                     "violated", "not_flat_membership")

    def test_an_independent_root_does_not_become_a_member_of_the_checked_root(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                kernel, checker = self.case(profile)
                if profile == "structural-graph":
                    root_kind, root_props = "graph", (Property("root", "other-member"),)
                    member_kind, member_props = "node", (Property("label", "separate"),)
                else:
                    root_kind = "machine"
                    root_props = (Property("initial", "other-member"), Property("alphabet", "x"), Property("trace", ""))
                    member_kind, member_props = "state", (Property("accepting", True),)
                separate = Element("other-root", root_kind, "other-root", None, root_props,
                                   ("other-member",), False, "hypothesis", True, ())
                member = Element("other-member", member_kind, "other-member", "other-root", member_props,
                                 (), True, "hypothesis", True, ())
                proposal = self.proposal(kernel, AddElement("add_element", separate), AddElement("add_element", member))
                report = checker(kernel.preview(proposal).candidate, kernel.plan)
                self.assertTrue(report.satisfied)
                self.assertEqual(report.binding.scope, (kernel.snapshot().elements[0].id,))
                kernel.apply(proposal, kernel.decide(proposal, report, "editor"), "editor")

    def test_direct_checker_reports_parent_cycles_without_looping(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                kernel, checker = self.case(profile)
                snapshot = kernel.snapshot()
                members = list(snapshot.elements)
                members[1] = replace(members[1], parent=members[2].id)
                members[2] = replace(members[2], parent=members[1].id)
                report = checker(replace(snapshot, elements=tuple(members)), kernel.plan)
                self.assertTrue(all(outcome.status == "error" for outcome in report.outcomes))
                self.assertTrue(any("parent_cycle" in item for outcome in report.outcomes for item in outcome.findings))

    def test_new_consumers_preserve_permission_version_and_report_boundaries(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                kernel, checker = self.case(profile)
                original = kernel.snapshot()
                root = original.elements[0]
                proposal = self.proposal(kernel, Rename("rename", root.id, "renamed"))
                report = checker(kernel.preview(proposal).candidate, kernel.plan)
                with self.assertRaises(ContractError) as caught:
                    kernel.decide(proposal, report, "outsider")
                self.assertEqual(caught.exception.code, "forbidden")
                self.assert_uncommitted(kernel, original)
                wrong = replace(report, binding=replace(report.binding, candidate_hash="0" * 64))
                with self.assertRaises(ContractError) as caught:
                    kernel.decide(proposal, wrong, "editor")
                self.assertEqual(caught.exception.code, "conflict")
                self.assert_uncommitted(kernel, original)
                kernel.apply(proposal, kernel.decide(proposal, report, "editor"), "editor")
                committed = kernel.snapshot()
                with self.assertRaises(ContractError) as caught:
                    kernel.preview(replace(proposal, proposal_id="old-base"))
                self.assertEqual(caught.exception.code, "conflict")
                self.assertEqual(kernel.snapshot(), committed)

    def test_explicit_loader_does_not_replace_missing_configuration(self):
        with TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError):
                load_case(Path(folder))


if __name__ == "__main__":
    unittest.main()
