"""Fixed declared goals, actual saves, and separate reference outcomes."""
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from task_acceptance import EngineeringTaskCard, _inside, load_example, run_task
from task_contracts import load_task
from task_checks import check_tasks
from finite_models import check_automaton, check_structure
from fixtures import load_case
from modelspine_assurance.tasks import prepare_task
from modelspine_kernel import ModelKernel
from modelspine_protocols import (
    ArtifactRef, ContractError, Outcome, ReportBinding, SetDependencies, SetProperty,
    ValidationReport, decode, digest, dumps, loads, ref, select_scope, validate_report,
)
from support.task_oracle import evaluate_candidate, pin_evaluation_spec

PLATFORM = Path(__file__).resolve().parents[1]


def revised_task(prepared, **changes):
    contract = replace(prepared.contract, **changes)
    raw = dumps(contract).encode()
    expected = replace(prepared.task_ref, revision=contract.version, content_hash=hashlib.sha256(raw).hexdigest())
    folder = PLATFORM / "domain-packs" / contract.base.model_id / "tasks"
    source = (folder / "source.txt").read_bytes()
    return prepare_task(raw, expected, {e.source: source for s in contract.statements for e in s.source_refs})


def oracle(profile):
    folder = PLATFORM / "tests" / "fixtures" / "task-acceptance"
    name = "graph-reference.json" if profile == "structural-graph" else "automaton-reference.json"
    index = json.loads((folder / "reference-index.json").read_text())
    return pin_evaluation_spec((folder / name).read_bytes(), decode(ArtifactRef, index[name]))


def self_trace_defect(snapshot, plan, scope=None):
    """Injected defect: generalize self-selected trace success to every goal.

    This deliberately wrong test checker keeps all integrity bindings correct.
    It is not a naturally observed defect or an alternative production checker.
    """
    _, _, legacy = load_case(PLATFORM / "domain-packs" / "finite-automaton")
    old = check_automaton(snapshot, legacy)
    scope = select_scope(plan, scope)
    return ValidationReport(ReportBinding(digest(snapshot), digest(plan), scope, plan.assumptions,
                                          "injected-self-trace-defect", "1"),
                            tuple(Outcome(o.id, o.version, "satisfied" if old.satisfied else "violated",
                                          ("injected: generalized editable trace result",))
                                  for o in plan.obligations if o.target in scope))


def broken_behavior(proposal):
    return replace(proposal, operations=(SetProperty("set_property", "step-b", "symbol", "a"),
                                        SetProperty("set_property", "machine", "trace", "aa")))


