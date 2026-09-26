"""Engineering payload fixtures only: no provider invocation or transport receipt."""
from base64 import b64decode
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.construction import run as single
from studies.construction import replay_candidates as replay
import candidate_batch
from modelspine_protocols import ContractError, decode, digest, dumps, loads, to_data
from support.task_oracle import EvaluationResult, EvaluationSpec, pin_evaluation_spec
from task_acceptance import EngineeringTaskCard


class CandidateReplayTests(unittest.TestCase):
    def setUp(self):
        self.inputs = single.load_example()
        folder = ROOT / "domain-packs" / "structural-graph" / "tasks"
        card = loads(EngineeringTaskCard, (folder / "card.json").read_text(encoding="utf-8"))
        sources = {source.ref: (folder / source.path).read_bytes() for source in card.sources}
        # These are host test byte limits, not token budgets or provider settings.
        self.request = candidate_batch.prepare_candidate_request(
            self.inputs, sources, request_id="engineering-replay-fixture",
            limits=candidate_batch.CandidateLimits(9, 3, 100000, 10000))
        self.request_hash = digest(self.request)

    def payload(self, indices=(0, 1, 2)):
        return json.dumps({"schema_version": "candidate-selection/0.1", "request_id": self.request.request_id,
                           "option_ids": [self.request.options[i].id for i in indices]}, indent=2).encode("utf-8")

    def replay(self, payload=None, **kwargs):
        return replay.replay_candidates(self.inputs, self.request, self.payload() if payload is None else payload,
                                        self.request_hash, **kwargs)

    def test_same_payload_three_fresh_bases_preserve_cost_and_raw_checkpoint(self):
        before = to_data(self.inputs[2])
        payload = self.payload()
        checkpoints = []
        parser = candidate_batch.parse_candidate_selection
        def parse(request, raw):
            self.assertTrue(checkpoints)
            self.assertEqual(b64decode(checkpoints[0]["raw_payload"]["content"]), raw)
            self.assertEqual(checkpoints[0]["raw_payload"]["sha256"], sha256(raw).hexdigest())
            self.assertEqual(checkpoints[0]["planned_trials"], list(single.CONDITIONS))
            return parser(request, raw)
        with patch.object(candidate_batch, "parse_candidate_selection", side_effect=parse), \
                patch.object(candidate_batch, "run_candidate_selection", wraps=candidate_batch.run_candidate_selection) as app:
            record = self.replay(checkpoint=lambda value: checkpoints.append(json.loads(json.dumps(value))))
        self.assertEqual(app.call_count, 3)
        self.assertEqual((record["planned_batches"], record["valid_batches"], record["planned"],
                          record["started"], record["terminal"], record["app_returned"], record["saved"]),
                         (1, 1, 3, 3, 3, 3, 3))
        self.assertEqual(record["payload_origin"], "caller_supplied")
        self.assertEqual(record["api_calls_during_replay"], 0)
        self.assertIsNone(record["backend_receipt"])
        self.assertIsNone(record["source_generation_cost"])
        self.assertIsNone(record["source_generation_usage"])
        self.assertEqual(to_data(self.inputs[2]), before)
        for index, trial in enumerate(record["trials"]):
            self.assertTrue(trial["saved"])
            self.assertEqual(trial["app_result"]["run"]["accepted"]["revision"], 1)
            self.assertTrue(decode(EvaluationResult, trial["independent_saved"]).satisfied)
            self.assertEqual(trial["counts"]["search_candidate_checks"], (3, 2, 2)[index])
            self.assertEqual(trial["counts"]["final_acceptance_checker_calls"], 3)
            self.assertEqual(trial["total_development_checker_calls"], (6, 5, 5)[index])
            self.assertEqual(trial["batch_response_hash"], sha256(payload).hexdigest())
            self.assertEqual(trial["api_calls_during_replay"], 0)
            self.assertNotIn("llm_calls", trial)
            self.assertNotIn("paid_api_cost", trial)
            self.assertIs(app.call_args_list[index].args[0], self.inputs)
            self.assertIs(app.call_args_list[index].args[1], self.request)
        self.assertEqual(record["run_status"], "complete")

    def test_reordered_subsequence_is_not_replaced_by_full_catalog(self):
        for indices in ((7, 1, 2), (2, 0)):
            with self.subTest(indices=indices):
                record = self.replay(self.payload(indices))
                expected = [self.request.options[i].id for i in (indices if len(indices) == 3 else indices[:1])]
                self.assertEqual(record["selection"]["option_ids"], [self.request.options[i].id for i in indices])
                for trial in record["trials"]:
                    self.assertEqual([s["option"]["id"] for s in trial["app_result"]["search"]["steps"]], expected)
                    self.assertTrue(trial["saved"])

    def test_empty_valid_batch_really_executes_three_empty_searches(self):
        with patch.object(candidate_batch, "run_candidate_selection", wraps=candidate_batch.run_candidate_selection) as app:
            record = self.replay(self.payload(()))
        self.assertEqual(app.call_count, 3)
        self.assertEqual((record["valid_batches"], record["catalog_size"], record["returned_options"]), (1, 9, 0))
        self.assertEqual((record["app_returned"], record["saved"]), (3, 0))
        for trial in record["trials"]:
            self.assertEqual(trial["status"], "exhausted")
            self.assertEqual(trial["exhaustion_scope"], "backend_batch")
            self.assertEqual(trial["batch"]["exhaustion_scope"], "backend_batch")
            self.assertEqual(trial["app_result"]["search"]["steps"], [])
            self.assertEqual(trial["total_development_checker_calls"], 0)
            self.assertIsNone(trial["independent_saved"])

    def test_invalid_non_utf8_keeps_original_bytes_and_all_unstarted(self):
        raw = b"\xff\x00\xfe"
        checkpoints = []
        with patch.object(candidate_batch, "run_candidate_selection") as app:
            record = self.replay(raw, checkpoint=lambda value: checkpoints.append(json.loads(json.dumps(value))))
            app.assert_not_called()
        self.assertEqual(b64decode(checkpoints[0]["raw_payload"]["content"]), raw)
        self.assertEqual(record["raw_payload"]["sha256"], sha256(raw).hexdigest())
        self.assertEqual(record["selection_status"], "response_invalid")
        self.assertEqual((record["valid_batches"], record["started"], record["not_started"]), (0, 0, 3))
        self.assertIsNone(record["returned_options"])
        self.assertEqual(record["error"]["phase"], "selection")
        self.assertEqual(record["run_status"], "error")

    def test_wrong_original_request_hash_blocks_parser_and_every_app(self):
        with patch.object(candidate_batch, "parse_candidate_selection") as parser, \
                patch.object(candidate_batch, "run_candidate_selection") as app:
            record = replay.replay_candidates(self.inputs, self.request, self.payload(), "0" * 64)
        parser.assert_not_called()
        app.assert_not_called()
        self.assertEqual(record["error"]["phase"], "request_binding")
        self.assertEqual(record["error"]["code"], "conflict")
        self.assertEqual((record["started"], record["not_started"]), (0, 3))

    def test_same_model_wrong_task_reference_blocks_before_parsing(self):
        original = single.reference_spec()
        spec = loads(EvaluationSpec, original.content.decode())
        wrong = replace(spec, task_ref=replace(spec.task_ref, revision="stale"))
        raw = dumps(wrong).encode()
        pinned = pin_evaluation_spec(raw, replace(original.spec_ref, content_hash=sha256(raw).hexdigest()))
        with patch.object(single, "reference_spec", return_value=pinned), \
                patch.object(candidate_batch, "parse_candidate_selection") as parser, \
                patch.object(candidate_batch, "run_candidate_selection") as app:
            record = self.replay()
        parser.assert_not_called()
        app.assert_not_called()
        self.assertEqual(record["error"]["phase"], "reference_binding")
        self.assertEqual((record["valid_batches"], record["started"], record["not_started"]), (0, 0, 3))

    def test_app_failure_does_not_erase_or_skip_other_independent_conditions(self):
        calls = 0
        execute = candidate_batch.run_candidate_selection
        def fail_first(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ContractError("invalid", "injected app failure")
            return execute(*args, **kwargs)
        with patch.object(candidate_batch, "run_candidate_selection", side_effect=fail_first):
            record = self.replay()
        self.assertEqual((calls, record["started"], record["terminal"], record["app_returned"], record["saved"]), (3, 3, 3, 2, 2))
        self.assertEqual(record["run_status"], "error")
        self.assertEqual(record["trials"][0]["exception_code"], "invalid")
        self.assertIsNone(record["trials"][0]["saved"])
        self.assertIsNone(record["trials"][0]["counts"])
        self.assertTrue(all(t["saved"] for t in record["trials"][1:]))

    def test_reference_errors_keep_all_saves_and_evaluate_each_role_once(self):
        checkpoints = []
        with patch.object(single, "evaluate_candidate", side_effect=RuntimeError("reference unavailable")) as oracle:
            record = self.replay(checkpoint=lambda value: checkpoints.append(json.loads(json.dumps(value))))
        self.assertEqual(oracle.call_count, 10)  # 3+2+2 candidates, plus 3 saved-result roles.
        self.assertEqual((record["saved"], record["reference_error_trials"]), (3, 3))
        self.assertEqual(record["run_status"], "reference_error")
        for trial in record["trials"]:
            self.assertTrue(trial["saved"])
            self.assertIsNotNone(trial["independent_saved_error"])
        self.assertTrue(any(c["active_trial"] and c["active_trial"].get("saved")
                            and c["active_trial"]["reference_status"] == "pending" for c in checkpoints))

    def test_raw_checkpoint_failure_prevents_parse_and_execution(self):
        with patch.object(candidate_batch, "parse_candidate_selection") as parser, \
                patch.object(candidate_batch, "run_candidate_selection") as app:
            with self.assertRaisesRegex(OSError, "record unavailable"):
                self.replay(checkpoint=lambda _: (_ for _ in ()).throw(OSError("record unavailable")))
        parser.assert_not_called()
        app.assert_not_called()

    def test_later_serialization_failure_keeps_completed_and_current_saved_app(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "replay.json"
            with output.open("x", encoding="utf-8") as stream:
                stream.write("{}")
            def checkpoint(record):
                if len(record["trials"]) == 2 and record["active_trial"] is None:
                    record = {**record, "unserializable": object()}
                single._write_checkpoint(output, record)
            with self.assertRaises(TypeError):
                self.replay(checkpoint=checkpoint)
            kept = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(list(Path(folder).iterdir()), [output])
        self.assertEqual(len(kept["trials"]), 1)
        self.assertTrue(kept["trials"][0]["saved"])
        self.assertTrue(kept["active_trial"]["saved"])
        self.assertEqual(kept["active_trial"]["condition"], "dag-construction")
        self.assertEqual(kept["active_trial"]["reference_status"], "pending")
        self.assertEqual(kept["run_status"], "in_progress")
        self.assertEqual(kept["planned"], 3)
        self.assertEqual(b64decode(kept["raw_payload"]["content"]), self.payload())

    def test_execute_app_default_keeps_original_recorder_behavior(self):
        with patch.object(single, "execute_condition", wraps=single.execute_condition) as original:
            record = single.observe_trial("default", "ordinary-rule", self.inputs, single.reference_spec())
        original.assert_called_once_with("ordinary-rule", self.inputs, None)
        self.assertTrue(record["saved"])
        self.assertEqual(record["total_development_checker_calls"], 5)


if __name__ == "__main__":
    unittest.main()
