"""Fixed goals remain independent of editable model inputs and invalid models."""
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "adapters"))

from finite_models import check_automaton, check_structure
from fixtures import load_case
from task_checks import TOOL, VERSION, check_tasks
from modelspine_protocols import ContractError, Obligation, Property, digest, validate_report

CASES = Path(__file__).resolve().parents[1] / "domain-packs"


class TaskCheckerTests(unittest.TestCase):
    def setUp(self):
        _, self.graph, self.graph_plan = load_case(CASES / "structural-graph")
        _, self.machine, self.machine_plan = load_case(CASES / "finite-automaton")

    def fields(self, snapshot, element_id, **values):
        return replace(snapshot, elements=tuple(
            replace(element, properties=tuple(Property(item.name, values.get(item.name, item.value))
                                              for item in element.properties))
            if element.id == element_id else element for element in snapshot.elements))

    def element(self, snapshot, target, **values):
        return replace(snapshot, elements=tuple(replace(element, **values) if element.id == target else element
                                                for element in snapshot.elements))

    def plan(self, kind, **parameters):
        graph = kind == "graph_reachability"
        baseline = self.graph_plan if graph else self.machine_plan
        obligation = Obligation("fixed-goal", "1", kind, "graph" if graph else "machine",
                                "root" if graph else "initial",
                                tuple(Property(key, value) for key, value in parameters.items()))
        return replace(baseline, id="fixed-target", rule_version="task-checks/1", obligations=(obligation,))

    def outcome(self, snapshot, plan):
        report = check_tasks(snapshot, plan)
        self.assertEqual(report.binding.candidate_hash, digest(snapshot))
        self.assertEqual(report.binding.plan_hash, digest(plan))
        self.assertEqual((report.binding.tool, report.binding.tool_version), (TOOL, VERSION))
        self.assertEqual(validate_report(report, snapshot, plan, (plan.obligations[0].target,)), report)
        return report.outcomes[0]

    def test_graph_positive_negative_and_zero_length_reachability(self):
        for source, destination, expected, status in [
            ("node-a", "node-c", True, "satisfied"),
            ("node-c", "node-a", False, "satisfied"),
            ("node-b", "node-b", True, "satisfied"),
            ("node-b", "node-b", False, "violated"),
        ]:
            with self.subTest(source=source, destination=destination, expected=expected):
                plan = self.plan("graph_reachability", source=source, destination=destination,
                                 expected_reachable=expected)
                self.assertEqual(self.outcome(self.graph, plan).status, status)

    def test_valid_graph_change_can_violate_fixed_goal_without_changing_goal(self):
        plan = self.plan("graph_reachability", source="node-b", destination="node-c", expected_reachable=True)
        candidate = self.fields(self.graph, "edge-bc", source="node-a")
        candidate = self.element(candidate, "edge-bc", dependencies=("node-a", "node-c"))
        self.assertTrue(check_structure(candidate, self.graph_plan).satisfied)
        self.assertEqual(self.outcome(self.graph, plan).status, "satisfied")
        self.assertEqual(self.outcome(candidate, plan).status, "violated")

    def test_invalid_graph_cannot_satisfy_negative_expectation(self):
        plan = self.plan("graph_reachability", source="node-c", destination="node-a", expected_reachable=False)
        candidates = [
            (self.fields(self.graph, "edge-ab", target="node-a"), "violated", "directed_cycle"),
            (self.fields(self.graph, "edge-ab", target="absent"), "violated", "invalid_endpoint"),
            (self.element(self.graph, "edge-ab", parent="node-a"), "violated", "not_flat_membership"),
            (self.element(self.graph, "graph", dependencies_complete=True), "error", "membership_completeness"),
            (self.element(self.graph, "graph", dependencies=()), "error", "member_read_dependencies"),
        ]
        for candidate, status, finding in candidates:
            with self.subTest(finding=finding):
                outcome = self.outcome(candidate, plan)
                self.assertEqual(outcome.status, status)
                self.assertTrue(any(finding in item for item in outcome.findings))

    def test_fixed_graph_endpoint_must_belong_to_graph(self):
        for source, destination in [("absent", "node-a"), ("node-a", "graph")]:
            with self.subTest(source=source, destination=destination):
                plan = self.plan("graph_reachability", source=source, destination=destination,
                                 expected_reachable=False)
                self.assertEqual(self.outcome(self.graph, plan).status, "error")

    def test_fixed_input_cannot_be_replaced_by_editing_candidate_trace(self):
        plan = self.plan("trace_acceptance", input="ab", expected_accept=True)
        candidate = self.fields(self.machine, "step-b", symbol="a")
        candidate = self.fields(candidate, "machine", trace="aa")
        original = digest(candidate)
        self.assertTrue(check_automaton(candidate, self.machine_plan).satisfied)
        self.assertEqual(self.outcome(candidate, plan).status, "violated")
        self.assertEqual(digest(candidate), original)
        trace_only = self.fields(self.machine, "machine", trace="outside-the-alphabet")
        self.assertFalse(check_automaton(trace_only, self.machine_plan).satisfied)
        self.assertEqual(self.outcome(trace_only, plan).status, "satisfied")

    def test_supported_trace_rejection_can_satisfy_negative_expectation(self):
        for task_input, expected, status in [
            ("ab", True, "satisfied"), ("ab", False, "violated"),
            ("a", False, "satisfied"), ("aa", False, "satisfied"),
            ("", False, "satisfied"),
        ]:
            with self.subTest(task_input=task_input, expected=expected):
                plan = self.plan("trace_acceptance", input=task_input, expected_accept=expected)
                self.assertEqual(self.outcome(self.machine, plan).status, status)
        accepts_empty = self.fields(self.machine, "s0", accepting=True)
        plan = self.plan("trace_acceptance", input="", expected_accept=True)
        self.assertEqual(self.outcome(accepts_empty, plan).status, "satisfied")

    def test_input_outside_alphabet_remains_unknown_for_both_expectations(self):
        for expected in (False, True):
            with self.subTest(expected=expected):
                plan = self.plan("trace_acceptance", input="ac", expected_accept=expected)
                self.assertEqual(self.outcome(self.machine, plan).status, "unknown")

    def test_invalid_machine_cannot_satisfy_negative_expectation(self):
        plan = self.plan("trace_acceptance", input="a", expected_accept=False)
        nondeterministic = self.fields(self.machine, "step-b", source="s0", symbol="a")
        nondeterministic = self.element(nondeterministic, "step-b", dependencies=("s0", "s2"))
        candidates = [
            (nondeterministic, "violated", "nondeterministic"),
            (self.fields(self.machine, "step-b", target="missing"), "violated", "invalid_endpoint"),
            (self.fields(self.machine, "step-b", symbol=""), "violated", "invalid_finite_symbol"),
            (self.element(self.machine, "step-b", parent="s0"), "violated", "not_flat_membership"),
            (self.element(self.machine, "machine", dependencies_complete=True), "error", "membership_completeness"),
            (self.element(self.machine, "step-b", dependencies=()), "error", "endpoint_read_dependencies"),
        ]
        for candidate, status, finding in candidates:
            with self.subTest(finding=finding):
                outcome = self.outcome(candidate, plan)
                self.assertEqual(outcome.status, status)
                self.assertTrue(any(finding in item for item in outcome.findings))

    def test_task_parameters_require_exact_keys_and_scalar_types(self):
        graph_parameters = {"source": "node-a", "destination": "node-c", "expected_reachable": True}
        machine_parameters = {"input": "ab", "expected_accept": True}
        for kind, snapshot, parameters in [("graph_reachability", self.graph, graph_parameters),
                                           ("trace_acceptance", self.machine, machine_parameters)]:
            variants = [dict(parameters, extra=False), {},
                        {key: 1 if type(value) is bool else value for key, value in parameters.items()},
                        {key: False if type(value) is str else value for key, value in parameters.items()}]
            for candidate in variants:
                with self.subTest(kind=kind, parameters=candidate):
                    self.assertEqual(self.outcome(snapshot, self.plan(kind, **candidate)).status, "error")

    def test_legacy_rule_outcomes_are_preserved_by_shared_helpers(self):
        graph_bad = self.fields(self.graph, "edge-bc", target="absent")
        machine_bad = self.fields(self.machine, "machine", trace="ac")
        for snapshot, plan, legacy in [
            (self.graph, self.graph_plan, check_structure), (graph_bad, self.graph_plan, check_structure),
            (self.machine, self.machine_plan, check_automaton), (machine_bad, self.machine_plan, check_automaton),
        ]:
            with self.subTest(model=snapshot.model_id, content=digest(snapshot)):
                self.assertEqual(check_tasks(snapshot, plan).outcomes, legacy(snapshot, plan).outcomes)

    def test_scope_unknown_rules_and_missing_targets_are_explicit(self):
        for target, status in [("graph", "unknown"), ("absent", "error")]:
            with self.subTest(target=target):
                unknown = Obligation("unknown", "1", "unimplemented", target, "root", ())
                plan = replace(self.graph_plan, obligations=(unknown,))
                self.assertEqual(self.outcome(self.graph, plan).status, status)
        for scope in [(), ("graph", "graph"), ("absent",)]:
            with self.subTest(scope=scope), self.assertRaises(ContractError):
                check_tasks(self.graph, self.graph_plan, scope)

    def test_renaming_preserves_fixed_identity_and_unicode_input_is_supported(self):
        renamed = self.element(self.graph, "node-b", name="renamed-with-stable-id")
        plan = self.plan("graph_reachability", source="node-a", destination="node-c", expected_reachable=True)
        self.assertEqual(self.outcome(renamed, plan).status, "satisfied")
        unicode_machine = self.fields(self.machine, "machine", alphabet="甲乙")
        unicode_machine = self.fields(unicode_machine, "step-a", symbol="甲")
        unicode_machine = self.fields(unicode_machine, "step-b", symbol="乙")
        plan = self.plan("trace_acceptance", input="甲乙", expected_accept=True)
        self.assertEqual(self.outcome(unicode_machine, plan).status, "satisfied")


if __name__ == "__main__":
    unittest.main()
