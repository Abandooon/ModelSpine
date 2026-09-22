"""Test-owned, finite reference acceptance; never a production checker.

Expectations come from evaluator-pinned bytes, not candidate fields or a development
CheckPlan. Independent construction here means separate engineering logic and
fixed inputs; shared authorship and public fixtures do not establish blind truth.
"""
from collections import deque
from dataclasses import dataclass
from hashlib import sha256

from modelspine_protocols import (
    ArtifactRef, ContractError, MetamodelRef, Snapshot, SnapshotRef,
    checked, loads, ref, require,
)


@dataclass(frozen=True)
class ModelIdentity:
    project_id: str
    model_id: str
    metamodel: MetamodelRef
    metamodel_hash: str


@dataclass(frozen=True)
class ReferenceCase:
    id: str
    kind: str
    target: str
    input: str
    destination: str | None
    expected: bool | None


@dataclass(frozen=True)
class EvaluationSpec:
    schema: str
    id: str
    version: str
    task_ref: ArtifactRef
    model: ModelIdentity
    cases: tuple[ReferenceCase, ...]


@dataclass(frozen=True)
class PinnedEvaluationSpec:
    spec_ref: ArtifactRef
    content: bytes


@dataclass(frozen=True)
class ReferenceOutcome:
    case_id: str
    status: str
    finding: str


@dataclass(frozen=True)
class EvaluationResult:
    spec_ref: ArtifactRef
    task_ref: ArtifactRef
    candidate_ref: SnapshotRef
    outcomes: tuple[ReferenceOutcome, ...]

    @property
    def satisfied(self):
        return bool(self.outcomes) and all(o.status == "satisfied" for o in self.outcomes)


def _read_spec(pinned):
    require(type(pinned) is PinnedEvaluationSpec, "reference specification must be pinned")
    expected = checked(pinned.spec_ref, ArtifactRef)
    require(type(pinned.content) is bytes, "reference specification must contain exact bytes")
    require(sha256(pinned.content).hexdigest() == expected.content_hash,
            "reference specification differs from evaluator-pinned bytes", "conflict")
    try:
        text = pinned.content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("invalid", "reference specification is not UTF-8") from exc
    spec = loads(EvaluationSpec, text)
    require(spec.schema == "task-evaluation/0.1", "unsupported reference specification", "unsupported")
    require((expected.project_id, expected.artifact_id, expected.revision) ==
            (spec.model.project_id, spec.id, spec.version), "reference identity mismatch", "conflict")
    require(bool(spec.id and spec.version and spec.model.model_id and spec.cases), "empty reference specification")
    require(len({c.id for c in spec.cases}) == len(spec.cases), "duplicate reference case")
    require(all(c.id and c.kind and c.target for c in spec.cases), "empty reference case identity")
    require(spec.task_ref.project_id == spec.model.project_id, "task/project mismatch", "conflict")
    require(bool(spec.task_ref.artifact_id and spec.task_ref.revision), "missing task identity")
    for value in (spec.task_ref.content_hash, spec.model.metamodel_hash):
        require(len(value) == 64 and all(c in "0123456789abcdef" for c in value), "invalid reference hash")
    return spec


def pin_evaluation_spec(raw_json: str | bytes, expected_ref: ArtifactRef) -> PinnedEvaluationSpec:
    """The evaluator supplies expected_ref before receiving candidate changes.

    Do not derive expected_ref from a candidate-controlled file at evaluation time.
    This is a trusted in-process boundary, not a sandbox against arbitrary Python.
    """
    require(type(raw_json) in (str, bytes), "reference input must be UTF-8 text or bytes")
    content = raw_json.encode("utf-8") if type(raw_json) is str else raw_json
    pinned = PinnedEvaluationSpec(checked(expected_ref, ArtifactRef), content)
    _read_spec(pinned)
    return pinned


class _ReferenceFailure(Exception):
    def __init__(self, status, finding):
        self.status, self.finding = status, finding


def _fail(status, finding):
    raise _ReferenceFailure(status, finding)


def _fields(element, schema):
    names = [prop.name for prop in element.properties]
    if len(names) != len(set(names)):
        _fail("error", f"duplicate_property:{element.id}")
    values = {prop.name: prop.value for prop in element.properties}
    if set(schema) - set(values):
        _fail("error", f"missing_property:{element.id}")
    if set(values) - set(schema):
        _fail("unknown", f"unsupported_property:{element.id}")
    if any(type(values[name]) is not expected for name, expected in schema.items()):
        _fail("error", f"invalid_property_type:{element.id}")
    return values


