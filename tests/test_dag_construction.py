"""DAG construction controls one redirect, while all task goals still need checks."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "adapters"))

from dag_construction import DagEditSpace, prepare_dag
from modelspine_kernel import ModelKernel
from modelspine_protocols import (
    ContractError, EvidenceRef, Obligation, Property, SetDependencies, SetProperty,
    digest, properties, ref, to_data,
)
from task_acceptance import load_example
from task_checks import check_tasks


class DagConstructionTests(unittest.TestCase):
    def setUp(self):
        self.task, self.meta, self.snapshot, _ = load_example("structural-graph")
        self.plan = self.task.contract.plan
        self.space = DagEditSpace("dag-edit-space/0.1", "dag-space", "1", self.task.task_ref,
                                  ref(self.snapshot), "graph", ("edge-bc",),
                                  ("node-c", "node-a", "node-b"), ("node-b", "node-c", "node-a"), 9)
        self.evidence = (EvidenceRef(self.task.task_ref, "artifact", "fixed-task-contract"),)
        self.constructor = self.prepare()

    def prepare(self, snapshot=None, space=None, plan=None):
        return prepare_dag(self.snapshot if snapshot is None else snapshot,
                           self.plan if plan is None else plan,
                           self.space if space is None else space, self.evidence)

    def option(self, source, target, constructor=None, edge="edge-bc"):
        constructor = self.constructor if constructor is None else constructor
        return next(option for option in constructor.options if option.target == edge
                    and properties(option.values) == {"source": source, "target": target})

    def fields(self, snapshot, element_id, **values):
        return replace(snapshot, elements=tuple(
            replace(element, properties=tuple(Property(item.name, values.get(item.name, item.value))
                                              for item in element.properties))
            if element.id == element_id else element for element in snapshot.elements))

    def element(self, snapshot, element_id, **changes):
        return replace(snapshot, elements=tuple(replace(e, **changes) if e.id == element_id else e
                                                for e in snapshot.elements))

    def evaluate(self, proposal, snapshot=None):
        snapshot = self.snapshot if snapshot is None else snapshot
        kernel = ModelKernel(snapshot, self.meta, self.plan, check_tasks, frozenset({"test"}))
        candidate = kernel.preview(proposal).candidate
        return candidate, check_tasks(candidate, self.plan)

    def test_fixed_space_is_cartesian_sorted_and_does_not_drop_disallowed_options(self):
        original = digest(self.snapshot)
        actual = [(option.target, properties(option.values)["source"], properties(option.values)["target"])
                  for option in self.constructor.options]
        nodes = ("node-a", "node-b", "node-c")
        self.assertEqual(actual, [("edge-bc", source, target) for source in nodes for target in nodes])
        self.assertEqual(len({option.id for option in self.constructor.options}), 9)
        controls = [self.constructor.control(option) for option in self.constructor.options]
        self.assertEqual([control.option_hash for control in controls],
                         [digest(option) for option in self.constructor.options])
        self.assertEqual([control.status for control in controls],
                         ["exclude", "allow", "allow", "exclude", "exclude", "no_change",
                          "allow", "allow", "exclude"])
        self.assertEqual(digest(self.snapshot), original)

    def test_redirect_removes_only_the_old_edge_before_cycle_detection(self):
        reverse = self.option("node-c", "node-b")
        self.assertEqual(self.constructor.control(reverse).status, "allow")
        candidate, report = self.evaluate(self.constructor.build(reverse))
        self.assertEqual(report.outcomes[0].status, "satisfied")
        self.assertEqual(properties(next(e for e in candidate.elements if e.id == "edge-bc").properties),
                         {"source": "node-c", "target": "node-b"})
        # Keeping another b->c edge means reversing only edge-bc does form a cycle.
        old = next(e for e in self.snapshot.elements if e.id == "edge-bc")
        parallel = replace(old, id="parallel-bc", name="parallel-bc")
        snapshot = replace(self.snapshot, elements=self.snapshot.elements + (parallel,))
        root = next(e for e in snapshot.elements if e.id == "graph")
        snapshot = self.element(snapshot, "graph", dependencies=root.dependencies + (parallel.id,))
        constructor = self.prepare(snapshot=snapshot, space=replace(self.space, base=ref(snapshot)))
        reverse = self.option("node-c", "node-b", constructor)
        self.assertEqual(constructor.control(reverse).status, "exclude")
        self.assertEqual(constructor.control(reverse).reason, "redirect_would_create_cycle")

    def test_no_change_has_no_proposal_and_does_not_mutate_the_base(self):
        original = digest(self.snapshot)
        option = self.option("node-b", "node-c")
        self.assertEqual(self.constructor.control(option).status, "no_change")
        with self.assertRaises(ContractError):
            self.constructor.build(option)
        self.assertEqual(digest(self.snapshot), original)

    def test_builder_updates_both_endpoints_and_exact_endpoint_dependencies(self):
        proposal = self.constructor.build(self.option("node-a", "node-c"))
        self.assertEqual(proposal.base, ref(self.snapshot))
        self.assertEqual(proposal.intent_refs, self.evidence)
        self.assertEqual(proposal.operations, (
            SetProperty("set_property", "edge-bc", "source", "node-a"),
            SetProperty("set_property", "edge-bc", "target", "node-c"),
            SetDependencies("set_dependencies", "edge-bc", ("node-a", "node-c"), True)))
        _, report = self.evaluate(proposal)
        self.assertTrue(report.satisfied)
        changed_space = replace(self.space, version="2")
        constructor = self.prepare(space=changed_space)
        self.assertNotEqual(proposal.proposal_id,
                            constructor.build(self.option("node-a", "node-c", constructor)).proposal_id)

    def test_terminal_only_builder_can_bypass_control_but_terminal_checker_rejects_cycle(self):
        for source, target in (("node-a", "node-a"), ("node-b", "node-a")):
            with self.subTest(source=source, target=target):
                option = self.option(source, target)
                self.assertEqual(self.constructor.control(option).status, "exclude")
                proposal = self.constructor.build(option)
                candidate, report = self.evaluate(proposal)
                self.assertEqual(report.outcomes[0].status, "violated")
                self.assertFalse(report.satisfied)
                self.assertEqual(candidate.revision, self.snapshot.revision + 1)
        self_loop = self.constructor.build(self.option("node-a", "node-a"))
        self.assertEqual(self_loop.operations[-1].dependencies, ("node-a",))

    def test_dag_control_does_not_claim_fixed_reachability_will_pass(self):
        option = self.option("node-a", "node-b")
        self.assertEqual(self.constructor.control(option).status, "allow")
        _, report = self.evaluate(self.constructor.build(option))
        self.assertEqual([outcome.status for outcome in report.outcomes],
                         ["satisfied", "violated", "satisfied"])
        self.assertEqual(self.constructor.plan.check_plan_hash, digest(self.plan))
        self.assertEqual([control.stage for control in self.constructor.plan.controls],
                         ["construction", "terminal-only", "terminal-only"])
        self.assertEqual(self.constructor.plan.residual, ("fixed-positive", "fixed-negative"))
        self.assertTrue(all(control.remaining == "independent terminal check required"
                            for control in self.constructor.plan.controls))

    def test_altered_option_ids_targets_values_or_scalar_types_cannot_escape_fixed_space(self):
        option = self.option("node-a", "node-c")
        variants = [replace(option, id="invented"), replace(option, target="edge-ab"),
                    *(replace(option, id=f"{self.space.id}/option-{suffix}")
                      for suffix in ("0", "-1", "999999", "01", "1a", "１", "9" * 5000)),
                    replace(option, values=(Property("source", "node-b"), Property("target", "node-c"))),
                    replace(option, values=(Property("source", True), Property("target", "node-c"))),
                    replace(option, values=option.values + (Property("extra", "node-a"),)),
                    replace(option, values=option.values + (option.values[0],))]
        for altered in variants:
            with self.subTest(option=altered):
                with self.assertRaises(ContractError):
                    self.constructor.control(altered)
                with self.assertRaises(ContractError):
                    self.constructor.build(altered)

    def test_invalid_base_graphs_are_rejected_before_options_can_be_used(self):
        candidates = [self.fields(self.snapshot, "edge-ab", target="node-a"),
                      self.fields(self.snapshot, "edge-ab", target="missing"),
                      self.element(self.snapshot, "edge-bc", parent="node-a"),
                      self.element(self.snapshot, "graph", dependencies=()),
                      self.element(self.snapshot, "graph", dependencies_complete=True),
                      self.element(self.snapshot, "edge-bc", dependencies=()),
                      replace(self.snapshot, elements=self.snapshot.elements + (self.snapshot.elements[0],))]
        for snapshot in candidates:
            with self.subTest(base=digest(snapshot)), self.assertRaises(ContractError):
                self.prepare(snapshot=snapshot, space=replace(self.space, base=ref(snapshot)))

    def test_space_requires_bound_model_task_identity_exact_shape_and_valid_members(self):
        variants = [replace(self.space, id=" "), replace(self.space, version=""),
                    replace(self.space, base=replace(self.space.base, revision=1)),
                    replace(self.space, task_ref=replace(self.space.task_ref, project_id="other")),
                    replace(self.space, graph="missing"), replace(self.space, graph="node-a"),
                    replace(self.space, edges=("node-a",)), replace(self.space, edges=("edge-ab", "edge-ab")),
                    replace(self.space, sources=("graph",)), replace(self.space, destinations=("missing",)),
                    replace(self.space, sources=("node-a", "node-a")),
                    replace(self.space, destinations=("node-a", "node-a")),
                    replace(self.space, max_options=True), replace(self.space, max_options=-1)]
        wrong_shape = to_data(self.space)
        wrong_shape["extra"] = "ignored?"
        variants.append(wrong_shape)
        for space in variants:
            with self.subTest(space=space), self.assertRaises(ContractError):
                self.prepare(space=space)

    def test_only_the_selected_graph_dag_rule_is_claimed_and_unknown_rules_remain_residual(self):
        unknown = Obligation("unknown", "1", "unsupported", "graph", "root", ())
        plan = replace(self.plan, obligations=self.plan.obligations + (unknown,))
        constructor = self.prepare(plan=plan)
        self.assertEqual(constructor.plan.controls[-1].stage, "terminal-only")
        self.assertIn("unknown", constructor.plan.residual)
        for obligation in (replace(self.plan.obligations[0], field="bad"),
                           replace(self.plan.obligations[0], parameters=(Property("extra", True),)),
                           replace(self.plan.obligations[0], target="other-graph")):
            with self.subTest(obligation=obligation), self.assertRaises(ContractError):
                self.prepare(plan=replace(self.plan, obligations=(obligation,)))

    def test_empty_declared_space_stays_empty_and_zero_budget_does_not_truncate_space(self):
        for field in ("edges", "sources", "destinations"):
            with self.subTest(field=field):
                self.assertEqual(self.prepare(space=replace(self.space, **{field: ()})).options, ())
        self.assertEqual(len(self.prepare(space=replace(self.space, max_options=0)).options), 9)

    def test_intent_refs_are_required_and_validated(self):
        for references in ((), (replace(self.evidence[0], locator=""),),
                           (replace(self.evidence[0], source=replace(self.task.task_ref, content_hash="bad")),)):
            with self.subTest(references=references), self.assertRaises(ContractError):
                prepare_dag(self.snapshot, self.plan, self.space, references)

    def test_editable_edge_cannot_lose_extra_dependencies_or_upgrade_incomplete_dependencies(self):
        variants = ({"dependencies": ("node-a", "node-b", "node-c")},
                    {"dependencies_complete": False},
                    {"dependencies": ("node-b", "node-c", "node-c")})
        for changes in variants:
            snapshot = self.element(self.snapshot, "edge-bc", **changes)
            with self.subTest(changes=changes), self.assertRaises(ContractError) as raised:
                self.prepare(snapshot=snapshot, space=replace(self.space, base=ref(snapshot)))
            self.assertEqual(raised.exception.code, "unsupported")

    def test_unedited_edges_preserve_their_extra_and_incomplete_dependencies(self):
        snapshot = self.element(self.snapshot, "edge-ab", dependencies=("node-a", "node-b", "node-c"),
                                dependencies_complete=False)
        constructor = self.prepare(snapshot=snapshot, space=replace(self.space, base=ref(snapshot)))
        option = self.option("node-a", "node-c", constructor)
        self.assertEqual(constructor.control(option).status, "allow")
        proposal = constructor.build(option)
        candidate, report = self.evaluate(proposal, snapshot=snapshot)
        self.assertTrue(report.satisfied)
        before = next(element for element in snapshot.elements if element.id == "edge-ab")
        after = next(element for element in candidate.elements if element.id == "edge-ab")
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
