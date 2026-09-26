"""Study-only ordinary program controls; no DAG-controller dependency."""
from modelspine_generation.bounded import ConstructionDecision
from modelspine_protocols import GenerationControl, GenerationPlan, digest, properties, require


def control_plan(check_plan, *, ordinary):
    controls = tuple(GenerationControl(
        obligation.id, obligation.version, obligation.kind,
        "construction" if ordinary and obligation.kind == "directed_acyclic_graph" else "terminal-only",
        "ordinary Kahn topological elimination" if ordinary and obligation.kind == "directed_acyclic_graph"
        else "fixed complete terminal validation",
        "all obligations remain subject to terminal validation")
        for obligation in check_plan.obligations)
    return GenerationPlan(digest(check_plan), controls,
                          tuple(c.obligation_id for c in controls if c.stage == "terminal-only"))


def ordinary_control(snapshot, space, option, *, terminal_only=False):
    """Called after the host validates the base and allowed fixed edit space.

    Independently decide a substituted graph using indegrees, not A's
    target-to-source path algorithm. Parallel edges count separately.
    """
    values = properties(option.values)
    require(option.target in space.edges and set(values) == {"source", "target"},
            "ordinary control option outside edit space")
    require(values["source"] in space.sources and values["target"] in space.destinations,
            "ordinary control endpoints outside edit space")
    edge = next(e for e in snapshot.elements if e.id == option.target)
    if values == properties(edge.properties):
        return ConstructionDecision(digest(option), "no_change", "unchanged endpoints")
    if terminal_only:
        return ConstructionDecision(digest(option), "allow", "all constraints deferred to terminal")
    nodes = {e.id for e in snapshot.elements if e.parent == space.graph and e.kind == "node"}
    adjacency = {node: [] for node in nodes}
    indegrees = {node: 0 for node in nodes}
    for member in snapshot.elements:
        if member.parent == space.graph and member.kind == "edge":
            relation = values if member.id == option.target else properties(member.properties)
            source, target = relation["source"], relation["target"]
            require(source in nodes and target in nodes, "ordinary control invalid endpoint")
            adjacency[source].append(target)
            indegrees[target] += 1
    pending = [node for node in nodes if indegrees[node] == 0]
    removed = 0
    while pending:
        node = pending.pop()
        removed += 1
        for target in adjacency[node]:
            indegrees[target] -= 1
            if indegrees[target] == 0:
                pending.append(target)
    acyclic = removed == len(nodes)
    return ConstructionDecision(digest(option), "allow" if acyclic else "exclude",
                                "topological elimination complete" if acyclic else "directed cycle")
