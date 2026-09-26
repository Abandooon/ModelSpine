"""Finite clarification preserves parent goals, provenance, and final checks."""
from dataclasses import replace
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from clarification import derive_task, load_example, run_clarification
from clarification_checks import observe
from modelspine_assurance.tasks import prepare_task
from modelspine_protocols import (
    ContractError, Property, SetDependencies, SetProperty, TaskContract,
    digest, loads, properties, ref, to_data,
)
from modelspine_requirements import AnswerRecord, ClarificationCase, artifact, propose


class ClarificationIntegrationTests(unittest.TestCase):
    def replace_case(self, args, case):
        updated = list(args)
        updated[3], updated[2] = artifact(case, args[3].project_id, case.id, case.version)
        updated[5] = ()
        return updated

    def replace_parent(self, args, parent):
        updated = list(args)
        updated[1], updated[0] = artifact(parent, args[1].project_id, parent.id, parent.version)
        case = loads(ClarificationCase, args[2].decode("utf-8"))
        return self.replace_case(updated, replace(case, task_ref=updated[1]))

    def add_answer(self, args, value=True, status="answered"):
        updated = list(args)
        updated[5] = ()
        pending = run_clarification(*updated)
        self.assertEqual(pending.session.status, "awaiting_answer")
        record = AnswerRecord("clarification-answer/0.1", "test-answer", "1",
                              digest(pending.session.question), status, value, "test-author")
        answer_ref, raw = artifact(record, args[3].project_id, record.id, record.version)
        updated[5] = ((answer_ref, raw),)
        return updated

    def derivation_inputs(self, args, result):
        sources = dict(args[4])
        sources.update({args[1]: args[0], args[3]: args[2], **dict(args[5])})
        parent = prepare_task(args[0], args[1], sources)
        return parent, result.session.case, args[3], result.session.answers, args[6], sources

    def assert_stopped(self, result):
        self.assertIsNone(result.run)
        self.assertIsNone(result.successor)
        self.assertIsNone(result.derivation)

    def test_both_profiles_commit_and_preserve_parent_goals_and_derivation_sources(self):
        for profile in ("structural-graph", "finite-automaton"):
            with self.subTest(profile=profile):
                args = load_example(profile)
                parent = loads(TaskContract, args[0].decode("utf-8"))
                result = run_clarification(*args)
                self.assertEqual(result.session.status, "ready")
                self.assertEqual(len(result.session.answers), 1)
                self.assertEqual(result.session.questions_used, 1)
                self.assertIsNotNone(result.run.commit)
                self.assertEqual(result.run.accepted.revision, args[8].revision + 1)
                self.assertEqual(result.run.commit.snapshot, ref(result.run.accepted))
                self.assertEqual(result.run.assessment.candidate, result.run.commit.snapshot)
                self.assertEqual(result.run.assessment.goal_status, "satisfied")
                self.assertEqual(result.run.assessment.intent_status, "ready")
                self.assertEqual(result.successor.base, parent.base)
                self.assertNotEqual(result.successor.version, parent.version)
                self.assertNotEqual(result.successor.plan.version, parent.plan.version)
                self.assertEqual(result.successor.plan.obligations[:-1], parent.plan.obligations)
                self.assertEqual(result.successor.statements[:-1], parent.statements)
                self.assertEqual(result.successor.bindings[:-1], parent.bindings)
                self.assertEqual(result.derivation.parent, args[1])
                self.assertEqual(result.derivation.case, args[3])
                self.assertEqual(result.derivation.answers, tuple(item[0] for item in args[5]))
                self.assertEqual(result.derivation.successor, result.run.assessment.task_ref)
                added = result.successor.statements[-1]
                self.assertTrue(added.required)
                self.assertEqual((added.category, added.confirmation), ("intent", "confirmed"))
                source_refs = {source.source for source in added.source_refs}
                self.assertTrue({args[1], args[3], args[5][0][0]} <= source_refs)
                self.assertIn("issued-behavior-question", {source.origin for source in added.source_refs})
                final_proposal = propose(result.session, result.derivation.successor)
                self.assertTrue({args[3], args[5][0][0], result.derivation.successor}
                                <= {source.source for source in final_proposal.intent_refs})
                for recorded in result.artifacts:
                    self.assertEqual(sha256(recorded.text.encode("utf-8")).hexdigest(),
                                     recorded.reference.content_hash)
                elements = {element.id: properties(element.properties) for element in result.run.accepted.elements}
                if profile == "structural-graph":
                    self.assertEqual(elements["edge-bc"]["source"], "node-a")
                else:
                    self.assertIs(elements["s1"]["accepting"], True)

    def test_unanswered_refused_and_conflicted_inputs_do_not_run_acceptance(self):
        for profile in ("structural-graph", "finite-automaton"):
            args = list(load_example(profile))
            args[5] = ()
            with self.subTest(profile=profile, status="unanswered"), patch("clarification.run_task") as accept:
                result = run_clarification(*args)
                self.assertEqual(result.session.status, "awaiting_answer")
                self.assert_stopped(result)
                accept.assert_not_called()
            for status in ("refused", "conflicted"):
                variant = self.add_answer(args, None, status)
                with self.subTest(profile=profile, status=status), patch("clarification.run_task") as accept:
                    result = run_clarification(*variant)
                    self.assertEqual(result.session.status, "unresolved")
                    self.assertEqual(result.session.reason, "answer_" + status)
                    self.assertEqual(result.session.answers[0].answer.status, status)
                    self.assert_stopped(result)
                    accept.assert_not_called()

    def test_missing_evidence_and_exhausted_budgets_remain_unresolved(self):
        args = load_example("structural-graph")
        case = loads(ClarificationCase, args[2].decode("utf-8"))
        variants = [replace(case, needs=(replace(case.needs[0], pending_reason="author source pending"),)
                                         + case.needs[1:]),
                    replace(case, budget=replace(case.budget, max_questions=0)),
                    replace(case, budget=replace(case.budget, max_observations=0))]
        for variant in variants:
            with self.subTest(case=variant), patch("clarification.run_task") as accept:
                result = run_clarification(*self.replace_case(args, variant))
                self.assertEqual(result.session.status, "unresolved")
                self.assert_stopped(result)
                accept.assert_not_called()

    def test_confirmed_current_interpretation_checks_successor_without_commit(self):
        args = load_example("structural-graph")
        case = loads(ClarificationCase, args[2].decode("utf-8"))
        source = case.interpretations[0]
        unchanged = replace(source, id="keep-current", text="Retain current graph", operations=())
        changed = replace(source, id="remove-a-b", text="Redirect a-b to c", operations=(
            SetProperty("set_property", "edge-ab", "target", "node-c"),
            SetDependencies("set_dependencies", "edge-ab", ("node-a", "node-c"), True)))
        probe = next(probe for probe in case.probes
                     if properties(probe.obligation.parameters).get("source") == "node-a"
                     and properties(probe.obligation.parameters).get("destination") == "node-b")
        variant = replace(case, interpretations=(unchanged, changed), probes=(probe,))
        args = self.add_answer(self.replace_case(args, variant))
        with patch("clarification.run_task") as accept:
            result = run_clarification(*args)
        accept.assert_not_called()
        self.assertEqual(result.session.status, "no_change")
        self.assertEqual(result.session.remaining, ("keep-current",))
        self.assertIsNone(result.run.commit)
        self.assertEqual(result.run.accepted, args[8])
        self.assertEqual(result.run.assessment.goal_status, "satisfied")
        self.assertEqual(result.run.assessment.task_ref, result.derivation.successor)

    def test_semantically_wrong_observations_cannot_bypass_final_goal_check(self):
        def flipped(snapshot, probe):
            actual = observe(snapshot, probe)
            self.assertEqual(actual.status, "observed")
            return replace(actual, value=not actual.value, reason="injected semantic observation defect")

        for profile in ("structural-graph", "finite-automaton"):
            with self.subTest(profile=profile), patch("clarification.observe", side_effect=flipped):
                args = self.add_answer(load_example(profile))
                result = run_clarification(*args)
            self.assertEqual(result.session.status, "ready")
            self.assertEqual(result.run.assessment.goal_status, "violated")
            self.assertEqual(result.run.assessment.report.outcomes[-1].status, "violated")
            self.assertTrue(all(item.status == "satisfied" for item in result.run.assessment.report.outcomes[:-1]))
            self.assertIsNone(result.run.commit)
            self.assertIsNotNone(result.run.candidate)
            self.assertEqual(result.run.accepted, args[8])

    def test_conflicting_parent_goal_is_preserved_and_blocks_commit(self):
        args = load_example("structural-graph")
        parent = loads(TaskContract, args[0].decode("utf-8"))
        negative = replace(parent.plan.obligations[-1], parameters=(
            Property("source", "node-a"), Property("destination", "node-b"),
            Property("expected_reachable", False)))
        changed_parent = replace(parent, version="conflicting-parent",
                                 plan=replace(parent.plan, version="conflicting-parent-plan",
                                              obligations=parent.plan.obligations[:-1] + (negative,)),
                                 statements=parent.statements[:-1] + (replace(parent.statements[-1],
                                     text="Keep node-a unable to reach node-b."),))
        args = self.add_answer(self.replace_parent(args, changed_parent))
        result = run_clarification(*args)
        self.assertEqual(result.successor.plan.obligations[:-1], changed_parent.plan.obligations)
        self.assertEqual(result.run.assessment.report.outcomes[-2].status, "violated")
        self.assertEqual(result.run.assessment.report.outcomes[-1].status, "satisfied")
        self.assertIsNone(result.run.commit)
        self.assertEqual(result.run.accepted, args[8])

    def test_missing_or_changed_sources_fail_without_substitution(self):
        args = load_example("structural-graph")
        case = loads(ClarificationCase, args[2].decode("utf-8"))
        source_ref = case.interpretations[0].source_refs[0].source
        for mode, code in (("missing", "not_found"), ("changed", "conflict")):
            variant = list(args)
            variant[4] = dict(args[4])
            if mode == "missing":
                del variant[4][source_ref]
            else:
                variant[4][source_ref] += b"\nchanged"
            with self.subTest(mode=mode), self.assertRaises(ContractError) as raised:
                run_clarification(*variant)
            self.assertEqual(raised.exception.code, code)

    def test_old_answer_cannot_follow_changed_case_or_parent_version(self):
        args = load_example("finite-automaton")
        case = loads(ClarificationCase, args[2].decode("utf-8"))
        parent = loads(TaskContract, args[0].decode("utf-8"))
        variants = [self.replace_case(args, replace(case, version="changed-case")),
                    self.replace_parent(args, replace(parent, version="changed-parent"))]
        for variant in variants:
            variant[5] = args[5]
            with self.subTest(case_ref=variant[3]), self.assertRaises(ContractError) as raised:
                run_clarification(*variant)
            self.assertEqual(raised.exception.code, "conflict")

    def test_original_answer_bytes_are_retained_and_need_matching_hash(self):
        args = list(load_example("structural-graph"))
        answer_ref, raw = args[5][0]
        record = loads(AnswerRecord, raw.decode("utf-8"))
        pretty = (json.dumps(to_data(record), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        self.assertNotEqual(pretty, raw)
        args[5] = ((answer_ref, pretty),)
        with self.assertRaises(ContractError):
            run_clarification(*args)
        updated_ref = replace(answer_ref, content_hash=sha256(pretty).hexdigest())
        args[5] = ((updated_ref, pretty),)
        result = run_clarification(*args)
        self.assertIsNotNone(result.run.commit)
        recorded = next(item for item in result.artifacts if item.reference == updated_ref)
        self.assertEqual(recorded.text.encode("utf-8"), pretty)
        self.assertEqual(result.derivation.answers, (updated_ref,))

    def test_derivation_rejects_changed_case_parent_answer_bytes_or_records(self):
        args = load_example("structural-graph")
        result = run_clarification(*args)
        inputs = self.derivation_inputs(args, result)
        for source_ref in (args[1], args[3], args[5][0][0]):
            variant = list(inputs)
            variant[5] = dict(inputs[5])
            variant[5][source_ref] += b"\n"
            with self.subTest(source=source_ref.artifact_id), self.assertRaises(ContractError):
                derive_task(*variant)
        variant = list(inputs)
        variant[1] = replace(inputs[1], version="different-case-object")
        with self.assertRaises(ContractError):
            derive_task(*variant)
        variant = list(inputs)
        answered = inputs[3][0]
        variant[3] = (replace(answered, answer=replace(answered.answer, value=False)),)
        with self.assertRaises(ContractError):
            derive_task(*variant)
        variant = list(inputs)
        variant[5] = dict(inputs[5])
        del variant[5][answered.answer_ref]
        with self.assertRaises(ContractError) as raised:
            derive_task(*variant)
        self.assertEqual(raised.exception.code, "not_found")

    def test_successor_version_must_differ_from_both_parent_task_and_plan(self):
        args = load_example("structural-graph")
        parent = loads(TaskContract, args[0].decode("utf-8"))
        parent = replace(parent, version="parent-task", plan=replace(parent.plan, version="parent-plan"))
        args = self.add_answer(self.replace_parent(args, parent))
        result = run_clarification(*args)
        inputs = self.derivation_inputs(args, result)
        for version in ("parent-task", "parent-plan", " "):
            variant = list(inputs)
            variant[4] = version
            with self.subTest(version=version), self.assertRaises(ContractError):
                derive_task(*variant)


if __name__ == "__main__":
    unittest.main()
