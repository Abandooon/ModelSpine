"""Versioned design models. One in-memory owner, thread-atomic commits."""
from dataclasses import replace
from threading import RLock
from uuid import uuid4

from modelspine_protocols import (
    AddElement, Applicability, ChangeProposal, Checker, CheckPlan, Commit, Confirm, Decision,
    DependencyFingerprint, Element, ElementRef, EvidenceRecord, ImpactSet, Metamodel,
    Preview, Property, RemoveElement, Rename, SetDependencies, SetProperty, Snapshot,
    ValidationReport, checked, digest, properties, ref, require, validate_evidence_refs,
    validate_model, validate_plan,
)


def impact(before: Snapshot, after: Snapshot) -> ImpactSet:
    before, after = checked(before, Snapshot), checked(after, Snapshot)
    require((before.project_id, before.model_id, before.metamodel, before.metamodel_hash) == (
        after.project_id, after.model_id, after.metamodel, after.metamodel_hash),
        "impact requires the same model and metamodel", "conflict")
    old, new = ({e.id: e for e in s.elements} for s in (before, after))
    changed = {key for key in old.keys() | new.keys() if old.get(key) != new.get(key)}
    reverse: dict[str, set[str]] = {}
    unknown = set()
    for snapshot in (before, after):
        for element in snapshot.elements:
            if not element.dependencies_complete:
                unknown.add(element.id)
            for dependency in element.dependencies:
                reverse.setdefault(dependency, set()).add(element.id)
    affected, todo = set(changed), list(changed)
    while todo:
        for dependent in reverse.get(todo.pop(), ()):
            if dependent not in affected:
                affected.add(dependent)
                todo.append(dependent)
    return ImpactSet(tuple(sorted(changed)), tuple(sorted(affected)), tuple(sorted(unknown)))


def dependency_fingerprints(snapshot: Snapshot, scope: tuple[str, ...]):
    elements = {e.id: e for e in snapshot.elements}
    seen, todo, complete = set(), list(scope), True
    while todo:
        key = todo.pop()
        if key in seen:
            continue
        require(key in elements, f"missing evidence dependency {key}", "not_found")
        seen.add(key)
        element = elements[key]
        complete = complete and element.dependencies_complete
        todo.extend(element.dependencies)
    return (tuple(DependencyFingerprint(key, digest(elements[key])) for key in sorted(seen)), complete)


def applicability(evidence: EvidenceRecord, snapshot: Snapshot, plan: CheckPlan,
                  tool: str, tool_version: str) -> Applicability:
    old, now, binding = evidence.snapshot, ref(snapshot), evidence.report.binding
    if (old.project_id, old.model_id, old.metamodel, old.metamodel_hash) != (
            now.project_id, now.model_id, now.metamodel, now.metamodel_hash):
        return Applicability(evidence.id, "stale", "model/metamodel identity changed")
    if (binding.plan_hash, binding.assumptions, binding.tool, binding.tool_version) != (
            digest(plan), plan.assumptions, tool, tool_version):
        return Applicability(evidence.id, "stale", "rule/tool/assumptions changed")
    elements = {e.id: e for e in snapshot.elements}
    if any(d.element_id not in elements or digest(elements[d.element_id]) != d.content_hash
           for d in evidence.dependencies):
        return Applicability(evidence.id, "stale", "dependency fingerprint changed")
    if not evidence.complete:
        return Applicability(evidence.id, "unknown", "dependency set incomplete")
    current, complete = dependency_fingerprints(snapshot, binding.scope)
    if not complete:
        return Applicability(evidence.id, "unknown", "current dependency set incomplete")
    if current != evidence.dependencies:
        return Applicability(evidence.id, "stale", "dependency set changed")
    return Applicability(evidence.id, "current", "complete dependencies and checking context unchanged")


