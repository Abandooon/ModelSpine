"""Independent pinned engineering expectations and source-associated witnesses."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps"))
import bootstrap
bootstrap.activate(("generation", "model-kernel", "assurance"))

from bounded_generation import load_example
from dag_construction import DagEditSpace, prepare_dag
from modelspine_kernel import ModelKernel
from modelspine_protocols import (
    AddElement, ArtifactRef, ChangeProposal, Element, EvidenceRef, Property,
    SetDependencies, SetProperty, decode, loads, properties, ref,
)
from studies.construction.controls import ordinary_control
from studies.construction.run import (
    CONDITIONS, SCENARIOS, execute_condition, observe_trial, reference_spec, scenario_inputs,
)
from support.task_oracle import evaluate_candidate
from task_checks import check_tasks

FIXTURES = ROOT / "tests" / "fixtures" / "construction"


class ConstructionStudyTests(unittest.TestCase):
    def setUp(self):
        self.inputs = load_example()
        self.pinned = reference_spec()

    def test_all_nine_options_match_fixed_oracle_and_independent_rule(self):
        prepared, meta, snapshot, raw, _ = self.inputs
        space = loads(DagEditSpace, raw.decode())
        constructor = prepare_dag(snapshot, prepared.contract.plan, space,
                                  (EvidenceRef(prepared.task_ref, "artifact", "study-task"),))
        expected = json.loads((FIXTURES / "expected-options.json").read_text())["options"]
        self.assertEqual(len(constructor.options), len(expected))
        kernel = ModelKernel(snapshot, meta, prepared.contract.plan, check_tasks, frozenset({"test"}))
        valid_edits = []
        for option, truth in zip(constructor.options, expected):
            with self.subTest(option=truth):
                self.assertEqual(properties(option.values), {"source": truth["source"], "target": truth["target"]})
                dag = constructor.control(option)
                ordinary = ordinary_control(snapshot, space, option)
                self.assertEqual(dag.status, truth["control"])
                self.assertEqual(ordinary.status, truth["control"])
                candidate = (snapshot if dag.status == "no_change" else
                             kernel.preview(constructor.build(option)).candidate)
                evaluation = evaluate_candidate(candidate, self.pinned)
                self.assertEqual(evaluation.satisfied, truth["reference"] == "satisfied")
                if evaluation.satisfied and dag.status != "no_change":
                    valid_edits.append(option.id)
                    self.assertEqual(ordinary.status, "allow")
        self.assertEqual(len(valid_edits), 1)

    def test_budgets_one_two_three_keep_same_options_and_stop(self):
        for budget in (1, 2, 3):
            outputs = [execute_condition(c, scenario_inputs(self.inputs, {"max_options": budget}))
                       for c in CONDITIONS]
            self.assertEqual([tuple(s.option for s in r.search.steps) for r in outputs],
                             [tuple(s.option for s in outputs[0].search.steps)] * 3)
            for result in outputs:
                self.assertEqual(result.search.status, "candidate_found" if budget == 3 else "budget_exhausted")
                self.assertEqual(len(result.search.steps), budget)
                self.assertEqual(bool(result.run and result.run.commit), budget == 3)
                if result.run:
                    self.assertTrue(evaluate_candidate(result.run.accepted, self.pinned).satisfied)
            if budget == 3:
                self.assertEqual([sum(s.evaluation is not None for s in r.search.steps) for r in outputs], [3, 2, 2])
                self.assertEqual(outputs[0].run.accepted, outputs[1].run.accepted)
                self.assertEqual(outputs[1].run.accepted, outputs[2].run.accepted)

    def test_leaked_cycle_and_acyclic_wrong_goal_are_terminal_rejected(self):
        inputs = scenario_inputs(self.inputs, {"max_options": 2})
        terminal = execute_condition("terminal-only", inputs)
        cycle, wrong_goal = terminal.search.steps
        self.assertEqual(cycle.decision.status, "allow")
        self.assertEqual(cycle.evaluation.report.outcomes[0].status, "violated")
        self.assertFalse(evaluate_candidate(cycle.evaluation.candidate, self.pinned).satisfied)
        self.assertEqual(wrong_goal.evaluation.report.outcomes[0].status, "satisfied")
        self.assertFalse(wrong_goal.evaluation.report.satisfied)
        self.assertIsNone(terminal.run)
        for condition in CONDITIONS[1:]:
            result = execute_condition(condition, inputs)
            self.assertEqual(result.search.steps[1].decision.status, "allow")
            self.assertFalse(result.search.steps[1].evaluation.report.satisfied)

    def test_single_valid_invalid_and_no_change_do_not_fake_candidates(self):
        for name, changes in SCENARIOS[4:]:
            for condition in CONDITIONS:
                with self.subTest(scenario=name, condition=condition):
                    result = execute_condition(condition, scenario_inputs(self.inputs, changes))
                    self.assertEqual(result.search.status, "candidate_found" if name == "only-valid" else "exhausted")
                    self.assertEqual(bool(result.run and result.run.commit), name == "only-valid")
                    if name == "unchanged":
                        self.assertEqual(result.search.steps[0].decision.status, "no_change")
                        self.assertIsNone(result.search.steps[0].proposal)

    def test_reference_cannot_change_search_or_save(self):
        inputs = scenario_inputs(self.inputs, {"max_options": 3})
        with patch("studies.construction.run.evaluate_candidate", side_effect=AssertionError("oracle leaked")):
            result = execute_condition("ordinary-rule", inputs)
        self.assertIsNotNone(result.run.commit)

    def test_real_checker_counts_include_assess_decide_and_apply(self):
        for condition, search_checks in zip(CONDITIONS, (3, 2, 2)):
            record = observe_trial(condition, condition, scenario_inputs(self.inputs, {"max_options": 3}), self.pinned)
            self.assertEqual(record["counts"]["search_candidate_checks"], search_checks)
            self.assertEqual(record["counts"]["final_acceptance_checker_calls"], 3)
            self.assertEqual(record["total_development_checker_calls"], search_checks + 3)
            self.assertTrue(record["saved"])
            self.assertIsNone(record["human_seconds"])
            self.assertGreaterEqual(record["wall_seconds"], 0)
            self.assertGreaterEqual(record["reference_seconds"], 0)

    def test_faults_stay_in_attempt_denominator_without_fallback(self):
        for fault in ("unknown", "error", "exception"):
            with self.subTest(fault=fault):
                record = observe_trial(fault, "ordinary-rule", self.inputs, self.pinned, fault)
                self.assertTrue(record["planned"] and record["started"])
                self.assertEqual(record["status"], "unknown" if fault == "unknown" else "error")
                self.assertFalse(record["saved"])
                self.assertEqual(record["total_development_checker_calls"], 0)
                if fault == "exception":
                    self.assertFalse(record["returned"])
                    self.assertIsNone(record["counts"])
                    self.assertEqual(record["exception_type"], "RuntimeError")
                else:
                    self.assertTrue(record["returned"])
                    self.assertEqual(record["counts"]["considered"], 1)
                    self.assertEqual(record["counts"]["constructed"], 0)

    def test_ordinary_rule_does_not_call_dag_control(self):
        with patch("dag_construction._DagConstructor.control", side_effect=AssertionError("shared algorithm")):
            result = execute_condition("ordinary-rule", self.inputs)
        self.assertIsNotNone(result.run.commit)

    def test_empty_space_and_zero_budget_do_not_prove_representation_gap(self):
        for changes, expected in (({"sources": ()}, "exhausted"), ({"max_options": 0}, "budget_exhausted")):
            for condition in CONDITIONS:
                result = execute_condition(condition, scenario_inputs(self.inputs, changes))
                self.assertEqual(result.search.status, expected)
                self.assertEqual(result.search.steps, ())
                self.assertIsNone(result.run)


class DiagnosticWitnessTests(unittest.TestCase):
    def setUp(self):
        self.prepared, self.meta, self.base, _, _ = load_example()
        self.fixture = json.loads((FIXTURES / "diagnostic-cases.json").read_text())
        raw = (FIXTURES / "diagnostic-source.txt").read_bytes()
        self.assertEqual(sha256(raw).hexdigest(), self.fixture["source"]["content_hash"])
        self.assertEqual(raw.decode().splitlines()[1],
                         "R1: The identified relation direct-ac goes directly from node-a to node-c.")
        self.evidence = EvidenceRef(decode(ArtifactRef, self.fixture["source"]),
                                    self.fixture["source_locator"], self.fixture["origin"])
        self.assertEqual(self.evidence.locator, "lines:2-2")

    def redirect(self, snapshot):
        statement = self.fixture["statement"]
        return ChangeProposal("0.1", "diagnostic-redirect", ref(snapshot), (
            SetProperty("set_property", "edge-bc", "source", statement["source"]),
            SetProperty("set_property", "edge-bc", "target", statement["target"]),
            SetDependencies("set_dependencies", "edge-bc", ("node-a", "node-c"), True),
        ), (self.evidence,))

    def addition(self, snapshot):
        statement = self.fixture["statement"]
        edge = Element("edge-ac", "edge", statement["relation_identity"], "graph",
                       (Property("source", statement["source"]), Property("target", statement["target"])),
                       ("node-a", "node-c"), True, "intent", True, (self.evidence,))
        root = next(e for e in snapshot.elements if e.id == "graph")
        return ChangeProposal("0.1", "diagnostic-add", ref(snapshot), (
            AddElement("add_element", edge),
            SetDependencies("set_dependencies", "graph", (*root.dependencies, "edge-ac"), False),
        ), (self.evidence,))

    def replay(self, snapshot, proposal, identity):
        kernel = ModelKernel(snapshot, self.meta, self.prepared.contract.plan, check_tasks, frozenset({"test"}))
        candidate = kernel.preview(proposal).candidate
        self.assertTrue(check_tasks(candidate, self.prepared.contract.plan).satisfied)
        self.assertTrue(evaluate_candidate(candidate, reference_spec()).satisfied)
        edge = next(e for e in candidate.elements if e.id == identity)
        self.assertEqual(properties(edge.properties), {"source": self.fixture["statement"]["source"],
                                                     "target": self.fixture["statement"]["target"]})
        self.assertEqual(edge.sources, (self.evidence,))
        return candidate

    def test_mapping_witness_preserves_identity_source_and_existing_task(self):
        base = replace(self.base, elements=tuple(replace(e, sources=(self.evidence,)) if e.id == "edge-bc" else e
                                                for e in self.base.elements))
        # The original graph passes behavioral goals while violating R1's direct edge.
        self.assertTrue(evaluate_candidate(base, reference_spec()).satisfied)
        self.assertNotEqual(properties(next(e for e in base.elements if e.id == "edge-bc").properties),
                            {"source": "node-a", "target": "node-c"})
        self.replay(base, self.redirect(base), "edge-bc")

    def test_missing_instance_has_same_metamodel_addition_witness(self):
        base = replace(self.base, elements=tuple(
            replace(e, dependencies=tuple(d for d in e.dependencies if d != "edge-bc"))
            for e in self.base.elements if e.id != "edge-bc"))
        self.assertFalse(evaluate_candidate(base, reference_spec()).satisfied)
        candidate = self.replay(base, self.addition(base), "edge-ac")
        self.assertEqual(candidate.metamodel, base.metamodel)
        self.assertEqual(len(candidate.elements), len(base.elements) + 1)

    def test_unassociated_behavior_allows_two_repairs_without_classification(self):
        case = next(c for c in self.fixture["cases"] if c["id"] == "unassociated")
        self.assertIsNone(case["association"])
        self.assertFalse(case["inventory_complete"])
        self.assertEqual(case["expected"], "unknown")
        kernel = ModelKernel(self.base, self.meta, self.prepared.contract.plan, check_tasks, frozenset({"test"}))
        for proposal in (self.redirect(self.base), self.addition(self.base)):
            candidate = kernel.preview(proposal).candidate
            self.assertTrue(evaluate_candidate(candidate, reference_spec()).satisfied)
        # These are possible behavior repairs, not evidence that an existing edge
        # is R1's identity. No diagnostic implementation is called or supplied.

    def test_faithful_relation_needs_no_fabricated_repair(self):
        base = replace(self.base, elements=tuple(replace(e, sources=(self.evidence,)) if e.id == "edge-bc" else e
                                                for e in self.base.elements))
        candidate = self.replay(base, self.redirect(base), "edge-bc")
        self.assertTrue(evaluate_candidate(candidate, reference_spec()).satisfied)
        self.assertEqual(next(c for c in self.fixture["cases"] if c["id"] == "already-faithful")["expected"],
                         "no-defect-evidence")


if __name__ == "__main__":
    unittest.main()
