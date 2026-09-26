"""Evaluator-fixed multitask semantics, reference identity and real succession."""
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
from studies.construction import run_multitask as multi
from studies.construction.controls import ordinary_control
from dag_construction import DagEditSpace, prepare_dag
from modelspine_generation.bounded import EditOption
from modelspine_protocols import (
    ArtifactRef, ContractError, Element, EvidenceRef, Property, Snapshot, decode,
    digest, dumps, loads, properties, ref,
)
from support.task_oracle import (
    EvaluationResult, EvaluationSpec, ModelIdentity, ReferenceCase,
    evaluate_candidate, pin_evaluation_spec,
)


def truths():
    return json.loads((multi.FIXTURES / "semantics.json").read_text(encoding="utf-8"))["tasks"]


def evaluator_snapshot(truth):
    """Author the reference starting graph without a development task or candidate."""
    _, meta, _, _, _ = single.load_example()
    nodes = tuple(Element("node-" + n, "node", n, "graph", (Property("label", n),), (), True,
                          "hypothesis", True, ()) for n in "abcd")
    edges = tuple(Element(identity, "edge", identity, "graph",
                          (Property("source", endpoints[0]), Property("target", endpoints[1])),
                          tuple(sorted(set(endpoints))), True, "hypothesis", True, ())
                  for identity, endpoints in truth["edges"].items())
    root = Element("graph", "graph", "graph", None, (Property("root", "node-a"),),
                   tuple(e.id for e in nodes + edges), False, "hypothesis", True, ())
    return Snapshot("evaluator-engineering", truth["id"], 0, meta.ref, digest(meta), (root, *nodes, *edges))


def evaluator_reference(snapshot, truth, task_ref):
    spec = EvaluationSpec("task-evaluation/0.1", truth["id"] + "-truth", "1", task_ref,
                          ModelIdentity(snapshot.project_id, snapshot.model_id, snapshot.metamodel, snapshot.metamodel_hash),
                          tuple(ReferenceCase(f"goal-{i}", "graph_reachability", "graph", a, b, expected)
                                for i, (a, b, expected) in enumerate(truth["goals"], 1)))
    raw = dumps(spec).encode()
    return pin_evaluation_spec(raw, ArtifactRef(snapshot.project_id, spec.id, spec.version, sha256(raw).hexdigest()))


class IndependentMultitaskSemanticsTests(unittest.TestCase):
    def test_predeclared_full_spaces_match_independent_oracle_and_kahn(self):
        for truth in truths():
            if truth["expected_controls"] is None:
                continue
            snapshot = evaluator_snapshot(truth)
            task_ref = ArtifactRef(snapshot.project_id, "authored-target", "1", "a" * 64)
            pinned = evaluator_reference(snapshot, truth, task_ref)
            space = DagEditSpace("dag-edit-space/0.1", "authored-space", "1", task_ref, ref(snapshot),
                                 "graph", (truth["edit"],), tuple(truth["sources"]),
                                 tuple(truth["destinations"]), truth["budget"])
            options = [(a, b) for a in space.sources for b in space.destinations]
            for index, (a, b) in enumerate(options):
                with self.subTest(task=truth["id"], source=a, target=b):
                    option = EditOption(str(index), truth["edit"], (Property("source", a), Property("target", b)))
                    self.assertEqual(ordinary_control(snapshot, space, option).status, truth["expected_controls"][index])
                    candidate = replace(snapshot, elements=tuple(
                        replace(e, properties=option.values, dependencies=tuple(sorted({a, b})))
                        if e.id == truth["edit"] else e for e in snapshot.elements))
                    self.assertEqual(evaluate_candidate(candidate, pinned).satisfied, truth["expected_reference"][index])

    def test_parent_reference_goals_are_a_strict_prefix_of_successor(self):
        parent, successor = (next(t for t in truths() if t["id"] == name)
                             for name in ("fork-stage1", "fork-stage2"))
        self.assertEqual(successor["goals"][:-1], parent["goals"])
        self.assertEqual(successor["goals"][-1], ["node-d", "node-c", True])