def _members(snapshot, target, kind):
    by_id = {element.id: element for element in snapshot.elements}
    if len(by_id) != len(snapshot.elements):
        _fail("error", "duplicate_element_identity")
    if target not in by_id:
        _fail("error", f"missing_target:{target}")
    root = by_id[target]
    if root.kind != kind or root.parent is not None:
        _fail("error", f"invalid_target_root:{target}")
    children = {key: [] for key in by_id}
    for element in snapshot.elements:
        if element.parent is not None:
            if element.parent not in by_id:
                _fail("error", f"missing_parent:{element.id}")
            children[element.parent].append(element.id)
    # A forest must have every element reachable from a parentless root.
    reached = set()
    pending = deque(element.id for element in snapshot.elements if element.parent is None)
    while pending:
        current = pending.popleft()
        if current in reached:
            _fail("error", "invalid_containment")
        reached.add(current)
        pending.extend(children[current])
    if reached != set(by_id):
        _fail("error", "containment_cycle")
    direct = children[target]
    if any(children[member] for member in direct):
        _fail("violated", f"nested_members_not_supported:{target}")
    return root, tuple(by_id[key] for key in sorted(direct))


def _reachable(start, destinations, edges):
    pending, visited = deque(destinations), set()
    while pending:
        vertex = pending.popleft()
        if vertex == start:
            return True
        if vertex not in visited:
            visited.add(vertex)
            pending.extend(edges[vertex])
    return False


def _graph(snapshot, case):
    root, members = _members(snapshot, case.target, "graph")
    root_fields = _fields(root, {"root": str})
    nodes = {element.id for element in members if element.kind == "node"}
    edges = {node: [] for node in nodes}
    for element in members:
        if element.kind == "node":
            _fields(element, {"label": str})
        elif element.kind == "edge":
            relation = _fields(element, {"source": str, "target": str})
            if relation["source"] not in nodes or relation["target"] not in nodes:
                _fail("violated", f"invalid_graph_endpoint:{element.id}")
            edges[relation["source"]].append(relation["target"])
        else:
            _fail("unknown", f"unsupported_graph_member:{element.kind}")
    if root_fields["root"] not in nodes:
        _fail("violated", "invalid_graph_root")
    if any(_reachable(node, edges[node], edges) for node in nodes):
        _fail("violated", "directed_cycle")
    if case.destination is None:
        _fail("error", "graph_destination_required")
    if case.input not in nodes or case.destination not in nodes:
        _fail("error", "reference_endpoint_missing")
    return _reachable(case.destination, [case.input], edges)


def _automaton(snapshot, case):
    root, members = _members(snapshot, case.target, "machine")
    machine = _fields(root, {"initial": str, "alphabet": str, "trace": str})
    if case.destination is not None:
        _fail("error", "automaton_destination_not_applicable")
    if not machine["alphabet"] or len(set(machine["alphabet"])) != len(machine["alphabet"]):
        _fail("violated", "invalid_alphabet")
    states = {}
    moves = []
    for member in members:
        if member.kind == "state":
            states[member.id] = _fields(member, {"accepting": bool})["accepting"]
        elif member.kind == "transition":
            fields = _fields(member, {"source": str, "target": str, "symbol": str})
            moves.append((member.id, fields["source"], fields["target"], fields["symbol"]))
        else:
            _fail("unknown", f"unsupported_automaton_member:{member.kind}")
    if machine["initial"] not in states:
        _fail("violated", "invalid_initial_state")
    choices = set()
    for identity, source, destination, symbol in moves:
        if source not in states or destination not in states:
            _fail("violated", f"invalid_transition_endpoint:{identity}")
        if len(symbol) != 1 or symbol not in machine["alphabet"]:
            _fail("violated", f"invalid_single_codepoint_symbol:{identity}")
        if (source, symbol) in choices:
            _fail("violated", "nondeterministic_automaton")
        choices.add((source, symbol))
    if any(character not in machine["alphabet"] for character in case.input):
        _fail("unknown", "input_outside_supported_alphabet")
    # Independently unfold one input step at a time; no candidate trace is used.
    active = {machine["initial"]}
    for character in case.input:
        active = {destination for _, source, destination, symbol in moves
                  if source in active and symbol == character}
    return any(states[state] for state in active)


def evaluate_candidate(snapshot: Snapshot, evaluation_spec: PinnedEvaluationSpec) -> EvaluationResult:
    spec = _read_spec(evaluation_spec)
    snapshot = checked(snapshot, Snapshot)
    identity = ModelIdentity(snapshot.project_id, snapshot.model_id, snapshot.metamodel, snapshot.metamodel_hash)
    require(identity == spec.model, "candidate/reference model identity mismatch", "conflict")
    outcomes = []
    for case in spec.cases:
        if case.expected is None:
            outcome = ReferenceOutcome(case.id, "unknown", "expected_behavior_unresolved")
        elif case.kind not in ("graph_reachability", "finite_acceptance"):
            outcome = ReferenceOutcome(case.id, "unknown", f"unsupported_reference_rule:{case.kind}")
        else:
            try:
                observed = _graph(snapshot, case) if case.kind == "graph_reachability" else _automaton(snapshot, case)
                status = "satisfied" if observed == case.expected else "violated"
                outcome = ReferenceOutcome(case.id, status, f"expected={case.expected};observed={observed}")
            except _ReferenceFailure as failure:
                outcome = ReferenceOutcome(case.id, failure.status, failure.finding)
        outcomes.append(outcome)
    return EvaluationResult(evaluation_spec.spec_ref, spec.task_ref, ref(snapshot), tuple(outcomes))
