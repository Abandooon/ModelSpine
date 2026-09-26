"""Application integrity and the acceptance boundary after bounded construction."""
from dataclasses import replace
from hashlib import sha256
import unittest
from unittest.mock import patch

import bounded_generation
from bounded_generation import load_example, run_construction
from dag_construction import DagEditSpace
from task_checks import check_tasks
from modelspine_generation.bounded import ConstructionDecision
from modelspine_protocols import ContractError, digest, dumps, loads, properties


def repin(raw, reference, **changes):
    space = replace(loads(DagEditSpace, raw.decode("utf-8")), **changes)
    raw = dumps(space).encode("utf-8")
    return raw, replace(reference, content_hash=sha256(raw).hexdigest())


class BoundedGenerationTests(unittest.TestCase):
    def test_precontrol_terminal_rejection_and_real_task_commit(self):
        prepared, meta, snapshot, raw, reference = load_example()
        before = digest(snapshot)
        result = run_construction(prepared, meta, snapshot, raw, reference)
        self.assertEqual(result.space_ref, reference)
        self.assertEqual(result.search.status, "candidate_found")
        self.assertEqual([s.decision.status for s in result.search.steps], ["exclude", "allow", "allow"])
        self.assertIsNone(result.search.steps[0].proposal)
        self.assertFalse(result.search.steps[1].evaluation.report.satisfied)
        self.assertTrue(result.search.steps[2].evaluation.report.satisfied)
        self.assertIsNotNone(result.run.commit)
        self.assertEqual(result.run.accepted, result.search.steps[-1].evaluation.candidate)
        self.assertEqual(result.run.assessment.task_ref, prepared.task_ref)
        edge = next(e for e in result.run.accepted.elements if e.id == "edge-bc")
        self.assertEqual(properties(edge.properties), {"source": "node-a", "target": "node-c"})
        self.assertEqual(edge.dependencies, ("node-a", "node-c"))
        self.assertEqual(digest(snapshot), before)
        self.assertEqual(result.run.accepted.revision, snapshot.revision + 1)

    def test_raw_hash_identity_task_and_base_are_pinned(self):
        prepared, meta, snapshot, raw, reference = load_example()
        bad_inputs = [
            (raw + b" ", reference),
            repin(raw, reference, id="different-space"),
            repin(raw, reference, task_ref=replace(prepared.task_ref, revision="other")),
            repin(raw, reference, base=replace(prepared.contract.base, revision=1)),
        ]
        for altered, expected in bad_inputs:
            with self.subTest(raw=altered[-40:]), self.assertRaises(ContractError):
                run_construction(prepared, meta, snapshot, altered, expected)

    def test_non_utf8_space_is_an_explicit_error(self):
        prepared, meta, snapshot, _, reference = load_example()
        raw = b"\xff"
        reference = replace(reference, content_hash=sha256(raw).hexdigest())
        with self.assertRaisesRegex(ContractError, "UTF-8"):
            run_construction(prepared, meta, snapshot, raw, reference)

    def test_controller_and_plan_cannot_be_partially_overridden(self):
        inputs = load_example()
        for override in ({"controller": lambda option: None}, {"construction_plan": object()}):
            with self.subTest(override=override), self.assertRaisesRegex(ContractError, "together"):
                run_construction(*inputs, **override)

    def test_unknown_control_stops_without_fallback_or_commit(self):
        inputs = load_example()
        plan = run_construction(*inputs).search.plan
        result = run_construction(*inputs, construction_plan=plan,
                                  controller=lambda o: ConstructionDecision(digest(o), "unknown", "unavailable"))
        self.assertEqual(result.search.status, "unknown")
        self.assertEqual(len(result.search.steps), 1)
        self.assertIsNone(result.search.steps[0].proposal)
        self.assertIsNone(result.run)

    def test_checker_exception_propagates(self):
        with patch.object(bounded_generation, "check_tasks", side_effect=OSError("checker unavailable")):
            with self.assertRaisesRegex(OSError, "checker unavailable"):
                run_construction(*load_example())

    def test_found_candidate_does_not_bypass_final_acceptance(self):
        inputs = load_example()
        calls = 0

        def final_failure(candidate, plan, scope=None):
            nonlocal calls
            calls += 1
            report = check_tasks(candidate, plan, scope)
            if calls == 3:
                return replace(report, outcomes=(replace(report.outcomes[0], status="violated",
                                                          findings=("injected final check failure",)),
                                                 *report.outcomes[1:]))
            return report

        with patch.object(bounded_generation, "check_tasks", side_effect=final_failure):
            result = run_construction(*inputs)
        self.assertEqual(result.search.status, "candidate_found")
        self.assertEqual(result.run.assessment.goal_status, "violated")
        self.assertIsNone(result.run.commit)
        self.assertEqual(result.run.accepted, inputs[2])


if __name__ == "__main__":
    unittest.main()
