"""Fixed-target checks on the original candidate; no task or input substitution."""
from modelspine_protocols import (
    CheckPlan, Outcome, ReportBinding, Snapshot, ValidationReport,
    checked, digest, properties, require, select_scope, validate_plan,
)
from finite_models import _automaton, _graph, _machine, _run_input, _structure

TOOL = "modelspine-task-checker"
VERSION = "0.1.0"

_FIELDS = {
    "directed_acyclic_graph": "root",
    "deterministic_automaton": "initial",
    "finite_trace_acceptance": "trace",
    "graph_reachability": "root",
    "trace_acceptance": "initial",
}


def _reachability(snapshot, root, obligation, parameters):
    expected_fields = {"source", "destination", "expected_reachable"}
    if (set(parameters) != expected_fields or type(parameters.get("source")) is not str
            or type(parameters.get("destination")) is not str
            or type(parameters.get("expected_reachable")) is not bool):
        return "error", (f"{obligation.id}:invalid_reachability_parameters",)
    adjacency, failure = _graph(snapshot, root)
    if failure:
        return failure
    source, destination = parameters["source"], parameters["destination"]
    if source not in adjacency or destination not in adjacency:
        return "error", (f"{obligation.id}:task_endpoint_not_in_graph",)
    seen, todo = {source}, [source]
    while todo:
        for target in adjacency[todo.pop()]:
            if target not in seen:
                seen.add(target)
                todo.append(target)
    reachable = destination in seen
    if reachable == parameters["expected_reachable"]:
        return "satisfied", ()
    return "violated", (f"{obligation.id}:reachability_expectation_mismatch",)


def _trace_acceptance(snapshot, root, obligation, parameters):
    if (set(parameters) != {"input", "expected_accept"} or type(parameters.get("input")) is not str
            or type(parameters.get("expected_accept")) is not bool):
        return "error", (f"{obligation.id}:invalid_trace_parameters",)
    machine, failure = _machine(snapshot, root)
    if failure:
        return failure
    task_input = parameters["input"]
    if any(symbol not in machine[1] for symbol in task_input):
        return "unknown", (f"{obligation.id}:input_outside_alphabet",)
    accepted, reason = _run_input(machine, task_input)
    if accepted == parameters["expected_accept"]:
        return "satisfied", ()
    return "violated", (f"{obligation.id}:{reason or 'unexpected_acceptance'}",)


def check_tasks(snapshot: Snapshot, plan: CheckPlan,
                scope: tuple[str, ...] | None = None) -> ValidationReport:
    """Check legacy finite rules and fixed graph/input goals with explicit scope."""
    snapshot, plan = checked(snapshot, Snapshot), validate_plan(plan)
    scope = select_scope(plan, scope)
    elements = {element.id: element for element in snapshot.elements}
    require(len(elements) == len(snapshot.elements), "duplicate element ID")
    outcomes = []
    for obligation in plan.obligations:
        if obligation.target not in scope:
            continue
        root = elements.get(obligation.target)
        if root is None:
            result = "error", (f"{obligation.target}:missing_target",)
        elif obligation.kind not in _FIELDS:
            result = "unknown", (f"{obligation.target}:unsupported:{obligation.kind}",)
        elif (obligation.field != _FIELDS[obligation.kind]
              or (obligation.kind not in ("graph_reachability", "trace_acceptance") and obligation.parameters)):
            result = "error", (f"{obligation.id}:invalid_rule_configuration",)
        elif obligation.field not in properties(root.properties):
            result = "error", (f"{root.id}:missing_field:{obligation.field}",)
        else:
            parameters = properties(obligation.parameters)
            if obligation.kind == "graph_reachability":
                result = _reachability(snapshot, root, obligation, parameters)
            elif obligation.kind == "trace_acceptance":
                result = _trace_acceptance(snapshot, root, obligation, parameters)
            elif obligation.kind == "directed_acyclic_graph":
                result = _structure(snapshot, root, obligation)
            else:
                result = _automaton(snapshot, root, obligation)
        outcomes.append(Outcome(obligation.id, obligation.version, result[0], result[1]))
    return ValidationReport(
        ReportBinding(digest(snapshot), digest(plan), scope, plan.assumptions, TOOL, VERSION), tuple(outcomes))
