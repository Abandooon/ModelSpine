"""Candidate selection is a pinned host input, never a backend success receipt."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps"))
import bounded_generation as app
import candidate_batch as batch
from dag_construction import DagEditSpace
from modelspine_generation.bounded import ConstructionDecision
from modelspine_protocols import (
    ContractError, GenerationControl, GenerationPlan, digest, dumps, loads, properties, to_data,
)
from task_acceptance import EngineeringTaskCard


class CandidateBatchTests(unittest.TestCase):
    def setUp(self):
        self.inputs = app.load_example()
        folder = ROOT / "domain-packs/structural-graph/tasks"
        card = loads(EngineeringTaskCard, (folder / "card.json").read_text(encoding="utf-8"))
        self.sources = {item.ref: (folder / item.path).read_bytes() for item in card.sources}
        self.limits = batch.CandidateLimits(9, 3, 100000, 10000)
        self.request = self.prepare()

    def prepare(self, inputs=None, sources=None, limits=None):
        return batch.prepare_candidate_request(
            self.inputs if inputs is None else inputs, self.sources if sources is None else sources,
            request_id="host-batch-test", limits=self.limits if limits is None else limits)

    def option_id(self, source, target, request=None):
        request = self.request if request is None else request
        return next(option.id for option in request.options
                    if properties(option.values) == {"source": source, "target": target})

    def payload(self, ids, request=None):
        request = self.request if request is None else request
        return json.dumps({"schema_version": "candidate-selection/0.1", "request_id": request.request_id,
                           "option_ids": list(ids)}, separators=(",", ":")).encode("utf-8")

    def selection(self, ids, request=None):
        request = self.request if request is None else request
        return batch.parse_candidate_selection(request, self.payload(ids, request))

    def changed_space(self, **changes):
        prepared, meta, snapshot, raw, reference = self.inputs
        space = replace(loads(DagEditSpace, raw.decode("utf-8")), **changes)
        raw = dumps(space).encode("utf-8")
        return prepared, meta, snapshot, raw, replace(reference, content_hash=sha256(raw).hexdigest())

    def test_request_contains_verified_source_fragments_and_an_unlabelled_complete_catalog(self):
        self.assertEqual(len(self.request.options), 9)
        self.assertEqual(self.request.catalog_hash, digest(self.request.options))
        evidence = tuple(dict.fromkeys(e for statement in self.inputs[0].contract.statements
                                      for e in statement.source_refs))
        self.assertEqual(tuple(fragment.evidence for fragment in self.request.source_fragments), evidence)
        for fragment in self.request.source_fragments:
            start, end = map(int, fragment.evidence.locator.removeprefix("lines:").split("-"))
            lines = self.sources[fragment.evidence.source].decode("utf-8").splitlines()
            self.assertEqual(fragment.text, "\n".join(lines[start - 1:end]))
        for option in to_data(self.request)["options"]:
            self.assertEqual(set(option), {"id", "target", "values"})
        self.assertEqual(self.request.snapshot, self.inputs[2])
        self.assertEqual(self.request.task, self.inputs[0].contract)

    def test_reordered_subset_is_executed_in_response_order_and_really_saved(self):
        ids = tuple(self.option_id(source, target) for source, target in
                    (("node-c", "node-b"), ("node-a", "node-b"), ("node-a", "node-c")))
        raw = self.payload(ids)
        selection = batch.parse_candidate_selection(self.request, raw)
        result = batch.run_candidate_selection(self.inputs, self.request, selection)
        self.assertEqual(tuple(step.option.id for step in result.app_result.search.steps), ids)
        self.assertEqual(result.returned_options, 3)
        self.assertEqual(result.catalog_size, 9)
        self.assertEqual(result.max_considered_options, self.request.space.max_options)
        self.assertEqual(result.exhaustion_scope, "backend_batch")
        self.assertEqual(selection.response_hash, sha256(raw).hexdigest())
        self.assertEqual(selection.response_text.encode("utf-8"), raw)
        self.assertEqual(result.request_hash, digest(self.request))
        self.assertIsNotNone(result.app_result.run.commit)
        self.assertEqual(result.app_result.run.accepted.revision, self.inputs[2].revision + 1)
        self.assertEqual(result.app_result.run.accepted, app.run_construction(*self.inputs).run.accepted)
        self.assertEqual(self.inputs[2].revision, 0)

    def test_invalid_responses_are_rejected_as_a_whole_before_execution(self):
        option = self.request.options[0].id
        good = json.loads(self.payload((option,)))
        duplicate_key = ('{"schema_version":"candidate-selection/0.1",'
                         '"request_id":"host-batch-test","request_id":"host-batch-test","option_ids":[]}')
        variants = [b"{", b"```json\n{}\n```", duplicate_key.encode(), b"\xff",
                    json.dumps({**good, "saved": True}).encode(),
                    json.dumps({**good, "request_id": "other"}).encode(),
                    json.dumps({**good, "schema_version": "candidate-selection/other"}).encode(),
                    json.dumps({**good, "option_ids": option}).encode(),
                    json.dumps({**good, "option_ids": [True]}).encode(),
                    json.dumps({**good, "option_ids": [option, option]}).encode(),
                    json.dumps({**good, "option_ids": [item.id for item in self.request.options[:4]]}).encode(),
                    json.dumps({**good, "option_ids": [option, "outside-catalog"]}).encode(),
                    b" " * (self.limits.max_response_bytes + 1)]
        with patch.object(batch, "_execute_construction") as execute:
            for raw in variants:
                with self.subTest(response=raw[:100]), self.assertRaises(ContractError):
                    selection = batch.parse_candidate_selection(self.request, raw)
                    batch.run_candidate_selection(self.inputs, self.request, selection)
        execute.assert_not_called()

    def test_self_loop_is_a_legal_selection_and_control_still_precedes_construction(self):
        selection = self.selection((self.option_id("node-a", "node-a"),))
        dag = batch.run_candidate_selection(self.inputs, self.request, selection).app_result
        self.assertEqual(dag.search.status, "exhausted")
        self.assertEqual(dag.search.steps[0].decision.status, "exclude")
        self.assertIsNone(dag.search.steps[0].proposal)
        obligations = self.inputs[0].contract.plan.obligations
        plan = GenerationPlan(self.request.check_plan_hash, tuple(GenerationControl(
            item.id, item.version, item.kind, "terminal-only", "test complete terminal checking",
            "all obligations remain checked") for item in obligations), tuple(item.id for item in obligations))
        terminal = batch.run_candidate_selection(
            self.inputs, self.request, selection, construction_plan=plan,
            controller=lambda option: ConstructionDecision(digest(option), "allow", "terminal-only test"))
        self.assertIsNotNone(terminal.app_result.search.steps[0].proposal)
        self.assertFalse(terminal.app_result.search.steps[0].evaluation.report.satisfied)
        self.assertIsNone(terminal.app_result.run)

    def test_empty_and_unchanged_batches_do_not_claim_full_space_exhaustion_or_save(self):
        for ids in ((), (self.option_id("node-b", "node-c"),)):
            with self.subTest(ids=ids):
                result = batch.run_candidate_selection(self.inputs, self.request, self.selection(ids))
                self.assertEqual(result.catalog_size, 9)
                self.assertEqual(result.returned_options, len(ids))
                self.assertEqual(result.exhaustion_scope, "backend_batch")
                self.assertEqual(result.app_result.search.status, "exhausted")
                self.assertIsNone(result.app_result.run)
                self.assertTrue(all(step.proposal is None for step in result.app_result.search.steps))

    def test_control_budget_counts_exclusions_and_does_not_expand_to_fit_the_batch(self):
        inputs = self.changed_space(max_options=2)
        request = self.prepare(inputs)
        ids = tuple(self.option_id("node-a", target, request) for target in ("node-a", "node-b", "node-c"))
        result = batch.run_candidate_selection(inputs, request, self.selection(ids, request))
        self.assertEqual(result.returned_options, 3)
        self.assertEqual(result.max_considered_options, 2)
        self.assertEqual(result.app_result.search.status, "budget_exhausted")
        self.assertEqual(len(result.app_result.search.steps), 2)
        self.assertEqual(result.app_result.search.steps[0].decision.status, "exclude")
        self.assertIsNone(result.app_result.run)

    def test_catalog_limit_is_checked_before_materialization_even_with_zero_control_budget(self):
        with patch.object(app, "prepare_dag") as prepare_dag:
            with self.assertRaisesRegex(ContractError, "catalog exceeds"):
                self.prepare(self.changed_space(max_options=0), limits=replace(self.limits, max_catalog_options=8))
        prepare_dag.assert_not_called()

    def test_source_bytes_and_request_size_are_checked_before_a_request_is_usable(self):
        source = next(iter(self.sources))
        for sources in ({}, {source: b"changed source"}, {source: b"\xff"}):
            with self.subTest(sources=sources), self.assertRaises(ContractError):
                self.prepare(sources=sources)
        with self.assertRaisesRegex(ContractError, "request exceeds byte limit"):
            self.prepare(limits=replace(self.limits, max_request_bytes=1))

    def test_source_locator_must_name_existing_lines_before_a_fragment_can_be_sent(self):
        prepared, meta, snapshot, raw, space_ref = self.inputs
        for locator in ("characters:2-3", "lines:999-999"):
            statement = prepared.contract.statements[0]
            statement = replace(statement, source_refs=(replace(statement.source_refs[0], locator=locator),))
            contract = replace(prepared.contract, statements=(statement, *prepared.contract.statements[1:]))
            task_ref = replace(prepared.task_ref, content_hash=sha256(dumps(contract).encode()).hexdigest())
            changed = replace(prepared, contract=contract, task_ref=task_ref)
            space = replace(loads(DagEditSpace, raw.decode("utf-8")), task_ref=task_ref)
            space_raw = dumps(space).encode("utf-8")
            inputs = (changed, meta, snapshot, space_raw,
                      replace(space_ref, content_hash=sha256(space_raw).hexdigest()))
            with self.subTest(locator=locator), self.assertRaises(ContractError):
                self.prepare(inputs)

    def test_request_bindings_include_task_base_space_plan_and_catalog_order(self):
        reordered = tuple(reversed(self.request.options))
        variants = (
            replace(self.request, task_ref=replace(self.request.task_ref, revision="other")),
            replace(self.request, task=replace(self.request.task, version="other")),
            replace(self.request, snapshot=replace(self.request.snapshot, revision=1)),
            replace(self.request, space_ref=replace(self.request.space_ref, revision="other")),
            replace(self.request, space=replace(self.request.space, version="other")),
            replace(self.request, check_plan_hash="0" * 64),
            replace(self.request, options=reordered, catalog_hash=digest(reordered)),
        )
        with patch.object(batch, "_execute_construction") as execute:
            for index, request in enumerate(variants):
                selection = self.selection((request.options[0].id,), request)
                with self.subTest(case=index), self.assertRaises(ContractError):
                    batch.run_candidate_selection(self.inputs, request, selection)
        execute.assert_not_called()

    def test_catalog_and_selection_hashes_cannot_be_changed_during_replay(self):
        with self.assertRaises(ContractError):
            batch.parse_candidate_selection(replace(self.request, catalog_hash="0" * 64), self.payload(()))
        selection = self.selection((self.option_id("node-a", "node-c"),))
        variants = (
            replace(selection, request_hash="0" * 64),
            replace(selection, response_hash="0" * 64),
            replace(selection, option_hashes=("0" * 64,)),
            replace(selection, option_ids=(self.request.options[0].id,)),
            replace(selection, response_text=selection.response_text + " "),
        )
        with patch.object(batch, "_execute_construction") as execute:
            for index, altered in enumerate(variants):
                with self.subTest(case=index), self.assertRaises(ContractError):
                    batch.run_candidate_selection(self.inputs, self.request, altered)
        execute.assert_not_called()

    def test_full_catalog_replay_preserves_the_existing_app_result(self):
        request = self.prepare(limits=replace(self.limits, max_returned_options=9))
        selection = self.selection(tuple(option.id for option in request.options), request)
        result = batch.run_candidate_selection(self.inputs, request, selection)
        self.assertEqual(result.app_result, app.run_construction(*self.inputs))

    def test_a_real_other_task_or_committed_successor_rejects_the_original_batch(self):
        folder = ROOT / "domain-packs/structural-graph/construction/multitask"
        card_path = folder / "fork-stage1/card.json"
        inputs = app.load_construction_case(card_path)
        card = loads(app.ConstructionCaseCard, card_path.read_text(encoding="utf-8"))
        sources = {item.ref: (card_path.parent / item.path).read_bytes() for item in card.sources}
        request = self.prepare(inputs, sources=sources)
        selection = self.selection((request.options[3].id,), request)
        result = batch.run_candidate_selection(inputs, request, selection).app_result
        self.assertIsNotNone(result.run.commit)
        following = app.advance_construction(inputs, result, folder / "fork-stage2/card.json")
        self.assertEqual(following[2].revision, 1)
        other = app.load_construction_case(folder / "diamond/card.json")
        with patch.object(batch, "_execute_construction") as execute:
            for changed in (other, following):
                with self.subTest(task=changed[0].task_ref), self.assertRaises(ContractError):
                    batch.run_candidate_selection(changed, request, selection)
        execute.assert_not_called()

    def test_candidate_found_still_requires_final_task_acceptance_before_saving(self):
        selection = self.selection((self.option_id("node-a", "node-c"),))
        original = app.check_tasks
        calls = 0

        def final_rejection(candidate, plan, scope=None):
            nonlocal calls
            calls += 1
            report = original(candidate, plan, scope)
            if calls == 2:
                return replace(report, outcomes=(replace(report.outcomes[0], status="violated",
                                                          findings=("injected final rejection",)),
                                                 *report.outcomes[1:]))
            return report

        with patch.object(app, "check_tasks", side_effect=final_rejection):
            result = batch.run_candidate_selection(self.inputs, self.request, selection).app_result
        self.assertEqual(result.search.status, "candidate_found")
        self.assertIsNone(result.run.commit)
        self.assertEqual(result.run.assessment.goal_status, "violated")
        self.assertEqual(result.run.accepted, self.inputs[2])


if __name__ == "__main__":
    unittest.main()
