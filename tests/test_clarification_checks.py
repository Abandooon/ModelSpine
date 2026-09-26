"""Probe observations separate supported rejection from invalid/unknown models."""
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "adapters"))

from clarification_checks import goal, observe
from fixtures import load_case
from modelspine_protocols import (
    ArtifactRef, ContractError, EvidenceRef, Obligation, Property, digest, ref, to_data,
)
from modelspine_requirements import Probe

CASES = Path(__file__).resolve().parents[1] / "domain-packs"


class ClarificationCheckTests(unittest.TestCase):
    def setUp(self):
        _, self.graph, _ = load_case(CASES / "structural-graph")
        _, self.machine, _ = load_case(CASES / "finite-automaton")
        self.source = EvidenceRef(ArtifactRef("foundation-examples", "source", "1", "a" * 64),
                                  "line:1", "provided")

    def probe(self, kind="graph_reachability", **parameters):
        graph = kind == "graph_reachability"
        if not parameters:
            parameters = ({"source": "node-a", "destination": "node-c", "expected_reachable": True}
                          if graph else {"input": "ab", "expected_accept": True})
        obligation = Obligation("probe-goal", "1", kind, "graph" if graph else "machine",
                                "root" if graph else "initial",
                                tuple(Property(key, value) for key, value in parameters.items()))
        return Probe("probe", "Should this finite behavior hold?", obligation, (self.source,))

    def fields(self, snapshot, element_id, **values):
        return replace(snapshot, elements=tuple(
            replace(element, properties=tuple(Property(item.name, values.get(item.name, item.value))
                                              for item in element.properties))
            if element.id == element_id else element for element in snapshot.elements))

    def element(self, snapshot, element_id, **values):
        return replace(snapshot, elements=tuple(
            replace(element, **values) if element.id == element_id else element
            for element in snapshot.elements))

    def observation(self, snapshot, probe, status, value):
        result = observe(snapshot, probe)
        self.assertEqual((result.candidate, result.probe_hash), (ref(snapshot), digest(probe)))
        self.assertEqual((result.status, result.value), (status, value))
        self.assertTrue(result.reason)
        return result

    def test_graph_true_false_and_zero_length_paths(self):
        for source, destination, value in [("node-a", "node-c", True), ("node-c", "node-a", False),
                                           ("node-b", "node-b", True)]:
            with self.subTest(source=source, destination=destination):
                probe = self.probe(source=source, destination=destination, expected_reachable=True)
                self.observation(self.graph, probe, "observed", value)

    def test_invalid_graph_never_becomes_negative_observation(self):
        candidates = [
            self.fields(self.graph, "edge-ab", target="node-a"),
            self.fields(self.graph, "edge-ab", target="missing"),
            self.element(self.graph, "edge-ab", parent="node-a"),
            self.element(self.graph, "graph", dependencies_complete=True),
            self.element(self.graph, "graph", dependencies=()),
            self.element(self.graph, "edge-ab", dependencies=()),
            self.element(self.graph, "edge-ab", kind="unsupported"),
            self.element(self.graph, "graph", kind="machine"),
            replace(self.graph, elements=self.graph.elements + (self.graph.elements[0],)),
        ]
        for candidate in candidates:
            with self.subTest(candidate=digest(candidate)):
                self.observation(candidate, self.probe(), "error", None)

    def test_missing_graph_endpoint_or_probe_target_is_error(self):
        probe = self.probe(source="missing", destination="node-c", expected_reachable=True)
        self.observation(self.graph, probe, "error", None)
        probe = self.probe()
        self.observation(self.graph, replace(probe, obligation=replace(probe.obligation, target="missing")),
                         "error", None)

    def test_machine_acceptance_rejection_and_empty_input(self):
        for trace, value in [("ab", True), ("a", False), ("aa", False), ("", False)]:
            with self.subTest(trace=trace):
                self.observation(self.machine, self.probe("trace_acceptance", input=trace, expected_accept=True),
                                 "observed", value)
        accepts_empty = self.fields(self.machine, "s0", accepting=True)
        self.observation(accepts_empty, self.probe("trace_acceptance", input="", expected_accept=True),
                         "observed", True)

    def test_machine_model_trace_cannot_replace_fixed_probe_input(self):
        changed = self.fields(self.machine, "step-b", symbol="a")
        changed = self.fields(changed, "machine", trace="aa")
        probe = self.probe("trace_acceptance")
        before = digest(changed), digest(probe)
        self.observation(changed, probe, "observed", False)
        self.assertEqual((digest(changed), digest(probe)), before)
        self.observation(self.fields(self.machine, "machine", trace="outside"), probe, "observed", True)

    def test_invalid_machine_never_becomes_negative_observation(self):
        nondeterministic = self.fields(self.machine, "step-b", source="s0", symbol="a")
        nondeterministic = self.element(nondeterministic, "step-b", dependencies=("s0", "s2"))
        candidates = [
            nondeterministic,
            self.fields(self.machine, "step-b", target="missing"),
            self.fields(self.machine, "step-b", symbol=""),
            self.fields(self.machine, "machine", initial="missing"),
            self.fields(self.machine, "machine", alphabet="aa"),
            self.fields(self.machine, "s0", accepting=1),
            self.element(self.machine, "step-b", parent="s0"),
            self.element(self.machine, "machine", dependencies_complete=True),
            self.element(self.machine, "step-b", dependencies=()),
        ]
        for candidate in candidates:
            with self.subTest(candidate=digest(candidate)):
                self.observation(candidate, self.probe("trace_acceptance"), "error", None)

    def test_outside_alphabet_and_unknown_rule_are_unknown(self):
        self.observation(self.machine, self.probe("trace_acceptance", input="ac", expected_accept=True),
                         "unknown", None)
        probe = self.probe()
        unknown = replace(probe, obligation=replace(probe.obligation, kind="unknown_rule"))
        self.observation(self.graph, unknown, "unknown", None)
        with self.assertRaises(ContractError):
            goal(unknown, False)

    def test_templates_require_exact_fields_scalar_types_and_positive_boolean(self):
        for kind, snapshot in [("graph_reachability", self.graph), ("trace_acceptance", self.machine)]:
            valid = self.probe(kind)
            parameters = valid.obligation.parameters
            invalid_parameters = [(), parameters + (Property("extra", False),),
                                  parameters + (parameters[0],)]
            for replacement in [False, 1, "true"]:
                invalid_parameters.append(tuple(
                    Property(item.name, replacement) if item.name.startswith("expected_") else item
                    for item in parameters))
            invalid_parameters.append(tuple(
                Property(item.name, False) if type(item.value) is str else item for item in parameters))
            for invalid in invalid_parameters:
                with self.subTest(kind=kind, parameters=invalid):
                    probe = replace(valid, obligation=replace(valid.obligation, parameters=invalid))
                    self.observation(snapshot, probe, "error", None)
                    with self.assertRaises(ContractError):
                        goal(probe, False)
            wrong_field = replace(valid, obligation=replace(valid.obligation, field="wrong"))
            self.observation(snapshot, wrong_field, "error", None)
            with self.assertRaises(ContractError):
                goal(wrong_field, True)

    def test_duplicate_or_missing_model_properties_are_errors(self):
        root = self.graph.elements[0]
        duplicated = self.element(self.graph, root.id, properties=root.properties + root.properties)
        self.observation(duplicated, self.probe(), "error", None)
        missing = self.element(self.graph, root.id, properties=())
        self.observation(missing, self.probe(), "error", None)

    def test_goal_changes_only_answer_field_and_preserves_fixed_input(self):
        for kind in ("graph_reachability", "trace_acceptance"):
            probe = self.probe(kind)
            original = digest(probe)
            for answer in (True, False):
                expected = replace(probe.obligation, parameters=tuple(
                    Property(item.name, answer) if item.name.startswith("expected_") else item
                    for item in probe.obligation.parameters))
                self.assertEqual(goal(probe, answer), expected)
                self.assertEqual(digest(probe), original)
            for invalid in (0, 1, "yes", None):
                with self.subTest(kind=kind, answer=invalid), self.assertRaises(ContractError):
                    goal(probe, invalid)

    def test_probe_shape_and_source_are_strict_at_boundary(self):
        valid = self.probe()
        wrong_shape = to_data(valid)
        wrong_shape["extra"] = True
        invalid = [wrong_shape, replace(valid, id=1), replace(valid, source_refs=()),
                   replace(valid, source_refs=(replace(self.source, source=replace(self.source.source,
                                                                                  content_hash="bad")),)),
                   replace(valid, source_refs=(replace(self.source, locator=""),))]
        for probe in invalid:
            with self.subTest(probe=probe):
                with self.assertRaises(ContractError):
                    observe(self.graph, probe)
                with self.assertRaises(ContractError):
                    goal(probe, True)


if __name__ == "__main__":
    unittest.main()