class TaskAcceptanceTests(unittest.TestCase):
    def test_two_profiles_commit_with_task_plan_candidate_and_reference_bound(self):
        for profile in ("structural-graph", "finite-automaton"):
            with self.subTest(profile=profile):
                prepared, meta, snapshot, proposal = load_example(profile)
                result = run_task(prepared, meta, snapshot, proposal, check_tasks, "task-author")
                self.assertIsNotNone(result.commit)
                self.assertEqual(result.accepted.revision, snapshot.revision + 1)
                self.assertEqual(result.assessment.task_ref, prepared.task_ref)
                self.assertEqual(result.assessment.candidate, result.commit.snapshot)
                self.assertEqual(result.assessment.report.binding.plan_hash, prepared.plan_hash)
                reference = evaluate_candidate(result.accepted, oracle(profile))
                self.assertEqual(reference.task_ref, prepared.task_ref)
                self.assertEqual(reference.candidate_ref, result.commit.snapshot)
                self.assertTrue(reference.satisfied)

    def test_valid_acyclic_graph_can_violate_fixed_reachability_without_save(self):
        prepared, meta, snapshot, proposal = load_example("structural-graph")
        proposal = replace(proposal, operations=(
            SetProperty("set_property", "edge-bc", "source", "node-a"),
            SetProperty("set_property", "edge-bc", "target", "node-b"),
            SetDependencies("set_dependencies", "edge-bc", ("node-a", "node-b"), True)))
        result = run_task(prepared, meta, snapshot, proposal, check_tasks, "task-author")
        _, _, legacy = load_case(PLATFORM / "domain-packs" / "structural-graph")
        self.assertTrue(check_structure(result.candidate, legacy).satisfied)
        self.assertEqual(result.assessment.goal_status, "violated")
        self.assertIsNone(result.commit)
        self.assertEqual(result.accepted, snapshot)

    def test_editing_trace_and_behavior_cannot_replace_task_input(self):
        prepared, meta, snapshot, proposal = load_example("finite-automaton")
        result = run_task(prepared, meta, snapshot, broken_behavior(proposal), check_tasks, "task-author")
        _, _, legacy = load_case(PLATFORM / "domain-packs" / "finite-automaton")
        self.assertTrue(check_automaton(result.candidate, legacy).satisfied)
        self.assertEqual([o.status for o in result.assessment.report.outcomes],
                         ["satisfied", "violated", "violated"])
        self.assertIsNone(result.commit)
        self.assertEqual(result.accepted, snapshot)

    def test_common_semantic_error_keeps_save_and_reference_failure_as_separate_facts(self):
        prepared, meta, snapshot, proposal = load_example("finite-automaton")
        result = run_task(prepared, meta, snapshot, broken_behavior(proposal), self_trace_defect, "task-author")
        self.assertIsNotNone(result.commit)
        self.assertEqual(result.assessment.goal_status, "satisfied")
        validate_report(result.assessment.report, result.accepted, prepared.contract.plan,
                        select_scope(prepared.contract.plan))
        before = digest(result.accepted)
        reference = evaluate_candidate(result.accepted, oracle("finite-automaton"))
        self.assertFalse(reference.satisfied)
        self.assertEqual([o.status for o in reference.outcomes], ["violated", "violated"])
        self.assertEqual(reference.task_ref, prepared.task_ref)
        self.assertEqual(reference.candidate_ref, result.commit.snapshot)
        self.assertEqual(digest(result.accepted), before)

    def test_unresolved_and_unmapped_required_intents_block_save_but_keep_known_results(self):
        prepared, meta, snapshot, proposal = load_example("finite-automaton")
        statement = prepared.contract.statements[0]
        for statements in ((replace(statement, confirmation="conflicted", pending_reason="author conflict"),)
                           + prepared.contract.statements[1:],
                           prepared.contract.statements + (replace(statement, id="unmapped"),)):
            with self.subTest(statements=statements):
                pending = revised_task(prepared, statements=statements)
                result = run_task(pending, meta, snapshot, proposal, check_tasks, "task-author")
                self.assertEqual((result.assessment.intent_status, result.assessment.goal_status),
                                 ("unresolved", "satisfied"))
                self.assertIsNone(result.commit)
                self.assertEqual(result.accepted, snapshot)

    def test_no_plan_returns_before_kernel_preview_or_checker(self):
        prepared, meta, snapshot, proposal = load_example("finite-automaton")
        pending = revised_task(prepared, plan=None, bindings=())
        with patch("task_acceptance.ModelKernel", side_effect=AssertionError("kernel created")):
            result = run_task(pending, meta, snapshot, proposal,
                              lambda *_: self.fail("checker called"), "task-author")
        self.assertIsNone(result.candidate)
        self.assertIsNone(result.commit)
        self.assertIsNone(result.assessment.report)
        self.assertEqual(result.accepted, snapshot)
        with self.assertRaises(ContractError):
            run_task(pending, meta, replace(snapshot, revision=1), proposal, check_tasks, "task-author")

    def test_old_base_changed_metamodel_and_report_are_rejected(self):
        prepared, meta, snapshot, proposal = load_example("finite-automaton")
        variants = ((meta, replace(snapshot, revision=1), proposal),
                    (replace(meta, ref=replace(meta.ref, version="new")), snapshot, proposal),
                    (meta, snapshot, replace(proposal, base=replace(proposal.base, revision=1))))
        for model_meta, model, change in variants:
            with self.subTest(model=model), self.assertRaises(ContractError):
                run_task(prepared, model_meta, model, change, check_tasks, "task-author")
        def wrong(candidate, plan, scope=None):
            report = check_tasks(candidate, plan, scope)
            return replace(report, binding=replace(report.binding, candidate_hash=digest(snapshot)))
        with self.assertRaises(ContractError):
            run_task(prepared, meta, snapshot, proposal, wrong, "task-author")

    def test_commit_recheck_failure_does_not_change_accepted_snapshot_or_receipts(self):
        prepared, meta, snapshot, proposal = load_example("finite-automaton")
        for failure in ("exception", "different-report"):
            with self.subTest(failure=failure):
                instances, calls = [], []
                def capture(*args):
                    kernel = ModelKernel(*args)
                    instances.append(kernel)
                    return kernel
                def unstable(candidate, plan, scope=None):
                    calls.append(ref(candidate))
                    report = check_tasks(candidate, plan, scope)
                    if len(calls) == 3:
                        if failure == "exception":
                            raise RuntimeError("submit checker failed")
                        return replace(report, binding=replace(report.binding, tool_version="changed"))
                    return report
                with patch("task_acceptance.ModelKernel", side_effect=capture):
                    with self.assertRaises((RuntimeError, ContractError)):
                        run_task(prepared, meta, snapshot, proposal, unstable, "task-author")
                self.assertEqual(len(calls), 3)
                self.assertEqual(instances[0].snapshot(), snapshot)
                self.assertEqual(instances[0]._commits, {})

    def test_changed_task_requires_new_pinned_reference_and_version(self):
        prepared, _, _, _ = load_example("finite-automaton")
        changed = revised_task(prepared, version="2")
        self.assertNotEqual(changed.task_ref, prepared.task_ref)
        with self.assertRaises(ContractError):
            prepare_task(dumps(changed.contract).encode(), prepared.task_ref, {})

    def test_loader_has_no_missing_file_fallback_and_card_paths_are_bounded(self):
        prepared, _, _, _ = load_example("finite-automaton")
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with self.assertRaises(ContractError):
                load_task(folder / "missing.json", prepared.task_ref, {})
            for path in ("../outside", str(folder.parent / "outside")):
                with self.subTest(path=path), self.assertRaises(ContractError):
                    _inside(folder, path)
        for text in ("null", "42", '{"schema":"engineering-task-card/0.1","sources":null}'):
            with self.assertRaises(ContractError):
                loads(EngineeringTaskCard, text)


if __name__ == "__main__":
    unittest.main()
