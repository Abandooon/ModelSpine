"""Explicit checkers for two finite engineering configurations, not a general DSL."""
from modelspine_protocols import (
    CheckPlan, Outcome, ReportBinding, Snapshot, ValidationReport,
    checked, digest, properties, require, validate_plan,
)

VERSION = "0.1.0"


def _members(snapshot, root, root_kind):
    if root.kind != root_kind:
        return (), ("error", (f"{root.id}:wrong_root_kind",))
    # Membership is selected by parent. v0.1 cannot track the absence of future
    # members, so a complete dependency claim would allow unsafe evidence reuse.
    if root.dependencies_complete:
        return (), ("error", (f"{root.id}:membership_completeness_not_supported",))
    elements = {element.id: element for element in snapshot.elements}
    for element in snapshot.elements:
        current, seen, depth, nested = element, {element.id}, 0, False
        while current.parent is not None:
            parent = elements.get(current.parent)
            if parent is None:
                return (), ("error", (f"{current.id}:missing_parent",))
            if parent.id in seen:
                return (), ("error", (f"{element.id}:parent_cycle",))
            seen.add(parent.id)
            depth += 1
            nested = nested or (parent.id == root.id and depth > 1)
            current = parent
        if nested:
            return (), ("violated", (f"{root.id}:not_flat_membership",))
    members = tuple(sorted((e for e in snapshot.elements if e.parent == root.id), key=lambda e: e.id))
    if not {e.id for e in members} <= set(root.dependencies):
        return (), ("error", (f"{root.id}:member_read_dependencies_missing",))
    return members, None


def _structure(snapshot, root, obligation):
    members, failure = _members(snapshot, root, "graph")
    if failure:
        return failure
    nodes = {e.id: e for e in members if e.kind == "node"}
    edges = tuple(e for e in members if e.kind == "edge")
    if len(nodes) + len(edges) != len(members):
        return "violated", (f"{root.id}:unsupported_member_kind",)
    if properties(root.properties).get("root") not in nodes:
        return "violated", (f"{root.id}:invalid_root_node",)
    adjacency = {key: [] for key in nodes}
    indegree = {key: 0 for key in nodes}
    for edge in edges:
        values = properties(edge.properties)
        source, target = values.get("source"), values.get("target")
        if source not in nodes or target not in nodes:
            return "violated", (f"{edge.id}:invalid_endpoint",)
        if not {source, target} <= set(edge.dependencies):
            return "error", (f"{edge.id}:endpoint_read_dependencies_missing",)
        adjacency[source].append(target)
        indegree[target] += 1
    todo = [key for key in nodes if indegree[key] == 0]
    visited = 0
    while todo:
        current = todo.pop()
        visited += 1
        for target in adjacency[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                todo.append(target)
    if visited != len(nodes):
        return "violated", (f"{root.id}:directed_cycle",)
    return "satisfied", ()


def _automaton(snapshot, root, obligation):
    members, failure = _members(snapshot, root, "machine")
    if failure:
        return failure
    states = {e.id: e for e in members if e.kind == "state"}
    transitions = tuple(e for e in members if e.kind == "transition")
    if len(states) + len(transitions) != len(members):
        return "violated", (f"{root.id}:unsupported_member_kind",)
    values = properties(root.properties)
    initial, alphabet = values.get("initial"), values.get("alphabet")
    if initial not in states:
        return "violated", (f"{root.id}:invalid_initial_state",)
    if type(alphabet) is not str or not alphabet or len(set(alphabet)) != len(alphabet):
        return "violated", (f"{root.id}:invalid_finite_alphabet",)
    accepting = {key: properties(state.properties).get("accepting") for key, state in states.items()}
    if any(type(value) is not bool for value in accepting.values()):
        return "violated", (f"{root.id}:invalid_accepting_flag",)
    table = {}
    for transition in transitions:
        fields = properties(transition.properties)
        source, target, symbol = fields.get("source"), fields.get("target"), fields.get("symbol")
        if source not in states or target not in states:
            return "violated", (f"{transition.id}:invalid_endpoint",)
        if not {source, target} <= set(transition.dependencies):
            return "error", (f"{transition.id}:endpoint_read_dependencies_missing",)
        if type(symbol) is not str or len(symbol) != 1 or symbol not in alphabet:
            return "violated", (f"{transition.id}:invalid_finite_symbol",)
        if (source, symbol) in table:
            return "violated", (f"{root.id}:nondeterministic:{source}:{symbol}",)
        table[source, symbol] = target
    if obligation.kind == "deterministic_automaton":
        return "satisfied", ()
    trace = values.get("trace")
    if type(trace) is not str or any(symbol not in alphabet for symbol in trace):
        return "violated", (f"{root.id}:trace_outside_alphabet",)
    current = initial
    for index, symbol in enumerate(trace):
        if (current, symbol) not in table:
            return "violated", (f"{root.id}:trace_blocked:{index}",)
        current = table[current, symbol]
    if not accepting[current]:
        return "violated", (f"{root.id}:trace_not_accepted:{current}",)
    return "satisfied", ()


def _check(snapshot, plan, scope, supported, evaluate, tool):
    snapshot, plan = checked(snapshot, Snapshot), validate_plan(plan)
    targets = {o.target for o in plan.obligations}
    scope = tuple(sorted(targets)) if scope is None else scope
    require(type(scope) is tuple and bool(scope) and all(type(s) is str for s in scope), "invalid check scope")
    require(len(set(scope)) == len(scope) and set(scope) <= targets, "invalid check scope")
    scope = tuple(sorted(scope))
    elements = {element.id: element for element in snapshot.elements}
    require(len(elements) == len(snapshot.elements), "duplicate element ID")
    outcomes = []
    for obligation in plan.obligations:
        if obligation.target not in scope:
            continue
        if obligation.target not in elements:
            result = "error", (f"{obligation.target}:missing_target",)
        elif obligation.kind not in supported:
            result = "unknown", (f"{obligation.target}:unsupported:{obligation.kind}",)
        elif obligation.field != supported[obligation.kind] or obligation.parameters:
            result = "error", (f"{obligation.id}:invalid_rule_configuration",)
        elif obligation.field not in properties(elements[obligation.target].properties):
            result = "error", (f"{obligation.target}:missing_field:{obligation.field}",)
        else:
            result = evaluate(snapshot, elements[obligation.target], obligation)
        outcomes.append(Outcome(obligation.id, obligation.version, result[0], result[1]))
    return ValidationReport(
        ReportBinding(digest(snapshot), digest(plan), scope, plan.assumptions, tool, VERSION),
        tuple(outcomes),
    )


def check_structure(snapshot: Snapshot, plan: CheckPlan,
                    scope: tuple[str, ...] | None = None) -> ValidationReport:
    """Check declared direct graph members and directed acyclicity."""
    return _check(snapshot, plan, scope, {"directed_acyclic_graph": "root"},
                  _structure, "modelspine-structural-graph-checker")


def check_automaton(snapshot: Snapshot, plan: CheckPlan,
                    scope: tuple[str, ...] | None = None) -> ValidationReport:
    """Check a deterministic finite automaton and concrete finite trace acceptance."""
    return _check(snapshot, plan, scope,
                  {"deterministic_automaton": "initial", "finite_trace_acceptance": "trace"},
                  _automaton, "modelspine-finite-automaton-checker")
