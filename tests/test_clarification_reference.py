"""Preauthored answer goals, evaluated independently of method observations."""
import json
from pathlib import Path
import unittest

from clarification import load_example, run_clarification
from modelspine_protocols import ArtifactRef, decode, digest, ref
from support.task_oracle import evaluate_candidate, pin_evaluation_spec

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "clarification"


class ClarificationReferenceTests(unittest.TestCase):
    def test_fixed_reference_accepts_selected_and_rejects_other_interpretation(self):
        index = json.loads((FIXTURES / "reference-index.json").read_text())
        for profile, name in (("structural-graph", "graph-reference.json"),
                              ("finite-automaton", "automaton-reference.json")):
            with self.subTest(profile=profile):
                pinned = pin_evaluation_spec((FIXTURES / name).read_bytes(), decode(ArtifactRef, index[name]))
                result = run_clarification(*load_example(profile))
                self.assertIsNotNone(result.run.commit)
                before = digest(result.run.accepted)
                accepted = evaluate_candidate(result.run.accepted, pinned)
                self.assertEqual(accepted.task_ref, result.derivation.successor)
                self.assertEqual(accepted.candidate_ref, result.run.commit.snapshot)
                self.assertTrue(accepted.satisfied)
                rejected = next(c.snapshot for c in result.session.candidates
                                if c.interpretation_id not in result.session.remaining)
                negative = evaluate_candidate(rejected, pinned)
                self.assertFalse(negative.satisfied)
                self.assertEqual(negative.candidate_ref, ref(rejected))
                self.assertEqual([o.status for o in negative.outcomes], ["satisfied", "satisfied", "violated"])
                self.assertEqual(digest(result.run.accepted), before)


if __name__ == "__main__":
    unittest.main()
