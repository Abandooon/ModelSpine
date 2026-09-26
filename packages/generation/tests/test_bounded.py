"""Bounded search behavior with an explicitly trusted, small preview/check host."""
import unittest
from dataclasses import replace

from modelspine_generation.bounded import (
    CandidateEvaluation, ConstructionDecision, EditOption, search,
)
from modelspine_protocols import (
    ArtifactRef, ChangeProposal, CheckPlan, ContractError, Element, EvidenceRef,
    FieldSpec, GenerationControl, GenerationPlan, KindSpec, Metamodel, MetamodelRef,
    Obligation, Outcome, Property, ReportBinding, SetProperty, Snapshot,
    ValidationReport, digest, ref, to_data,
)


class BoundedConstructionTests(unittest.TestCase):
    def setUp(self):
        self.meta = Metamodel(MetamodelRef("finite-value", "1"),
                              (KindSpec("Value", (FieldSpec("value", "integer"),)),))
        self.snapshot = Snapshot("project", "model", 0, self.meta.ref, digest(self.meta),
                                 (Element("value", "Value", "value", None,
                                          (Property("value", -1),), (), True,
                                          "hypothesis", False, ()),))
        self.task = ArtifactRef("project", "task", "1", digest({"task": "fixed goal"}))
        self.checks = CheckPlan("checks", "1", "rules-1", ("finite-fixture",),
                                (Obligation("domain", "1", "domain", "value", "value", ()),
                                 Obligation("goal", "1", "goal", "value", "value", ())))
        self.plan = GenerationPlan(digest(self.checks), (
            GenerationControl("domain", "1", "finite domain", "construction", "test-domain", "terminal check"),
            GenerationControl("goal", "1", "fixed goal", "terminal-only", "test-goal", "terminal check")),
            ("goal",))
        self.options = tuple(EditOption(f"option-{i}", "value", (Property("value", i),)) for i in range(4))
        self.control_calls, self.build_calls, self.evaluate_calls = [], [], []
        self.decisions = {0: "exclude", 1: "allow", 2: "allow", 3: "allow"}
        self.outcomes = {0: ("violated", "violated"), 1: ("satisfied", "violated"),
                         2: ("satisfied", "satisfied"), 3: ("satisfied", "satisfied")}

    def control(self, option):
        self.control_calls.append(option)
        return ConstructionDecision(digest(option), self.decisions[option.values[0].value], "explicit fixture control")

    def build(self, option):
        self.build_calls.append(option)
        return ChangeProposal("0.1", option.id, ref(self.snapshot),
                              (SetProperty("set_property", option.target, "value", option.values[0].value),), ())

    def evaluate(self, proposal):
        self.evaluate_calls.append(proposal)
        value = proposal.operations[0].value
        candidate = replace(self.snapshot, revision=1,
                            elements=(replace(self.snapshot.elements[0], properties=(Property("value", value),)),))
        statuses = self.outcomes[value]
        report = ValidationReport(
            ReportBinding(digest(candidate), digest(self.checks), ("value",), self.checks.assumptions, "test-checker", "1"),
            tuple(Outcome(obligation.id, obligation.version, status, () if status == "satisfied" else (status,))
                  for obligation, status in zip(self.checks.obligations, statuses)))
        return CandidateEvaluation(candidate, report)

    def run_search(self, **overrides):
        arguments = dict(snapshot=self.snapshot, task_ref=self.task, check_plan=self.checks,
                         construction_plan=self.plan, options=self.options, max_options=4,
                         control=self.control, build=self.build, evaluate=self.evaluate)
        arguments.update(overrides)
        return search(**arguments)

    def test_first_full_success_retains_failed_work_without_committing_or_visiting_later_options(self):
        result = self.run_search()
        self.assertEqual((result.status, result.reason), ("candidate_found", "all_terminal_obligations_satisfied"))
        self.assertEqual(result.task_ref, self.task)
        self.assertEqual(result.base, ref(self.snapshot))
        self.assertEqual(result.plan, self.plan)
        self.assertEqual(tuple(step.option.id for step in result.steps), ("option-0", "option-1", "option-2"))
        self.assertIsNone(result.steps[0].proposal)
        self.assertIsNone(result.steps[0].evaluation)
        self.assertEqual(tuple(o.status for o in result.steps[1].evaluation.report.outcomes), ("satisfied", "violated"))
        self.assertEqual(result.proposal, result.steps[2].proposal)
        self.assertTrue(result.steps[2].evaluation.report.satisfied)
        self.assertEqual([o.id for o in self.control_calls], ["option-0", "option-1", "option-2"])
        self.assertEqual([o.id for o in self.build_calls], ["option-1", "option-2"])
        self.assertEqual([p.proposal_id for p in self.evaluate_calls], ["option-1", "option-2"])
        self.assertEqual(self.snapshot.revision, 0)
        self.assertEqual(self.snapshot.elements[0].properties[0].value, -1)
        self.assertFalse(hasattr(result, "commit"))

    def test_given_order_is_preserved_instead_of_sorted_or_ranked(self):
        result = self.run_search(options=(self.options[3], self.options[2], self.options[1]))
        self.assertEqual(result.proposal.proposal_id, "option-3")
        self.assertEqual(tuple(step.option.id for step in result.steps), ("option-3",))

    def test_budgets_one_two_three_include_exclusions_and_stop_exactly(self):
        for budget, status, builds in ((1, "budget_exhausted", 0), (2, "budget_exhausted", 1),
                                      (3, "candidate_found", 2)):
            with self.subTest(budget=budget):
                self.control_calls.clear()
                self.build_calls.clear()
                self.evaluate_calls.clear()
                result = self.run_search(max_options=budget)
                self.assertEqual(result.status, status)
                self.assertEqual(len(result.steps), budget)
                self.assertEqual(len(self.control_calls), budget)
                self.assertEqual((len(self.build_calls), len(self.evaluate_calls)), (builds, builds))
                if status == "budget_exhausted":
                    self.assertEqual(result.reason, "option_budget_exhausted")
                    self.assertIsNone(result.proposal)

    def test_zero_budget_and_empty_space_have_distinct_outcomes_without_callbacks(self):
        for options, expected in ((self.options, "budget_exhausted"), ((), "exhausted")):
            with self.subTest(expected=expected):
                result = self.run_search(options=options, max_options=0)
                self.assertEqual(result.status, expected)
                self.assertEqual(result.steps, ())
                self.assertIsNone(result.proposal)
        self.assertEqual((self.control_calls, self.build_calls, self.evaluate_calls), ([], [], []))

    def test_complete_space_with_only_violations_is_exhausted_at_exact_budget(self):
        result = self.run_search(options=self.options[:2], max_options=2)
        self.assertEqual((result.status, result.reason), ("exhausted", "option_space_exhausted"))
        self.assertEqual(len(result.steps), 2)
        self.assertIsNone(result.proposal)
        self.assertEqual(len(self.evaluate_calls), 1)
        self.assertEqual(result.steps[1].evaluation.report.residual, ("goal",))

    def test_no_change_is_recorded_and_consumes_budget_without_constructing(self):
        self.decisions[0] = "no_change"
        result = self.run_search(max_options=1)
        self.assertEqual(result.status, "budget_exhausted")
        self.assertEqual(result.steps[0].decision.status, "no_change")
        self.assertIsNone(result.steps[0].proposal)
        self.assertIsNone(result.steps[0].evaluation)
        self.assertEqual((self.build_calls, self.evaluate_calls), ([], []))
        single = self.run_search(options=(self.options[0],), max_options=1)
        self.assertEqual(single.status, "exhausted")
        self.assertIsNone(single.proposal)

    def test_control_unknown_and_error_stop_without_fallback_to_later_success(self):
        for status in ("unknown", "error"):
            with self.subTest(status=status):
                self.control_calls.clear()
                self.decisions[0] = status
                result = self.run_search()
                self.assertEqual((result.status, result.reason), (status, "control_" + status))
                self.assertEqual(len(result.steps), 1)
                self.assertEqual(result.steps[0].decision.reason, "explicit fixture control")
                self.assertIsNone(result.proposal)
                self.assertEqual(len(self.control_calls), 1)
                self.assertEqual((self.build_calls, self.evaluate_calls), ([], []))

    def test_terminal_unknown_error_and_not_applicable_stop_with_full_evaluation(self):
        for statuses, expected, reason in (
            (("satisfied", "unknown"), "unknown", "terminal_unknown"),
            (("violated", "unknown"), "unknown", "terminal_unknown"),
            (("satisfied", "not_applicable"), "unknown", "terminal_not_applicable"),
            (("violated", "error"), "error", "terminal_error"),
            (("unknown", "error"), "error", "terminal_error"),
        ):
            with self.subTest(statuses=statuses):
                self.control_calls.clear()
                self.build_calls.clear()
                self.evaluate_calls.clear()
                self.outcomes[1] = statuses
                result = self.run_search()
                self.assertEqual((result.status, result.reason), (expected, reason))
                self.assertEqual(len(result.steps), 2)
                self.assertEqual(tuple(o.status for o in result.steps[-1].evaluation.report.outcomes), statuses)
                self.assertIsNotNone(result.steps[-1].proposal)
                self.assertIsNone(result.proposal)
                self.assertEqual((len(self.control_calls), len(self.build_calls), len(self.evaluate_calls)), (2, 1, 1))

    def test_construction_control_does_not_remove_its_obligation_from_terminal_check(self):
        self.outcomes[1] = ("violated", "satisfied")
        result = self.run_search()
        self.assertEqual(result.steps[1].evaluation.report.residual, ("domain",))
        self.assertEqual(result.proposal.proposal_id, "option-2")

    def test_bad_budget_types_and_mutable_or_lazy_spaces_rejected_before_callbacks(self):
        for budget in (-1, True, 1.0, "1"):
            with self.subTest(budget=budget), self.assertRaises(ContractError):
                self.run_search(max_options=budget)
        for options in (list(self.options), iter(self.options), None):
            with self.subTest(options=options), self.assertRaises(ContractError):
                self.run_search(options=options)
        self.assertEqual((self.control_calls, self.build_calls, self.evaluate_calls), ([], [], []))

    def test_all_options_validate_before_search_even_beyond_budget(self):
        malformed = to_data(self.options[3])
        malformed["hint"] = "untrusted field"
        bad_options = (
            (self.options[0], self.options[0]),
            (replace(self.options[0], id=" "),),
            (replace(self.options[0], id=True),),
            (replace(self.options[0], target=""),),
            (replace(self.options[0], values=()),),
            (replace(self.options[0], values=(Property("value", 0), Property("value", 1))),),
            (replace(self.options[0], values=(Property("", 0),)),),
            (*self.options[:3], malformed),
        )
        for options in bad_options:
            with self.subTest(options=options), self.assertRaises(ContractError):
                self.run_search(options=options, max_options=0)
        self.assertEqual(self.control_calls, [])

    def test_bad_snapshot_task_project_and_noncallables_rejected(self):
        variants = (
            {"snapshot": replace(self.snapshot, revision=False)},
            {"snapshot": replace(self.snapshot, revision=-1)},
            {"task_ref": replace(self.task, project_id="another-project")},
            {"task_ref": replace(self.task, content_hash="not-a-hash")},
            {"task_ref": replace(self.task, revision=1)},
            {"control": None}, {"build": None}, {"evaluate": None},
        )
        for fields in variants:
            with self.subTest(fields=fields), self.assertRaises(ContractError):
                self.run_search(**fields)
        self.assertEqual(self.control_calls, [])

    def test_construction_plan_requires_complete_unique_versioned_obligation_coverage(self):
        domain, goal = self.plan.controls
        for plan in (
            replace(self.plan, check_plan_hash="0" * 64),
            replace(self.plan, controls=(domain,)),
            replace(self.plan, controls=(domain, goal, goal)),
            replace(self.plan, controls=(domain, replace(goal, obligation_version="2"))),
            replace(self.plan, controls=(domain, replace(goal, obligation_id="another"))),
            replace(self.plan, controls=(domain, goal, replace(goal, obligation_id="extra"))),
        ):
            with self.subTest(plan=plan), self.assertRaises(ContractError):
                self.run_search(construction_plan=plan)
        self.assertEqual(self.control_calls, [])

    def test_construction_plan_stage_explanation_and_residual_must_be_consistent(self):
        domain, goal = self.plan.controls
        variants = [replace(self.plan, residual=value) for value in ((), ("domain", "goal"), ("goal", "goal"))]
        variants += [replace(self.plan, controls=(replace(domain, **fields), goal))
                     for fields in ({"stage": "during-deployment"}, {"mechanism": ""},
                                    {"remaining": " "}, {"fragment": ""})]
        for plan in variants:
            with self.subTest(plan=plan), self.assertRaises(ContractError):
                self.run_search(construction_plan=plan)
        self.assertEqual(self.control_calls, [])

    def test_empty_or_duplicate_check_plan_obligations_rejected(self):
        for checks in (replace(self.checks, obligations=()),
                       replace(self.checks, obligations=self.checks.obligations * 2)):
            with self.subTest(checks=checks), self.assertRaises(ContractError):
                self.run_search(check_plan=checks)

    def test_control_response_requires_exact_option_binding_and_strict_shape(self):
        for fields in ({"option_hash": digest(self.options[1])}, {"status": True},
                       {"status": "satisfied"}, {"reason": " "}):
            with self.subTest(fields=fields), self.assertRaises(ContractError):
                self.run_search(control=lambda option: replace(self.control(option), **fields))
        def extra_field(option):
            response = to_data(self.control(option))
            response["fallback"] = "allow"
            return response
        with self.assertRaises(ContractError):
            self.run_search(control=extra_field)
        self.assertEqual((self.build_calls, self.evaluate_calls), ([], []))

    def test_builder_response_requires_original_base_nonempty_operations_and_valid_sources(self):
        bad_evidence = EvidenceRef(replace(self.task, content_hash="broken"), "lines:1-1", "fixture")
        variants = (
            {"base": replace(ref(self.snapshot), revision=1)},
            {"base": replace(ref(self.snapshot), revision=False)},
            {"operations": ()}, {"proposal_id": " "}, {"proposal_id": True},
            {"api_version": "other"}, {"intent_refs": (bad_evidence,)},
        )
        for fields in variants:
            with self.subTest(fields=fields), self.assertRaises(ContractError):
                self.run_search(build=lambda option: replace(self.build(option), **fields))
        self.assertEqual(self.evaluate_calls, [])

    def test_candidate_identity_revision_and_strict_shape_are_checked_before_report(self):
        changes = ({"revision": 0}, {"revision": 2}, {"revision": True},
                   {"project_id": "other"}, {"model_id": "other"},
                   {"metamodel": replace(self.meta.ref, version="2")}, {"metamodel_hash": "0" * 64})
        for fields in changes:
            def evaluator(proposal):
                evaluation = self.evaluate(proposal)
                candidate = replace(evaluation.candidate, **fields)
                report = replace(evaluation.report,
                                 binding=replace(evaluation.report.binding, candidate_hash=digest(candidate)))
                return CandidateEvaluation(candidate, report)
            with self.subTest(fields=fields), self.assertRaises(ContractError):
                self.run_search(evaluate=evaluator)

    def test_terminal_report_candidate_plan_scope_assumptions_and_tool_bindings_are_checked(self):
        for fields in ({"candidate_hash": "0" * 64}, {"plan_hash": "0" * 64},
                       {"scope": ()}, {"scope": ("other",)}, {"assumptions": ()},
                       {"tool": ""}, {"tool_version": ""}):
            def evaluator(proposal):
                evaluation = self.evaluate(proposal)
                return replace(evaluation, report=replace(evaluation.report,
                               binding=replace(evaluation.report.binding, **fields)))
            with self.subTest(fields=fields), self.assertRaises(ContractError):
                self.run_search(evaluate=evaluator)

    def test_terminal_report_rejects_missing_duplicate_wrong_version_or_extra_outcomes(self):
        def variants(report):
            first, second = report.outcomes
            return ((second,), (), (first, second, second),
                    (replace(first, obligation_version="2"), second),
                    (first, second, replace(first, obligation_id="extra")),
                    (replace(first, status=True), second))
        sample = self.evaluate(self.build(self.options[1])).report
        for outcomes in variants(sample):
            def evaluator(proposal):
                evaluation = self.evaluate(proposal)
                return replace(evaluation, report=replace(evaluation.report, outcomes=outcomes))
            with self.subTest(outcomes=outcomes), self.assertRaises(ContractError):
                self.run_search(evaluate=evaluator)

    def test_callback_exceptions_propagate_without_trying_another_option(self):
        failure = RuntimeError("callback unavailable")
        calls = []
        def fail(*args):
            calls.append(args)
            raise failure
        for name in ("control", "build", "evaluate"):
            calls.clear()
            with self.subTest(callback=name), self.assertRaises(RuntimeError) as caught:
                self.run_search(**{name: fail})
            self.assertIs(caught.exception, failure)
            self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
