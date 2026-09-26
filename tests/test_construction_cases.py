"""Explicit construction inputs and a real, source-preserving two-stage run."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps"))
import bounded_generation as app
from dag_construction import DagEditSpace
from modelspine_protocols import (
    ArtifactRef, ContractError, EvidenceRef, Obligation, Property, TaskBinding,
    TaskStatement, digest, dumps, loads, properties, ref, to_data,
)


class ConstructionCaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.prepared, self.meta, self.base, raw, _ = app.load_example()
        self.space = loads(DagEditSpace, raw.decode("utf-8"))
        source = (ROOT / "domain-packs/structural-graph/tasks/source.txt").read_bytes()
        self.sources = {e.source: source for s in self.prepared.contract.statements for e in s.source_refs}

    def write_card(self, name, *, task=None, space=None, predecessor=None, snapshot=None):
        folder = self.folder / name
        folder.mkdir(parents=True, exist_ok=True)
        task = self.prepared.contract if task is None else task
        snapshot = self.base if snapshot is None else snapshot
        raw = dumps(task).encode("utf-8")
        task_ref = ArtifactRef(task.base.project_id, task.id, task.version, sha256(raw).hexdigest())
        (folder / "task.json").write_bytes(raw)
        space = replace(self.space if space is None else space, task_ref=task_ref)
        raw = dumps(space).encode("utf-8")
        space_ref = ArtifactRef(task.base.project_id, space.id, space.version, sha256(raw).hexdigest())
        (folder / "space.json").write_bytes(raw)
        (folder / "model.json").write_text(dumps(snapshot), encoding="utf-8")
        (folder / "metamodel.json").write_text(dumps(self.meta), encoding="utf-8")
        source_paths = []
        references = dict.fromkeys(e.source for s in task.statements for e in s.source_refs)
        for index, reference in enumerate(references):
            path = f"source-{index}.txt"
            (folder / path).write_bytes(self.sources[reference])
            source_paths.append({"ref": to_data(reference), "path": path})
        card = {"schema_version": "construction-case/0.1", "metamodel": "metamodel.json",
                "model": "model.json", "task": "task.json", "task_ref": to_data(task_ref),
                "space": "space.json", "space_ref": to_data(space_ref), "sources": source_paths,
                "predecessor": to_data(predecessor)}
        path = folder / "card.json"
        path.write_text(json.dumps(card), encoding="utf-8")
        return path

    def successor(self, parent_ref):
        raw = b"Keep node-b able to reach node-c.\n"
        source = ArtifactRef(self.base.project_id, "second-stage-source", "1", sha256(raw).hexdigest())
        self.sources[source] = raw
        statement = TaskStatement("second-stage-goal", raw.decode().strip(), "intent", "confirmed", True,
                                  (EvidenceRef(source, "lines:1-1", "engineering-task-author"),), None)
        obligation = Obligation("second-stage-path", "1", "graph_reachability", "graph", "root", (
            Property("source", "node-b"), Property("destination", "node-c"),
            Property("expected_reachable", True)))
        parent = self.prepared.contract
        task = replace(parent, version="2", statements=parent.statements + (statement,),
                       plan=replace(parent.plan, version="2", obligations=parent.plan.obligations + (obligation,)),
                       bindings=parent.bindings + (TaskBinding(obligation.id, obligation.version, (statement.id,)),))
        space = replace(self.space, version="2", edges=("edge-ab",), sources=("node-b",),
                        destinations=("node-c",), max_options=1)
        return task, space, parent_ref

    def prepare_trajectory(self):
        initial = app.load_construction_case(self.write_card("initial"))
        task, space, predecessor = self.successor(initial[0].task_ref)
        card = self.write_card("next", task=task, space=space, predecessor=predecessor)
        result = app.run_construction(*initial)
        self.assertIsNotNone(result.run.commit)
        return initial, result, card, task, space

    def test_explicit_case_runs_without_any_correct_proposal_file(self):
        card = self.write_card("initial")
        self.assertFalse((card.parent / "proposal.json").exists())
        inputs = app.load_construction_case(card)
        result = app.run_construction(*inputs)
        self.assertEqual(inputs[0].contract, self.prepared.contract)
        self.assertEqual(result.run.accepted.revision, 1)
        self.assertIsNotNone(result.run.commit)
        self.assertEqual(result.run.assessment.task_ref, inputs[0].task_ref)
        self.assertEqual(result.space_ref, inputs[4])

    def test_legacy_example_no_longer_reads_a_precomputed_proposal(self):
        read_text, read_bytes = Path.read_text, Path.read_bytes

        def allowed_text(path, *args, **kwargs):
            self.assertNotEqual(path.name, "proposal.json")
            return read_text(path, *args, **kwargs)

        def allowed_bytes(path, *args, **kwargs):
            self.assertNotEqual(path.name, "proposal.json")
            return read_bytes(path, *args, **kwargs)

        with patch.object(Path, "read_text", allowed_text), patch.object(Path, "read_bytes", allowed_bytes):
            inputs = app.load_example()
        self.assertIsNotNone(app.run_construction(*inputs).run.commit)

    def test_card_paths_cannot_escape_or_use_absolute_paths(self):
        for field in ("metamodel", "model", "task", "space", "source"):
            for absolute in (False, True):
                with self.subTest(field=field, absolute=absolute):
                    path = self.write_card(f"path-{field}-{absolute}")
                    card = json.loads(path.read_text(encoding="utf-8"))
                    original = card["sources"][0]["path"] if field == "source" else card[field]
                    outside = self.folder / f"outside-{field}.json"
                    outside.write_bytes((path.parent / original).read_bytes())
                    value = str(path.parent / original) if absolute else "../" + outside.name
                    if field == "source":
                        card["sources"][0]["path"] = value
                    else:
                        card[field] = value
                    path.write_text(json.dumps(card), encoding="utf-8")
                    with self.assertRaises(ContractError):
                        app.load_construction_case(path)

    def test_missing_file_and_modified_source_fail_without_fallback(self):
        path = self.write_card("missing")
        (path.parent / "space.json").unlink()
        with self.assertRaises((ContractError, OSError)):
            app.load_construction_case(path)
        path = self.write_card("source")
        (path.parent / "source-0.txt").write_bytes(b"changed after pinning\n")
        with self.assertRaises(ContractError):
            app.load_construction_case(path)

    def test_loader_rejects_task_base_space_base_and_reference_mixups(self):
        changed_base = replace(ref(self.base), revision=1)
        paths = [self.write_card("task-base", task=replace(self.prepared.contract, base=changed_base)),
                 self.write_card("space-base", space=replace(self.space, base=changed_base))]
        path = self.write_card("space-ref")
        card = json.loads(path.read_text(encoding="utf-8"))
        card["space_ref"]["revision"] = "other"
        path.write_text(json.dumps(card), encoding="utf-8")
        paths.append(path)
        for path in paths:
            with self.subTest(case=path.parent.name), self.assertRaises(ContractError):
                app.load_construction_case(path)

    def test_successor_uses_actual_commit_preserves_parent_goals_and_keeps_template_bytes(self):
        initial, first, card, template, template_space = self.prepare_trajectory()
        before = {path.name: path.read_bytes() for path in card.parent.iterdir()}
        following = app.advance_construction(initial, first, card)
        prepared, meta, snapshot, raw, space_ref = following
        space = loads(DagEditSpace, raw.decode("utf-8"))
        suffix = "/bound-" + digest(ref(first.run.accepted))
        self.assertEqual(snapshot, first.run.accepted)
        self.assertEqual(prepared.contract.base, ref(snapshot))
        self.assertEqual(space.base, ref(snapshot))
        self.assertEqual(space.task_ref, prepared.task_ref)
        self.assertEqual(prepared.contract.version, template.version + suffix)
        self.assertEqual(space.version, template_space.version + suffix)
        self.assertEqual(prepared.contract.statements, template.statements)
        self.assertEqual(prepared.contract.plan, template.plan)
        self.assertEqual(prepared.contract.bindings, template.bindings)
        self.assertEqual(space_ref.content_hash, sha256(raw).hexdigest())
        self.assertEqual(prepared.task_ref.content_hash, sha256(dumps(prepared.contract).encode()).hexdigest())
        self.assertEqual(meta, initial[1])
        second = app.run_construction(*following)
        self.assertIsNotNone(second.run.commit)
        self.assertEqual([initial[2].revision, first.run.accepted.revision, second.run.accepted.revision], [0, 1, 2])
        self.assertEqual(second.run.commit.snapshot, ref(second.run.accepted))
        self.assertTrue(second.run.assessment.report.satisfied)
        self.assertEqual(properties(next(e for e in second.run.accepted.elements if e.id == "edge-ab").properties),
                         {"source": "node-b", "target": "node-c"})
        self.assertEqual(before, {path.name: path.read_bytes() for path in card.parent.iterdir()})

    def test_successor_cannot_remove_or_rewrite_parent_intent_obligations_or_bindings(self):
        initial, first, _, template, space = self.prepare_trajectory()
        parent = initial[0].contract
        variants = (
            replace(template, statements=template.statements[1:]),
            replace(template, statements=(replace(template.statements[0], text="rewritten goal"),
                                          *template.statements[1:])),
            replace(template, plan=replace(template.plan, obligations=template.plan.obligations[1:]),
                    bindings=template.bindings[1:]),
            replace(template, plan=replace(template.plan, obligations=(
                replace(template.plan.obligations[1], parameters=(Property("source", "node-a"),
                        Property("destination", "node-b"), Property("expected_reachable", True))),
                template.plan.obligations[0], *template.plan.obligations[2:]))),
            replace(template, bindings=(replace(template.bindings[0], statement_ids=(parent.statements[1].id,)),
                                        *template.bindings[1:])),
            replace(template, plan=replace(template.plan, rule_version="different")),
            replace(template, plan=replace(template.plan, assumptions=("weakened assumptions",))),
        )
        for index, task in enumerate(variants):
            card = self.write_card(f"rewrite-{index}", task=task, space=space, predecessor=initial[0].task_ref)
            with self.subTest(case=index), self.assertRaises(ContractError):
                app.advance_construction(initial, first, card)

    def test_successor_requires_its_parent_and_new_task_and_plan_versions(self):
        initial, first, _, template, space = self.prepare_trajectory()
        parent = initial[0].contract
        variants = (
            (template, replace(initial[0].task_ref, revision="another-parent")),
            (replace(template, version=parent.version), initial[0].task_ref),
            (replace(template, id="unrelated-task"), initial[0].task_ref),
            (replace(template, plan=replace(template.plan, version=parent.plan.version)), initial[0].task_ref),
            (replace(template, plan=replace(template.plan, id="unrelated-plan")), initial[0].task_ref),
        )
        for index, (task, predecessor) in enumerate(variants):
            card = self.write_card(f"identity-{index}", task=task, space=space, predecessor=predecessor)
            with self.subTest(case=index), self.assertRaises(ContractError):
                app.advance_construction(initial, first, card)
        card = self.write_card("template-only", task=template, space=space, predecessor=initial[0].task_ref)
        with self.assertRaises(ContractError):
            app.load_construction_case(card)

    def test_no_commit_and_a_result_from_another_task_cannot_start_the_next_stage(self):
        initial, _, card, _, _ = self.prepare_trajectory()
        stopped = app.load_construction_case(self.write_card("zero-budget", space=replace(self.space, max_options=0)))
        result = app.run_construction(*stopped)
        self.assertIsNone(result.run)
        with self.assertRaises(ContractError):
            app.advance_construction(stopped, result, card)
        other = app.load_construction_case(self.write_card("other-task", task=replace(self.prepared.contract, id="other-task")))
        other_result = app.run_construction(*other)
        self.assertIsNotNone(other_result.run.commit)
        with self.assertRaises(ContractError):
            app.advance_construction(initial, other_result, card)

    def test_mismatched_commit_assessment_or_old_space_cannot_be_reused(self):
        initial, first, card, _, _ = self.prepare_trajectory()
        variants = (
            replace(first, space_ref=replace(first.space_ref, revision="other")),
            replace(first, run=replace(first.run, accepted=self.base)),
            replace(first, run=replace(first.run, commit=replace(first.run.commit, snapshot=ref(self.base)))),
            replace(first, run=replace(first.run, commit=replace(first.run.commit,
                    report=replace(first.run.commit.report, binding=replace(
                        first.run.commit.report.binding, candidate_hash=digest(self.base)))))),
            replace(first, run=replace(first.run, assessment=replace(first.run.assessment,
                    task_ref=replace(initial[0].task_ref, revision="other")))),
            replace(first, run=replace(first.run, assessment=replace(first.run.assessment, report=None))),
        )
        for index, result in enumerate(variants):
            with self.subTest(case=index), self.assertRaises(ContractError):
                app.advance_construction(initial, result, card)
        following = app.advance_construction(initial, first, card)
        for mixed in ((initial[0], *following[1:]), (*following[:3], *initial[3:])):
            with self.subTest(task=mixed[0].task_ref), self.assertRaises(ContractError):
                app.run_construction(*mixed)
        second = app.run_construction(*following)
        for inputs in (initial, following):
            with self.subTest(base=inputs[2].revision), self.assertRaises(ContractError):
                app.advance_construction(inputs, second, card)

    def test_fixed_multitask_cards_use_the_same_app_and_actual_fork_commit(self):
        folder = ROOT / "domain-packs/structural-graph/construction/multitask"
        first_inputs = app.load_construction_case(folder / "fork-stage1/card.json")
        first = app.run_construction(*first_inputs)
        self.assertIsNotNone(first.run.commit)
        following = app.advance_construction(first_inputs, first, folder / "fork-stage2/card.json")
        self.assertEqual(following[2], first.run.accepted)
        second = app.run_construction(*following)
        self.assertIsNotNone(second.run.commit)
        self.assertEqual((first.run.accepted.revision, second.run.accepted.revision), (1, 2))
        self.assertTrue(all(goal in following[0].contract.plan.obligations
                            for goal in first_inputs[0].contract.plan.obligations))
        for name, saved in (("diamond", True), ("disconnected", False)):
            with self.subTest(case=name):
                inputs = app.load_construction_case(folder / name / "card.json")
                result = app.run_construction(*inputs)
                self.assertEqual(bool(result.run and result.run.commit), saved)
                self.assertEqual(result.search.status, "candidate_found" if saved else "exhausted")
        unsupported = app.load_construction_case(folder / "unsupported-cycle/card.json")
        with self.assertRaisesRegex(ContractError, "invalid base graph") as raised:
            app.run_construction(*unsupported)
        self.assertEqual(raised.exception.code, "invalid")


if __name__ == "__main__":
    unittest.main()
