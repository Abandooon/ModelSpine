"""Construct one edge redirect in a fixed, validated finite DAG edit space."""
from dataclasses import dataclass
from itertools import product
from typing import Literal

from modelspine_generation.bounded import ConstructionDecision, EditOption
from modelspine_protocols import (
    ArtifactRef, ChangeProposal, CheckPlan, EvidenceRef, GenerationControl,
    GenerationPlan, Property, SetDependencies, SetProperty, Snapshot, SnapshotRef,
    checked, digest, properties, ref, require, validate_artifact_ref,
    validate_evidence_refs, validate_plan, validate_snapshot_ref,
)

from finite_models import _graph


@dataclass(frozen=True)
class DagEditSpace:
    schema_version: Literal["dag-edit-space/0.1"]
    id: str
    version: str
    task_ref: ArtifactRef
    base: SnapshotRef
    graph: str
    edges: tuple[str, ...]
    sources: tuple[str, ...]
    destinations: tuple[str, ...]
    max_options: int


@dataclass(frozen=True)
class _DagConstructor:
    _snapshot: Snapshot
    _space: DagEditSpace
    _intent_refs: tuple[EvidenceRef, ...]
    options: tuple[EditOption, ...]
    plan: GenerationPlan

    def _option(self, option):
        option = checked(option, EditOption)
        prefix = f"{self._space.id}/option-"
        ordinal = option.id[len(prefix):] if option.id.startswith(prefix) else ""
        require(ordinal.isascii() and ordinal.isdecimal()
                and len(ordinal) <= len(str(len(self.options))),
                "invalid fixed-space option ID", "conflict")
        index = int(ordinal) - 1
        require(0 <= index < len(self.options), "option index outside fixed space", "conflict")
        expected = self.options[index]
        require(digest(option) == digest(expected),
                "option is not a member of the fixed edit space", "conflict")
        return option

    def _unchanged(self, option):
        edge = next(element for element in self._snapshot.elements if element.id == option.target)
        current, proposed = properties(edge.properties), properties(option.values)
        return all(current[field] == proposed[field] for field in ("source", "target"))

    def control(self, option: EditOption) -> ConstructionDecision:
        option = self._option(option)

        def decision(status, reason):
            return ConstructionDecision(digest(option), status, reason)

        if self._unchanged(option):
            return decision("no_change", "edge_endpoints_unchanged")
        values = properties(option.values)
        source, target = values["source"], values["target"]
        if source == target:
            return decision("exclude", "self_loop")
        # Remove only the selected edge by identity. Parallel edges remain.
        # The base DAG was validated once before this immutable constructor.
        members = tuple(e for e in self._snapshot.elements if e.parent == self._space.graph)
        adjacency = {e.id: [] for e in members if e.kind == "node"}
        for edge in members:
            if edge.kind == "edge" and edge.id != option.target:
                fields = properties(edge.properties)
                adjacency[fields["source"]].append(fields["target"])
        seen, todo = {target}, [target]
        while todo:
            current = todo.pop()
            if current == source:
                return decision("exclude", "redirect_would_create_cycle")
            for following in adjacency[current]:
                if following not in seen:
                    seen.add(following)
                    todo.append(following)
        return decision("allow", "redirect_preserves_dag")

    def build(self, option: EditOption) -> ChangeProposal:
        """Build a fixed-space edit; the selected controller owns DAG filtering.

        This deliberately permits cyclic edits for explicit terminal-only
        comparisons. The common terminal checker must still reject them.
        """
        option = self._option(option)
        require(not self._unchanged(option), "no_change option has no construction proposal")
        values = properties(option.values)
        source, target = values["source"], values["target"]
        return ChangeProposal(
            "0.1", f"{self._space.id}/{digest((self._space, option))}", ref(self._snapshot),
            (SetProperty("set_property", option.target, "source", source),
             SetProperty("set_property", option.target, "target", target),
             SetDependencies("set_dependencies", option.target, tuple(sorted({source, target})), True)),
            self._intent_refs,
        )


def prepare_dag(snapshot: Snapshot, check_plan: CheckPlan, space: DagEditSpace,
                intent_refs: tuple[EvidenceRef, ...]) -> _DagConstructor:
    """Pin the finite graph, Cartesian endpoint space, and construction claims.

    The host separately validates the declared metamodel and raw task/space
    bytes. This boundary validates graph semantics and its exact model binding.
    """
    snapshot, space = checked(snapshot, Snapshot), checked(space, DagEditSpace)
    check_plan = validate_plan(check_plan)
    validate_snapshot_ref(space.base)
    validate_artifact_ref(space.task_ref)
    require(space.base == ref(snapshot) and space.task_ref.project_id == snapshot.project_id,
            "edit space task/model binding mismatch", "conflict")
    require(bool(space.id.strip() and space.version.strip() and space.graph.strip()), "incomplete edit space")
    require(space.max_options >= 0, "negative option budget")
    intent_refs = checked(intent_refs, tuple[EvidenceRef, ...])
    require(bool(intent_refs), "construction requires intent references")
    validate_evidence_refs(intent_refs)
    elements = {element.id: element for element in snapshot.elements}
    require(len(elements) == len(snapshot.elements), "duplicate element ID")
    root = elements.get(space.graph)
    require(root is not None, "missing edit graph", "not_found")
    _, failure = _graph(snapshot, root)
    require(failure is None, "invalid base graph: " + (";".join(failure[1]) if failure else ""))
    for names, kind in ((space.edges, "edge"), (space.sources, "node"), (space.destinations, "node")):
        require(len(set(names)) == len(names), "duplicate edit-space member")
        require(all(name.strip() and name in elements and elements[name].kind == kind
                    and elements[name].parent == space.graph for name in names),
                "edit-space member is outside the selected graph or has the wrong kind")
    for name in space.edges:
        edge = elements[name]
        endpoints = properties(edge.properties)
        require(edge.dependencies_complete
                and len(set(edge.dependencies)) == len(edge.dependencies)
                and set(edge.dependencies) == {endpoints["source"], endpoints["target"]},
                "editable edge requires exact, complete endpoint dependencies", "unsupported")
    controls, residual = [], []
    for obligation in check_plan.obligations:
        controlled = obligation.kind == "directed_acyclic_graph" and obligation.target == space.graph
        if controlled:
            require(obligation.field == "root" and not obligation.parameters, "invalid DAG obligation")
        else:
            residual.append(obligation.id)
        controls.append(GenerationControl(
            obligation.id, obligation.version, obligation.kind,
            "construction" if controlled else "terminal-only",
            "reachability after removing redirected edge" if controlled else "outside DAG construction support",
            "independent terminal check required",
        ))
    require(any(control.stage == "construction" for control in controls),
            "edit graph has no supported DAG obligation", "unsupported")
    options = tuple(EditOption(f"{space.id}/option-{index}", edge,
                               (Property("source", source), Property("target", destination)))
                    for index, (edge, source, destination) in enumerate(product(
                        sorted(space.edges), sorted(space.sources), sorted(space.destinations)), start=1))
    return _DagConstructor(snapshot, space, intent_refs, options,
                           GenerationPlan(digest(check_plan), tuple(controls), tuple(residual)))
