"""Public clarification boundaries with a tiny, explicitly trusted model host."""
import unittest
from dataclasses import replace
from hashlib import sha256

from modelspine_protocols import (
    ArtifactRef, ContractError, Element, EvidenceRef, FieldSpec, ImpactSet,
    KindSpec, Metamodel, MetamodelRef, Obligation, Preview, Property,
    SetProperty, Snapshot, digest, dumps, ref, to_data,
)
from modelspine_requirements import (
    AnswerRecord, Budget, ClarificationCase, EvidenceNeed, Interpretation,
    Observation, Probe, answer, artifact, prepare, propose,
)


class RequirementsTests(unittest.TestCase):
    def setUp(self):
        self.meta = Metamodel(MetamodelRef("choice", "1"),
                              (KindSpec("Choice", (FieldSpec("value", "integer"),)),))
        self.snapshot = Snapshot("project", "model", 0, self.meta.ref, digest(self.meta),
                                 (Element("choice", "Choice", "choice", None,
                                          (Property("value", -1),), (), True,
                                          "hypothesis", False, ()),))
        self.source_raw = b"Choose an observable behavior.\nSource is explicit, not inferred.\n"
        self.source_ref = ArtifactRef("project", "source", "1", sha256(self.source_raw).hexdigest())
        self.evidence = EvidenceRef(self.source_ref, "lines:1-2", "test-input")
        self.sources = {self.source_ref: self.source_raw}
        self.task_ref, _ = artifact({"goal": "awaiting clarification"}, "project", "task", "1")
        self.successor_ref, _ = artifact({"goal": "explicit answer"}, "project", "task", "2")
        self.preview_calls = []
        self.observe_calls = []
        self.matrix = {"choice": {0: False, 1: True}}
        self.case = self.make_case()

    def make_case(self, count=2, probe_ids=("choice",), budget=Budget(8, 128, 8)):
        interpretations = tuple(
            Interpretation(f"i{i}", f"Choose behavior {i}",
                           (SetProperty("set_property", "choice", "value", i),), (self.evidence,))
            for i in range(count))
        probes = tuple(Probe(name, f"Observe {name}",
                             Obligation(name, "1", "test-choice", "choice", "value", ()),
                             (self.evidence,)) for name in probe_ids)
        return ClarificationCase("clarification-case/0.1", "case", "1", self.task_ref,
                                 ref(self.snapshot),
                                 (EvidenceNeed("need", "Desired behavior", (self.evidence,), None),),
                                 interpretations, probes, budget)

    def preview(self, proposal):
        self.preview_calls.append(proposal)
        self.assertEqual(proposal.base, ref(self.snapshot))
        self.assertEqual(len(proposal.operations), 1)
        operation = proposal.operations[0]
        self.assertIsInstance(operation, SetProperty)
        element = replace(self.snapshot.elements[0], properties=(Property("value", operation.value),))
        candidate = replace(self.snapshot, revision=1, elements=(element,))
        return Preview(digest(proposal), digest(candidate), candidate,
                       ImpactSet(("choice",), (), ()))

    def observe(self, snapshot, probe):
        self.observe_calls.append((snapshot, probe))
        value = self.matrix[probe.id][snapshot.elements[0].properties[0].value]
        return Observation(ref(snapshot), digest(probe),
                           "unknown" if value is None else "observed", value,
                           "not decidable in the declared scope" if value is None else "")

    def start(self, case=None, **overrides):
        case = self.case if case is None else case
        case_ref, raw = artifact(case, "project", case.id, case.version)
        arguments = dict(raw=raw, expected_ref=case_ref, task_ref=self.task_ref,
                         metamodel=self.meta, snapshot=self.snapshot, sources=self.sources,
                         preview=self.preview, observe=self.observe)
        arguments.update(overrides)
        return prepare(**arguments)

    def answer_bytes(self, question, status="answered", value=True, identity="answer-1", actor="tester"):
        record = AnswerRecord("clarification-answer/0.1", identity, "1", digest(question), status, value, actor)
        answer_ref, raw = artifact(record, "project", record.id, record.version)
        return raw, answer_ref

    def respond(self, session, **kwargs):
        raw, answer_ref = self.answer_bytes(session.question, **kwargs)
        return answer(session, session.question, raw, answer_ref)

    def test_answer_resolves_without_mutating_model_and_proposal_preserves_provenance(self):
        session = self.start()
        self.assertEqual(session.status, "awaiting_answer")
        self.assertEqual(session.remaining, ("i0", "i1"))
        self.assertEqual((session.observations_used, session.questions_used), (2, 1))
        resolved = self.respond(session)
        self.assertEqual((resolved.status, resolved.remaining), ("ready", ("i1",)))
        self.assertEqual(session.remaining, ("i0", "i1"))
        self.assertEqual(self.snapshot.elements[0].properties[0].value, -1)
        proposal = propose(resolved, self.successor_ref)
        self.assertEqual(proposal.base, ref(self.snapshot))
        self.assertEqual(proposal.operations, self.case.interpretations[1].operations)
        question_ref, _ = artifact(session.question, "project", session.question.id, session.question.version)
        references = {e.source for e in proposal.intent_refs}
        self.assertTrue({self.source_ref, session.case_ref, question_ref,
                         resolved.answers[0].answer_ref, self.successor_ref} <= references)

    def test_case_hash_pins_raw_bytes_not_only_parsed_json(self):
        case_ref, raw = artifact(self.case, "project", self.case.id, self.case.version)
        with self.assertRaisesRegex(ContractError, "artifact hash mismatch"):
            self.start(raw=raw + b"\n", expected_ref=case_ref)
        raw += b"\n"
        session = self.start(raw=raw, expected_ref=replace(case_ref, content_hash=sha256(raw).hexdigest()))
        self.assertEqual(session.status, "awaiting_answer")

    def test_case_unknown_nested_fields_duplicate_json_and_invalid_encoding_rejected(self):
        data = to_data(self.case)
        data["interpretations"][0]["confidence"] = 99
        valid_raw = dumps(self.case).encode()
        for raw in (dumps(data).encode(), valid_raw.replace(b'"id":"case"', b'"id":"case","id":"case"'), b"\xff"):
            with self.subTest(raw=raw[:30]):
                expected = ArtifactRef("project", "case", "1", sha256(raw).hexdigest())
                with self.assertRaises(ContractError):
                    self.start(raw=raw, expected_ref=expected)

    def test_case_identity_task_base_and_project_are_pinned(self):
        for overrides in (
            {"expected_ref": artifact(self.case, "project", "another-case", "1")[0]},
            {"expected_ref": artifact(self.case, "project", "case", "2")[0]},
            {"expected_ref": artifact(self.case, "other", "case", "1")[0]},
            {"task_ref": replace(self.task_ref, revision="2")},
            {"snapshot": replace(self.snapshot, revision=1)},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ContractError):
                self.start(**overrides)

    def test_duplicate_need_interpretation_and_probe_ids_rejected(self):
        for field in ("needs", "interpretations", "probes"):
            items = getattr(self.case, field)
            case = replace(self.case, **{field: items + (items[0],)})
            with self.subTest(field=field), self.assertRaisesRegex(ContractError, "duplicate clarification ID"):
                self.start(case)

    def test_missing_modified_and_nonraw_sources_rejected(self):
        for sources, message in (({}, "source missing"),
                                 ({self.source_ref: self.source_raw + b"changed"}, "source hash mismatch"),
                                 ({self.source_ref: self.source_raw.decode()}, "raw bytes")):
            with self.subTest(message=message), self.assertRaisesRegex(ContractError, message):
                self.start(sources=sources)

    def test_invalid_source_locator_and_encoding_rejected(self):
        for locator in ("lines:0-1", "lines:2-1", "lines:1-3", "lines:01-1", "json:/goal"):
            need = replace(self.case.needs[0], source_refs=(replace(self.evidence, locator=locator),))
            with self.subTest(locator=locator), self.assertRaises(ContractError):
                self.start(replace(self.case, needs=(need,)))
        bad_raw = b"\xff"
        bad_ref = replace(self.source_ref, content_hash=sha256(bad_raw).hexdigest())
        need = replace(self.case.needs[0], source_refs=(replace(self.evidence, source=bad_ref),))
        with self.assertRaisesRegex(ContractError, "source must be UTF-8"):
            self.start(replace(self.case, needs=(need,)), sources={**self.sources, bad_ref: bad_raw})

    def test_pending_evidence_preserves_all_candidates_without_calling_host(self):
        need = replace(self.case.needs[0], source_refs=(), pending_reason="source unavailable")
        session = self.start(replace(self.case, needs=(need,)))
        self.assertEqual((session.status, session.reason), ("unresolved", "evidence_pending:need"))
        self.assertEqual(session.remaining, ("i0", "i1"))
        self.assertEqual((self.preview_calls, self.observe_calls), ([], []))
        with self.assertRaises(ContractError):
            propose(session, self.successor_ref)

    def test_missing_evidence_without_reason_and_unsourced_interpretations_rejected(self):
        need = replace(self.case.needs[0], source_refs=())
        interpretation = replace(self.case.interpretations[0], source_refs=())
        probe = replace(self.case.probes[0], source_refs=())
        for case in (replace(self.case, needs=(need,)),
                     replace(self.case, interpretations=(interpretation, self.case.interpretations[1])),
                     replace(self.case, probes=(probe,))):
            with self.subTest(case=case), self.assertRaises(ContractError):
                self.start(case)

    def test_candidate_budget_does_not_silently_truncate_candidates(self):
        session = self.start(replace(self.case, budget=Budget(1, 128, 8)))
        self.assertEqual(session.reason, "candidate_budget_exhausted")
        self.assertEqual(session.remaining, ("i0", "i1"))
        self.assertEqual(session.candidates, ())
        self.assertEqual((self.preview_calls, self.observe_calls), ([], []))

    def test_observation_budget_records_partial_work_without_issuing_question(self):
        session = self.start(replace(self.case, budget=Budget(2, 1, 8)))
        self.assertEqual((session.status, session.reason), ("unresolved", "observation_budget_exhausted"))
        self.assertEqual(session.observations_used, 1)
        self.assertEqual(len(self.observe_calls), 1)
        self.assertEqual(len(session.observations[0].predictions), 1)
        self.assertEqual(session.remaining, ("i0", "i1"))
        self.assertIsNone(session.question)

    def test_zero_question_budget_prevents_question(self):
        session = self.start(replace(self.case, budget=Budget(2, 2, 0)))
        self.assertEqual(session.reason, "question_budget_exhausted")
        self.assertEqual(session.questions_used, 0)
        self.assertIsNone(session.question)

    def test_negative_and_boolean_budgets_rejected(self):
        for field in ("max_candidates", "max_observations", "max_questions"):
            for value in (-1, True):
                budget = replace(self.case.budget, **{field: value})
                with self.subTest(field=field, value=value), self.assertRaises(ContractError):
                    self.start(replace(self.case, budget=budget))

    def balanced_case(self, budget=Budget(4, 12, 4)):
        self.matrix = {"a-balanced": {0: False, 1: True, 2: False, 3: True},
                       "z-balanced": {0: False, 1: False, 2: True, 3: True},
                       "0-unbalanced": {0: False, 1: True, 2: False, 3: False}}
        return self.make_case(4, ("z-balanced", "0-unbalanced", "a-balanced"), budget)

    def test_two_questions_use_minimax_and_bound_remaining_set_until_single_candidate(self):
        case = self.balanced_case(Budget(4, 12, 2))
        session = self.start(replace(case, interpretations=tuple(reversed(case.interpretations))))
        self.assertEqual(session.question.probe.id, "a-balanced")
        self.assertEqual(session.question.remaining, ("i0", "i1", "i2", "i3"))
        first_raw, first_ref = self.answer_bytes(session.question, value=False)
        second = answer(session, session.question, first_raw, first_ref)
        self.assertEqual(second.status, "awaiting_answer")
        self.assertEqual(second.remaining, ("i0", "i2"))
        self.assertEqual(second.question.probe.id, "z-balanced")
        self.assertEqual(second.question.remaining, ("i0", "i2"))
        self.assertEqual(second.question.sequence, 2)
        self.assertEqual(second.question.case_ref, session.case_ref)
        self.assertEqual(second.question.task_ref, self.task_ref)
        self.assertEqual(second.question.base, ref(self.snapshot))
        self.assertEqual(tuple((p.interpretation_id, p.observation.value)
                               for p in second.question.predictions), (("i0", False), ("i2", True)))
        with self.assertRaisesRegex(ContractError, "answer question/project mismatch"):
            answer(second, second.question, first_raw, first_ref)
        with self.assertRaisesRegex(ContractError, "identity already used"):
            self.respond(second, identity="answer-1")
        self.assertEqual(second.answers[0].answer_ref, first_ref)
        self.assertEqual(len(second.answers), 1)
        resolved = self.respond(second, identity="answer-2")
        self.assertEqual((resolved.status, resolved.remaining), ("ready", ("i2",)))
        self.assertIsNone(resolved.question)
        self.assertEqual((resolved.questions_used, resolved.observations_used), (2, 12))
        self.assertEqual(tuple(a.question.remaining for a in resolved.answers),
                         (("i0", "i1", "i2", "i3"), ("i0", "i2")))
        self.assertEqual(tuple(a.answer.value for a in resolved.answers), (False, True))
        self.assertEqual(tuple(a.answer_ref.artifact_id for a in resolved.answers), ("answer-1", "answer-2"))
        proposal = propose(resolved, self.successor_ref)
        self.assertEqual(proposal.operations, case.interpretations[2].operations)
        references = {e.source for e in proposal.intent_refs}
        for recorded in resolved.answers:
            question = recorded.question
            question_ref, _ = artifact(question, "project", question.id, question.version)
            self.assertIn(question_ref, references)
            self.assertIn(recorded.answer_ref, references)
        self.assertEqual(len(self.preview_calls), 4)
        self.assertEqual(len(self.observe_calls), 12)

    def test_question_budget_exhaustion_keeps_unresolved_interpretations_and_answer(self):
        session = self.start(self.balanced_case(Budget(4, 12, 1)))
        result = self.respond(session, value=False)
        self.assertEqual((result.status, result.reason), ("unresolved", "question_budget_exhausted"))
        self.assertEqual(result.remaining, ("i0", "i2"))
        self.assertEqual(len(result.answers), 1)
        self.assertIsNone(result.question)
        self.assertEqual((result.questions_used, result.observations_used), (1, 12))
        self.assertEqual((len(self.preview_calls), len(self.observe_calls)), (4, 12))
        with self.assertRaises(ContractError):
            propose(result, self.successor_ref)

    def test_unknown_and_error_observations_never_eliminate_candidates(self):
        for status in ("unknown", "error"):
            def observer(snapshot, probe):
                if snapshot.elements[0].properties[0].value == 0:
                    return Observation(ref(snapshot), digest(probe), status, None, "unavailable")
                return self.observe(snapshot, probe)
            with self.subTest(status=status):
                session = self.start(observe=observer)
                self.assertEqual((session.status, session.reason), ("unresolved", "no_distinguishing_probe"))
                self.assertEqual(session.remaining, ("i0", "i1"))
                self.assertIsNone(session.question)

    def test_unknown_probe_is_skipped_when_another_probe_distinguishes(self):
        self.matrix = {"a-unknown": {0: None, 1: True}, "z-known": {0: False, 1: True}}
        session = self.start(self.make_case(probe_ids=("a-unknown", "z-known")))
        self.assertEqual(session.question.probe.id, "z-known")
        self.assertEqual(session.remaining, ("i0", "i1"))

    def test_identical_behavior_and_no_probes_do_not_confirm_an_interpretation(self):
        self.matrix["choice"] = {0: True, 1: True}
        for case in (self.case, replace(self.case, probes=())):
            with self.subTest(probe_count=len(case.probes)):
                session = self.start(case)
                self.assertEqual((session.status, session.reason), ("unresolved", "no_distinguishing_probe"))
                self.assertEqual(session.remaining, ("i0", "i1"))

    def test_refusal_and_conflict_are_recorded_and_terminal_without_selection(self):
        for status in ("refused", "conflicted"):
            with self.subTest(status=status):
                session = self.start()
                result = self.respond(session, status=status, value=None)
                self.assertEqual((result.status, result.reason), ("unresolved", "answer_" + status))
                self.assertEqual(result.remaining, session.remaining)
                self.assertEqual(len(result.answers), 1)
                self.assertEqual(session.answers, ())
                with self.assertRaises(ContractError):
                    propose(result, self.successor_ref)

    def test_stale_altered_and_replayed_questions_rejected(self):
        session = self.start(self.balanced_case())
        second = self.respond(session, value=False)
        raw, answer_ref = self.answer_bytes(session.question)
        with self.assertRaisesRegex(ContractError, "stale or altered question"):
            answer(second, session.question, raw, answer_ref)
        for question in (replace(session.question, version="2"),
                         replace(session.question, remaining=("i0", "i1")),
                         replace(session.question, predictions=tuple(reversed(session.question.predictions))),
                         replace(session.question, probe=replace(session.question.probe, text="Changed question"))):
            with self.subTest(question=question), self.assertRaisesRegex(ContractError, "stale or altered question"):
                raw, answer_ref = self.answer_bytes(question)
                answer(session, question, raw, answer_ref)
        with self.assertRaisesRegex(ContractError, "identity already used"):
            self.respond(second, identity="answer-1")
        resolved = self.respond(second, identity="answer-2")
        with self.assertRaisesRegex(ContractError, "not awaiting answer"):
            answer(resolved, second.question, *self.answer_bytes(second.question, identity="answer-3"))

    def test_question_integer_fields_do_not_accept_equal_booleans(self):
        session = self.start()
        for question in (replace(session.question, sequence=True),
                         replace(session.question, base=replace(session.question.base, revision=False))):
            with self.subTest(question=question), self.assertRaises(ContractError):
                answer(session, question, *self.answer_bytes(question))

    def test_answer_is_bound_to_case_version_candidate_operations_and_probe_set(self):
        original = self.start()
        raw, answer_ref = self.answer_bytes(original.question)
        changed_interpretation = replace(self.case.interpretations[1], text="Explicitly revised assumption")
        changed_operation = replace(self.case.interpretations[1], operations=(SetProperty("set_property", "choice", "value", 2),))
        self.matrix["choice"][2] = True
        self.matrix["extra"] = {0: True, 1: True}
        extra_probe = replace(self.case.probes[0], id="extra")
        variants = (
            replace(self.case, version="2"),
            replace(self.case, interpretations=(self.case.interpretations[0], changed_interpretation)),
            replace(self.case, interpretations=(self.case.interpretations[0], changed_operation)),
            replace(self.case, probes=self.case.probes + (extra_probe,)),
        )
        for case in variants:
            with self.subTest(case=case):
                session = self.start(case)
                with self.assertRaisesRegex(ContractError, "answer question/project mismatch"):
                    answer(session, session.question, raw, answer_ref)

    def test_answer_status_value_actor_hash_project_and_shape_are_strict(self):
        session = self.start()
        for options in ({"status": "answered", "value": None},
                        {"status": "refused", "value": False},
                        {"status": "conflicted", "value": True},
                        {"value": 1}, {"actor": "  "}):
            with self.subTest(options=options), self.assertRaises(ContractError):
                self.respond(session, **options)
        raw, answer_ref = self.answer_bytes(session.question)
        with self.assertRaisesRegex(ContractError, "artifact hash mismatch"):
            answer(session, session.question, raw + b" ", answer_ref)
        with self.assertRaisesRegex(ContractError, "answer question/project mismatch"):
            answer(session, session.question, raw, replace(answer_ref, project_id="other"))
        record = to_data(AnswerRecord("clarification-answer/0.1", "answer", "1",
                                     digest(session.question), "answered", True, "tester"))
        record["confidence"] = 1
        malformed_ref, malformed_raw = artifact(record, "project", "answer", "1")
        with self.assertRaises(ContractError):
            answer(session, session.question, malformed_raw, malformed_ref)

    def test_no_change_requires_answer_and_returns_no_proposal(self):
        self.matrix["choice"][-1] = False
        unchanged = replace(self.case.interpretations[0], operations=())
        session = self.start(replace(self.case, interpretations=(unchanged, self.case.interpretations[1])))
        self.assertEqual(len(self.preview_calls), 1)
        self.assertEqual(session.status, "awaiting_answer")
        result = self.respond(session, value=False)
        self.assertEqual((result.status, result.reason), ("no_change", "answer_resolved_no_change"))
        self.assertIsNone(propose(result, self.successor_ref))

    def test_proposal_requires_distinct_task_revision_with_same_identity(self):
        session = self.respond(self.start())
        for successor in (self.task_ref, replace(self.successor_ref, project_id="other"),
                          replace(self.successor_ref, artifact_id="other"),
                          replace(self.successor_ref, content_hash="invalid")):
            with self.subTest(successor=successor), self.assertRaises(ContractError):
                propose(session, successor)

    def test_callback_exceptions_are_not_converted_to_empty_or_success(self):
        error = RuntimeError("callback unavailable")
        def fail(*args):
            raise error
        for callback in ("preview", "observe"):
            with self.subTest(callback=callback), self.assertRaises(RuntimeError) as caught:
                self.start(**{callback: fail})
            self.assertIs(caught.exception, error)

    def test_preview_hashes_identity_and_model_shape_are_checked(self):
        def wrong_proposal(result):
            return replace(result, proposal_hash="0" * 64)
        def wrong_hash(result):
            return replace(result, candidate_hash="0" * 64)
        def wrong_revision(result):
            candidate = replace(result.candidate, revision=2)
            return replace(result, candidate=candidate, candidate_hash=digest(candidate))
        def wrong_model(result):
            element = replace(result.candidate.elements[0], properties=(Property("value", True),))
            candidate = replace(result.candidate, elements=(element,))
            return replace(result, candidate=candidate, candidate_hash=digest(candidate))
        for corrupt in (wrong_proposal, wrong_hash, wrong_revision, wrong_model):
            with self.subTest(corrupt=corrupt.__name__), self.assertRaises(ContractError):
                self.start(preview=lambda proposal: corrupt(self.preview(proposal)))

    def test_observation_bindings_status_value_reason_and_boolean_type_are_checked(self):
        changes = ({"candidate": ref(self.snapshot)}, {"probe_hash": "0" * 64},
                   {"status": "unknown"}, {"value": None}, {"value": 1},
                   {"status": "error", "value": None, "reason": ""})
        for fields in changes:
            with self.subTest(fields=fields), self.assertRaises(ContractError):
                self.start(observe=lambda snapshot, probe: replace(self.observe(snapshot, probe), **fields))


if __name__ == "__main__":
    unittest.main()
