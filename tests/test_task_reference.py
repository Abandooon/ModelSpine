"""Finite reference tests: fixed inputs, separate semantics, honest boundaries."""
import ast
import json
import sys
import unittest
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from modelspine_protocols import (
    ArtifactRef, CheckPlan, ContractError, Property, Snapshot,
    decode, digest, loads, ref,
)
from support.task_oracle import evaluate_candidate, pin_evaluation_spec

PLATFORM = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "task-acceptance"
INDEX = json.loads((FIXTURES / "reference-index.json").read_text(encoding="utf-8"))


def candidate(profile):
    return loads(Snapshot, (PLATFORM / "domain-packs" / profile / "model.json").read_text(encoding="utf-8"))


def change(snapshot, identity, **fields):
    return replace(snapshot, revision=snapshot.revision + 1, elements=tuple(
        replace(element, properties=tuple(Property(prop.name, fields.get(prop.name, prop.value))
                                          for prop in element.properties))
        if element.id == identity else element for element in snapshot.elements))


def specification(name):
    return pin_evaluation_spec((FIXTURES / name).read_bytes(), decode(ArtifactRef, INDEX[name]))


def authored_variant(original, modify):
    """Test-author changes establish a new expectation before candidate execution."""
    document = json.loads(original.content)
    modify(document)
    content = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    reference = replace(original.spec_ref, content_hash=sha256(content).hexdigest())
    return pin_evaluation_spec(content, reference)


