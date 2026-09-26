"""Finite observations and answer goals from caller-fixed, positive probes."""
from dataclasses import replace

from modelspine_protocols import (
    ContractError, Obligation, Property, Snapshot, checked, digest, properties,
    ref, require, validate_evidence_refs,
)
from modelspine_requirements import Observation, Probe

from finite_models import _graph, _machine, _run_input


_FIELDS = {"graph_reachability": "root", "trace_acceptance": "initial"}


def _probe(probe):
    probe = checked(probe, Probe)
    require(bool(probe.id and probe.text and probe.source_refs), "incomplete probe")
    validate_evidence_refs(probe.source_refs)
    return probe


def _parameters(probe):
    obligation = probe.obligation
    require(obligation.kind in _FIELDS, "unsupported probe rule", "unsupported")
    require(bool(obligation.id and obligation.version and obligation.target), "incomplete probe obligation")
    require(obligation.field == _FIELDS[obligation.kind], "invalid probe field")
    parameters = properties(obligation.parameters)
    if obligation.kind == "graph_reachability":
        expected = "expected_reachable"
        require(set(parameters) == {"source", "destination", expected}
                and type(parameters["source"]) is str and bool(parameters["source"])
                and type(parameters["destination"]) is str and bool(parameters["destination"]),
                "invalid reachability probe parameters")
    else:
        expected = "expected_accept"
        require(set(parameters) == {"input", expected} and type(parameters["input"]) is str,
                "invalid trace probe parameters")
    require(parameters[expected] is True, "probe must use a positive boolean template")
    return parameters, expected


def observe(snapshot: Snapshot, probe: Probe) -> Observation:
    """Observe supported finite behavior; malformed models never mean False.

    Shape/source errors raise ContractError at the input boundary. Finite-rule
    configuration or model errors remain explicit, bound observation results.
    """
    snapshot, probe = checked(snapshot, Snapshot), _probe(probe)

    def result(status, value, reason):
        return Observation(ref(snapshot), digest(probe), status, value, reason)

    elements = {element.id: element for element in snapshot.elements}
    if len(elements) != len(snapshot.elements):
        return result("error", None, "duplicate_element_id")
    root = elements.get(probe.obligation.target)
    if root is None:
        return result("error", None, "missing_target")
    if probe.obligation.kind not in _FIELDS:
        return result("unknown", None, "unsupported_probe_rule")
    try:
        parameters, _ = _parameters(probe)
        if probe.obligation.field not in properties(root.properties):
            return result("error", None, "missing_probe_field")
        if probe.obligation.kind == "graph_reachability":
            adjacency, failure = _graph(snapshot, root)
            if failure:
                return result("error", None, ";".join(failure[1]))
            source, destination = parameters["source"], parameters["destination"]
            if source not in adjacency or destination not in adjacency:
                return result("error", None, "probe_endpoint_not_in_graph")
            seen, todo = {source}, [source]
            while todo:
                for target in adjacency[todo.pop()]:
                    if target not in seen:
                        seen.add(target)
                        todo.append(target)
            return result("observed", destination in seen, "finite_graph_reachability")
        machine, failure = _machine(snapshot, root)
        if failure:
            return result("error", None, ";".join(failure[1]))
        if any(symbol not in machine[1] for symbol in parameters["input"]):
            return result("unknown", None, "input_outside_alphabet")
        accepted, reason = _run_input(machine, parameters["input"])
        return result("observed", accepted, reason or "trace_accepted")
    except ContractError as exc:
        return result("error", None, str(exc))


def goal(probe: Probe, value: bool) -> Obligation:
    """Bind an answer to the original probe without consulting a candidate."""
    probe = _probe(probe)
    require(type(value) is bool, "probe answer must be a boolean")
    _, expected = _parameters(probe)
    return replace(probe.obligation, parameters=tuple(
        Property(item.name, value) if item.name == expected else item
        for item in probe.obligation.parameters))