class ModelKernel:
    def __init__(self, snapshot: Snapshot, metamodel: Metamodel, plan: CheckPlan,
                 checker: Checker, editors: frozenset[str]):
        self._metamodel = checked(metamodel, Metamodel)
        self._current = checked(snapshot, Snapshot)
        validate_model(self._current, self._metamodel)
        self._plan = validate_plan(plan)
        require(callable(checker), "checker must be callable")
        self._checker = checker
        require(bool(editors) and all(type(a) is str and a for a in editors), "empty editors")
        self._editors = frozenset(editors)
        self._lock = RLock()
        self._history = {snapshot.revision: self._current}
        self._decisions: dict[str, tuple[Decision, ValidationReport]] = {}
        self._commits: dict[str, tuple[str, str, Decision, Commit]] = {}
        self._evidence: list[EvidenceRecord] = []
        self._notes: list[str] = []

    @property
    def plan(self) -> CheckPlan:
        return self._plan

    def snapshot(self, revision: int | None = None) -> Snapshot:
        with self._lock:
            if revision is None:
                return self._current
            require(type(revision) is int and revision in self._history, "unknown revision", "not_found")
            return self._history[revision]

    def resolve(self, reference: ElementRef) -> Element:
        reference = checked(reference, ElementRef)
        snapshot = self.snapshot(reference.snapshot.revision)
        require(reference.snapshot == ref(snapshot), "reference version/hash mismatch", "conflict")
        found = next((e for e in snapshot.elements if e.id == reference.element_id), None)
        require(found is not None, "missing element", "not_found")
        return found

    def add_note(self, text: str) -> None:
        require(type(text) is str, "notes accept text only")
        with self._lock:
            self._notes.append(text)

    def preview(self, proposal: ChangeProposal) -> Preview:
        proposal = checked(proposal, ChangeProposal)
        with self._lock:
            require(proposal.base == ref(self._current), "stale/mismatched base", "conflict")
            require(bool(proposal.proposal_id and proposal.operations), "empty proposal")
            validate_evidence_refs(proposal.intent_refs)
            elements = {e.id: e for e in self._current.elements}
            used_ids = {element.id for snapshot in self._history.values() for element in snapshot.elements}
            # A detached working set; no state is changed until the whole batch is valid.
            for operation in proposal.operations:
                if isinstance(operation, AddElement):
                    require(operation.element.id not in used_ids, "element ID already used in this history/batch", "conflict")
                    elements[operation.element.id] = operation.element
                    used_ids.add(operation.element.id)
                    continue
                require(operation.target in elements, "operation target missing", "not_found")
                element = elements[operation.target]
                if isinstance(operation, Rename):
                    elements[element.id] = replace(element, name=operation.name)
                elif isinstance(operation, SetProperty):
                    values = properties(element.properties)
                    require(operation.field in values, "unknown property")
                    elements[element.id] = replace(element, properties=tuple(
                        Property(p.name, operation.value if p.name == operation.field else p.value)
                        for p in element.properties))
                elif isinstance(operation, SetDependencies):
                    elements[element.id] = replace(element, dependencies=operation.dependencies,
                                                    dependencies_complete=operation.complete)
                elif isinstance(operation, RemoveElement):
                    del elements[element.id]
                elif isinstance(operation, Confirm):
                    elements[element.id] = replace(element, confirmed=operation.confirmed)
            candidate = replace(self._current, revision=self._current.revision + 1,
                                elements=tuple(elements.values()))
            validate_model(candidate, self._metamodel)
            return Preview(digest(proposal), digest(candidate), candidate, impact(self._current, candidate))

    def _authorized(self, actor: str) -> None:
        require(type(actor) is str and actor in self._editors, "actor cannot edit this model", "forbidden")

    def _check(self, snapshot: Snapshot, scope: tuple[str, ...] | None = None) -> ValidationReport:
        """Validate the selected checker's output without duplicating its rules."""
        targets = {o.target for o in self._plan.obligations}
        scope = tuple(sorted(targets)) if scope is None else scope
        require(type(scope) is tuple and bool(scope) and all(type(s) is str for s in scope),
                "invalid check scope")
        require(len(set(scope)) == len(scope) and set(scope) <= targets, "invalid check scope")
        scope = tuple(sorted(scope))
        # A backend exception aborts the operation; never substitute a cached or empty report.
        report = checked(self._checker(snapshot, self._plan, scope), ValidationReport)
        binding = report.binding
        require((binding.candidate_hash, binding.plan_hash, binding.scope, binding.assumptions) == (
            digest(snapshot), digest(self._plan), scope, self._plan.assumptions),
            "checker returned mismatched report binding", "conflict")
        require(bool(binding.tool and binding.tool_version), "checker identity/version missing", "conflict")
        expected = {o.id: o.version for o in self._plan.obligations if o.target in scope}
        actual = {o.obligation_id: o.obligation_version for o in report.outcomes}
        require(len(actual) == len(report.outcomes) and actual == expected,
                "checker returned incomplete, duplicate or mismatched obligation coverage", "conflict")
        return report

    def decide(self, proposal: ChangeProposal, report: ValidationReport, actor: str,
               policy: str = "satisfied-save") -> Decision:
        with self._lock:
            self._authorized(actor)
            require(policy in ("satisfied-save", "checked-save"), "unsupported save policy", "unsupported")
            preview = self.preview(proposal)
            report = checked(report, ValidationReport)
            # The checker is a trusted in-process dependency, not a caller-supplied report flag.
            expected = self._check(preview.candidate)
            require(report == expected, "report does not match candidate/plan/scope/checker", "conflict")
            require(policy == "checked-save" or report.satisfied, "unsatisfied model-save obligations")
            decision = Decision(uuid4().hex, preview.proposal_hash, preview.candidate_hash,
                                digest(report), report.binding, actor, policy)
            self._decisions[decision.token] = (decision, report)
            return decision

    def apply(self, proposal: ChangeProposal, decision: Decision, actor: str) -> Commit:
        proposal, decision = checked(proposal, ChangeProposal), checked(decision, Decision)
        with self._lock:
            self._authorized(actor)
            if proposal.proposal_id in self._commits:
                old_hash, old_actor, old_decision, commit = self._commits[proposal.proposal_id]
                require((digest(proposal), actor, decision) == (old_hash, old_actor, old_decision),
                        "proposal ID reused with different content/authority", "conflict")
                return commit
            preview = self.preview(proposal)
            registered = self._decisions.get(decision.token)
            require(registered is not None and registered[0] == decision, "unissued/altered decision", "forbidden")
            require((decision.proposal_hash, decision.candidate_hash, decision.actor) == (
                preview.proposal_hash, preview.candidate_hash, actor), "decision is for another candidate/actor", "conflict")
            report = registered[1]
            require(report == self._check(preview.candidate), "checking context changed", "conflict")
            states = self._evidence_status(preview.candidate, report)
            commit = Commit(proposal.proposal_id, ref(preview.candidate), report, decision.policy,
                            preview.impact, states)
            # No fallible validation or external side effects after this point.
            self._current = preview.candidate
            self._history[self._current.revision] = self._current
            self._commits[proposal.proposal_id] = (preview.proposal_hash, actor, decision, commit)
            return commit

    def record_evidence(self, report: ValidationReport) -> EvidenceRecord:
        report = checked(report, ValidationReport)
        with self._lock:
            require(report == self._check(self._current, report.binding.scope),
                    "evidence is not a current authentic check", "conflict")
            fingerprints, complete = dependency_fingerprints(self._current, report.binding.scope)
            record = EvidenceRecord(digest(report), ref(self._current), report, fingerprints, complete)
            if record not in self._evidence:
                self._evidence.append(record)
            return record

    def _evidence_status(self, snapshot: Snapshot, report: ValidationReport) -> tuple[Applicability, ...]:
        context = report.binding
        return tuple(applicability(e, snapshot, self._plan, context.tool, context.tool_version)
                     for e in self._evidence)

    def evidence_status(self) -> tuple[Applicability, ...]:
        with self._lock:
            return self._evidence_status(self._current, self._check(self._current))