class TaskReferenceTests(unittest.TestCase):
    def test_correct_graph_and_automaton_have_bound_complete_results_without_mutation(self):
        for profile, filename in (("structural-graph", "graph-reference.json"),
                                  ("finite-automaton", "automaton-reference.json")):
            with self.subTest(profile=profile):
                snapshot = candidate(profile)
                before = digest(snapshot)
                spec = specification(filename)
                result = evaluate_candidate(snapshot, spec)
                self.assertTrue(result.satisfied)
                self.assertEqual(result.spec_ref, spec.spec_ref)
                self.assertEqual(result.candidate_ref, ref(snapshot))
                self.assertEqual(len(result.outcomes), len(json.loads(spec.content)["cases"]))
                self.assertEqual(digest(snapshot), before)

    def test_fixed_inputs_ignore_editable_candidate_trace_and_detect_changed_behavior(self):
        original = candidate("finite-automaton")
        spec = specification("automaton-reference.json")
        altered_trace = change(original, "machine", trace="aa")
        self.assertTrue(evaluate_candidate(altered_trace, spec).satisfied)
        altered_both = change(altered_trace, "step-b", symbol="a")
        result = evaluate_candidate(altered_both, spec)
        self.assertEqual([o.status for o in result.outcomes[:2]], ["violated", "violated"])

    def test_well_bound_common_error_can_pass_development_but_fail_reference(self):
        # Only this comparison test calls the public development checker. The
        # reference module never imports it, its helpers, or its plan semantics.
        sys.path.insert(0, str(PLATFORM / "adapters"))
        from finite_models import check_automaton
        snapshot = change(change(candidate("finite-automaton"), "step-b", symbol="a"),
                          "machine", trace="aa")
        plan = loads(CheckPlan, (PLATFORM / "domain-packs" / "finite-automaton" /
                                "obligations.json").read_text(encoding="utf-8"))
        development = check_automaton(snapshot, plan)
        self.assertTrue(development.satisfied)
        self.assertEqual(development.binding.candidate_hash, digest(snapshot))
        self.assertEqual(development.binding.plan_hash, digest(plan))
        self.assertEqual({o.obligation_id for o in development.outcomes}, {o.id for o in plan.obligations})
        self.assertFalse(evaluate_candidate(snapshot, specification("automaton-reference.json")).satisfied)

    def test_reachability_change_is_caught_even_while_graph_remains_acyclic(self):
        snapshot = change(candidate("structural-graph"), "edge-bc", target="node-b")
        # Replace the second edge by a parallel A->B edge: still a DAG, no A->C.
        snapshot = change(snapshot, "edge-bc", source="node-a")
        result = evaluate_candidate(snapshot, specification("graph-reference.json"))
        self.assertEqual(result.outcomes[0].status, "violated")
        self.assertEqual(result.outcomes[1].status, "satisfied")

    def test_changed_specification_cannot_supply_its_own_new_hash(self):
        original = specification("automaton-reference.json")
        edited = json.loads(original.content)
        edited["cases"][0]["input"] = "aa"
        edited["cases"][1]["expected"] = True
        altered = json.dumps(edited).encode("utf-8")
        with self.assertRaises(ContractError):
            pin_evaluation_spec(altered, original.spec_ref)
        with self.assertRaises(ContractError):
            evaluate_candidate(candidate("finite-automaton"), replace(original, content=altered))
        # Even a formatting-only mutation differs from the externally pinned bytes.
        with self.assertRaises(ContractError):
            pin_evaluation_spec(original.content + b"\n", original.spec_ref)

    def test_specification_hash_does_not_replace_identity_or_strict_schema_checks(self):
        original = specification("automaton-reference.json")
        with self.assertRaises(ContractError):
            pin_evaluation_spec(original.content, replace(original.spec_ref, revision="other"))
        with self.assertRaises(ContractError):
            authored_variant(original, lambda data: data.update(content_hash="self-reported"))
        with self.assertRaises(ContractError):
            authored_variant(original, lambda data: data["cases"].append(data["cases"][0]))
        with self.assertRaises(ContractError):
            authored_variant(original, lambda data: data["cases"][0].update(expected=1))

    def test_cross_model_and_metamodel_candidates_are_rejected(self):
        snapshot = candidate("finite-automaton")
        spec = specification("automaton-reference.json")
        for altered in (replace(snapshot, model_id="other"), replace(snapshot, project_id="other"),
                        replace(snapshot, metamodel_hash="f" * 64),
                        replace(snapshot, metamodel=replace(snapshot.metamodel, version="future"))):
            with self.subTest(candidate=altered):
                with self.assertRaises(ContractError):
                    evaluate_candidate(altered, spec)

    def test_invalid_machine_cannot_satisfy_negative_expectation(self):
        original = candidate("finite-automaton")
        negatives = authored_variant(specification("automaton-reference.json"),
            lambda data: data.update(cases=[data["cases"][1]]))
        invalid = [change(original, "step-b", target="missing"),
                   change(change(original, "step-b", source="s0"), "step-b", symbol="a"),
                   change(original, "step-b", symbol="ab"),
                   change(original, "step-b", symbol=""),
                   change(original, "s2", accepting="false")]
        for altered in invalid:
            with self.subTest(candidate=altered):
                result = evaluate_candidate(altered, negatives)
                self.assertFalse(result.satisfied)
                self.assertIn(result.outcomes[0].status, ("violated", "error"))

    def test_nested_members_and_parent_cycles_are_not_silently_ignored(self):
        for profile, filename, parent in (("structural-graph", "graph-reference.json", "node-a"),
                                           ("finite-automaton", "automaton-reference.json", "s0")):
            original = candidate(profile)
            nested = replace(original.elements[-1], id="nested", parent=parent)
            altered = replace(original, elements=original.elements + (nested,))
            result = evaluate_candidate(altered, specification(filename))
            self.assertTrue(all(o.status == "violated" for o in result.outcomes))
            members = list(original.elements)
            members[1] = replace(members[1], parent=members[2].id)
            members[2] = replace(members[2], parent=members[1].id)
            result = evaluate_candidate(replace(original, elements=tuple(members)), specification(filename))
            self.assertTrue(all(o.status == "error" for o in result.outcomes))

    def test_missing_truth_and_unsupported_semantics_remain_unknown(self):
        original = specification("automaton-reference.json")
        variants = [authored_variant(original, lambda data: data["cases"][0].update(expected=None)),
                    authored_variant(original, lambda data: data["cases"][0].update(kind="temporal_logic"))]
        for spec in variants:
            result = evaluate_candidate(candidate("finite-automaton"), spec)
            self.assertFalse(result.satisfied)
            self.assertEqual(result.outcomes[0].status, "unknown")
            self.assertEqual(len(result.outcomes), 2)

    def test_outside_alphabet_is_unknown_even_for_negative_expectation(self):
        spec = authored_variant(specification("automaton-reference.json"),
            lambda data: data.update(cases=[dict(data["cases"][1], input="ac")]))
        result = evaluate_candidate(candidate("finite-automaton"), spec)
        self.assertFalse(result.satisfied)
        self.assertEqual(result.outcomes[0].status, "unknown")
        self.assertEqual(result.outcomes[0].finding, "input_outside_supported_alphabet")

    def test_reference_module_cannot_import_development_or_study_helpers(self):
        source = Path(__file__).with_name("support") / "task_oracle.py"
        parsed = ast.parse(source.read_text(encoding="utf-8"))
        allowed = {"collections", "dataclasses", "hashlib", "modelspine_protocols"}
        roots = set()
        for node in ast.walk(parsed):
            if isinstance(node, ast.Import):
                roots.update(name.name.split(".")[0] for name in node.names)
            elif isinstance(node, ast.ImportFrom):
                roots.add(node.module.split(".")[0])
        self.assertLessEqual(roots, allowed)


if __name__ == "__main__":
    unittest.main()