class MultitaskIntegrationTests(unittest.TestCase):
    def parent(self, condition="ordinary-rule"):
        inputs = single.bounded_generation.load_construction_case(multi.CARDS / "fork-stage1" / "card.json")
        return inputs, single.execute_condition(condition, inputs)

    def successor(self, condition="ordinary-rule"):
        previous, result = self.parent(condition)
        card = multi.CARDS / "fork-stage2" / "card.json"
        inputs = single.bounded_generation.advance_construction(previous, result, card)
        return inputs, card, previous, result

    def test_all_fifteen_fixed_entries_run_with_expected_stops_and_costs(self):
        record = multi.collect()
        self.assertEqual((record["planned"], record["started"], record["terminal"], record["not_started"]), (15, 15, 15, 0))
        self.assertEqual((record["returned"], record["saved"], record["reference_error_trials"]), (12, 9, 0))
        expected = {t["id"]: t for t in truths()}
        costs = {"fork-stage1": (4, 2), "fork-stage2": (4, 2), "diamond": (2, 1), "disconnected": (3, 1)}
        for trial in record["trials"]:
            with self.subTest(trial=trial["id"]):
                truth = expected[trial["case_id"]]
                self.assertEqual(trial["status"], truth["expected_status"])
                self.assertEqual(sha256(trial["task_content"].encode()).hexdigest(), trial["task_ref"]["content_hash"])
                self.assertEqual(sha256(trial["space_content"].encode()).hexdigest(), trial["space_ref"]["content_hash"])
                if trial["case_id"] == "unsupported-cycle":
                    self.assertFalse(trial["returned"])
                    self.assertEqual(trial["exception_type"], "ContractError")
                    self.assertIsNotNone(trial["exception_code"])
                    self.assertIsNone(trial["counts"])
                    continue
                expected_checks = costs[trial["case_id"]][trial["condition"] != "terminal-only"]
                self.assertEqual(trial["counts"]["search_candidate_checks"], expected_checks)
                self.assertEqual(trial["counts"]["final_acceptance_checker_calls"], 3 if trial["saved"] else 0)
                if trial["saved"]:
                    self.assertTrue(decode(EvaluationResult, trial["independent_saved"]).satisfied)
                    values = {p["name"]: p["value"] for e in trial["app_result"]["run"]["accepted"]["elements"]
                              if e["id"] == truth["edit"] for p in e["properties"]}
                    self.assertEqual([values["source"], values["target"]], truth["expected_selected"])
        for condition in single.CONDITIONS:
            first = next(t for t in record["trials"] if t["id"] == f"fork-stage1/{condition}")
            second = next(t for t in record["trials"] if t["id"] == f"fork-stage2/{condition}")
            self.assertEqual(second["input_snapshot"], first["app_result"]["run"]["commit"]["snapshot"])
            self.assertEqual(second["app_result"]["run"]["accepted"]["revision"], 2)

    def test_declared_inputs_and_all_options_match_evaluator_truth(self):
        for truth in truths():
            if truth["id"] == "fork-stage2":
                inputs, _, _, _ = self.successor()
            else:
                inputs = single.bounded_generation.load_construction_case(multi.CARDS / truth["id"] / "card.json")
            prepared, _, snapshot, raw, _ = inputs
            actual = {e.id: [properties(e.properties)["source"], properties(e.properties)["target"]]
                      for e in snapshot.elements if e.kind == "edge"}
            self.assertEqual(actual, truth["edges"])
            space = loads(DagEditSpace, raw.decode())
            self.assertEqual((space.edges, space.sources, space.destinations, space.max_options),
                             ((truth["edit"],), tuple(truth["sources"]), tuple(truth["destinations"]), truth["budget"]))
            if truth["expected_controls"] is None:
                continue
            constructor = prepare_dag(snapshot, prepared.contract.plan, space,
                                      (EvidenceRef(prepared.task_ref, "artifact", "fixed-task"),))
            decisions = [ordinary_control(snapshot, space, option).status for option in constructor.options]
            self.assertEqual(decisions, truth["expected_controls"])
            self.assertEqual([constructor.control(option).status for option in constructor.options], decisions)

    def test_successor_reference_only_changes_task_identity_and_version(self):
        inputs, card, parent, result = self.successor()
        pinned, binding = multi.bind_reference("fork-stage2", inputs, card)
        template = loads(EvaluationSpec, binding["template_content"])
        bound = loads(EvaluationSpec, pinned.content.decode())
        self.assertEqual(replace(bound, task_ref=template.task_ref, version=template.version), template)
        self.assertEqual(bound.version, template.version + "/bound-" + digest(inputs[0].task_ref))
        self.assertEqual(pinned.spec_ref.revision, bound.version)
        self.assertNotEqual(binding["template_ref"], binding["bound_ref"])
        old = parent[0].contract
        new = inputs[0].contract
        for original, successor in ((old.statements, new.statements), (old.bindings, new.bindings),
                                    (old.plan.obligations, new.plan.obligations)):
            self.assertTrue(all(item in successor for item in original))
        self.assertEqual(inputs[2], result.run.accepted)

    def test_same_model_stale_task_reference_is_rejected_before_app(self):
        inputs, _, parent, _ = self.successor()
        old_pinned, _ = multi.bind_reference("fork-stage1", parent, multi.CARDS / "fork-stage1" / "card.json")
        with patch.object(single, "execute_condition") as execute:
            with self.assertRaisesRegex(ContractError, "reference task"):
                single.observe_trial("stale", "ordinary-rule", inputs, old_pinned)
            execute.assert_not_called()

    def test_successor_reference_cannot_be_bound_to_parent_inputs(self):
        parent, _ = self.parent()
        with self.assertRaisesRegex(ContractError, "bound successor task"):
            multi.bind_reference("fork-stage2", parent, multi.CARDS / "fork-stage2" / "card.json")

    def test_noncommit_parent_preserves_unstarted_successor_denominator(self):
        loader = single.bounded_generation.load_construction_case
        def one_option(card):
            inputs = loader(card)
            return single.scenario_inputs(inputs, {"max_options": 1}) if card.parent.name == "fork-stage1" else inputs
        with patch.object(single.bounded_generation, "load_construction_case", side_effect=one_option), \
                patch.object(single.bounded_generation, "advance_construction") as advance:
            record = multi.collect()
            advance.assert_not_called()
        self.assertEqual((record["planned"], record["started"], record["terminal"], record["not_started"]), (15, 12, 12, 3))
        for trial in record["trials"]:
            if trial["case_id"] == "fork-stage2":
                self.assertEqual(trial["status"], "not_started")
                self.assertEqual(trial["predecessor_status"], "budget_exhausted")
                self.assertFalse(trial["started"])

    def test_input_failure_remains_error_and_blocks_only_its_successor(self):
        loader = single.bounded_generation.load_construction_case
        def unavailable(card):
            if card.parent.name == "fork-stage1":
                raise OSError("declared input unavailable")
            return loader(card)
        with patch.object(single.bounded_generation, "load_construction_case", side_effect=unavailable):
            record = multi.collect()
        self.assertEqual((record["planned"], record["started"], record["terminal"], record["not_started"]), (15, 12, 12, 3))
        self.assertEqual(record["preparation_error_trials"], 3)
        self.assertEqual(record["run_status"], "error")
        self.assertEqual(record["saved"], 3)
        for trial in record["trials"]:
            if trial["case_id"] == "fork-stage1":
                self.assertFalse(trial["app_started"])
                self.assertEqual(trial["reason"], "declared input unavailable")
                self.assertEqual(trial["error_stage"], "input_or_reference_preparation")
                self.assertIsNone(trial["wall_seconds"])

    def test_reference_error_does_not_erase_save_or_rewrite_successor(self):
        checkpoints = []
        with patch.object(single, "evaluate_candidate", side_effect=RuntimeError("reference failed")):
            record = multi.collect(checkpoint=lambda r: checkpoints.append(json.loads(json.dumps(r))))
        self.assertEqual((record["saved"], record["started"], record["terminal"]), (9, 15, 15))
        self.assertEqual(record["run_status"], "reference_error")
        self.assertTrue(any(r["active_trial"] and r["active_trial"].get("saved")
                            and r["active_trial"].get("reference_status") == "pending" for r in checkpoints))
        for trial in record["trials"]:
            if trial["saved"]:
                self.assertIsNotNone(trial["independent_saved_error"])
                self.assertEqual(trial["reference_status"], "error")

    def test_typed_result_callback_runs_once_after_app_checkpoint(self):
        inputs, _ = self.parent()
        pinned, _ = multi.bind_reference("fork-stage1", inputs, multi.CARDS / "fork-stage1" / "card.json")
        events = []
        def sink(result):
            self.assertEqual(events, ["saved-checkpoint"])
            self.assertIsNotNone(result.run.commit)
            events.append("typed-result")
        def checkpoint(record):
            self.assertTrue(record["saved"])
            events.append("saved-checkpoint")
        with patch.object(single, "execute_condition", wraps=single.execute_condition) as app:
            record = single.observe_trial("sink", "ordinary-rule", inputs, pinned, checkpoint=checkpoint, result_sink=sink)
        app.assert_called_once()
        self.assertTrue(record["saved"])
        self.assertEqual(events, ["saved-checkpoint", "typed-result"])

    def test_sink_failure_keeps_current_app_in_multitask_checkpoint(self):
        observe = single.observe_trial
        def interrupted(*args, result_sink=None, **kwargs):
            def failed_sink(result):
                result_sink(result)
                raise RuntimeError("typed consumer interrupted")
            return observe(*args, result_sink=failed_sink, **kwargs)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "checkpoint.json"
            with patch.object(sys, "argv", ["multitask", "--output", str(output)]), \
                    patch.object(single, "CONDITIONS", ("ordinary-rule",)), \
                    patch.object(single, "observe_trial", side_effect=interrupted):
                with self.assertRaisesRegex(RuntimeError, "typed consumer interrupted"):
                    multi.main()
            record = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(record["run_status"], "error")
        self.assertEqual((record["started"], record["returned"], record["saved"], record["terminal"]), (1, 1, 1, 0))
        self.assertTrue(record["active_trial"]["saved"])
        self.assertEqual(record["active_trial"]["reference_status"], "pending")
        self.assertEqual(record["active_trial"]["app_result"]["run"]["accepted"]["revision"], 1)

    def test_multitask_serialization_error_keeps_completed_and_active_saves(self):
        writer = single._write_checkpoint
        def fail_later(path, record):
            if len(record["trials"]) == 2 and record["active_trial"] is None:
                record = {**record, "bad_serialization": object()}
            writer(path, record)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "checkpoint.json"
            with patch.object(sys, "argv", ["multitask", "--output", str(output)]), \
                    patch.object(single, "CONDITIONS", ("ordinary-rule",)), \
                    patch.object(single, "_write_checkpoint", side_effect=fail_later):
                with self.assertRaises(TypeError):
                    multi.main()
            record = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(list(Path(folder).iterdir()), [output])
        self.assertEqual(record["run_status"], "error")
        self.assertEqual(record["trials"][0]["case_id"], "fork-stage1")
        self.assertTrue(record["trials"][0]["saved"])
        self.assertEqual(record["active_trial"]["case_id"], "diamond")
        self.assertTrue(record["active_trial"]["saved"])
        self.assertEqual(record["active_trial"]["reference_status"], "pending")


if __name__ == "__main__":
    unittest.main()
