"""Independent terminal checks for the documented design-field fragment."""
from modelspine_protocols import (
    CheckPlan, Outcome, ReportBinding, Snapshot, ValidationReport,
    checked, digest, properties, require, validate_plan,
)

TOOL = "modelspine-field-checker"
VERSION = "0.1.0"
SUPPORTED = frozenset({"integer_range", "equals"})


def check(snapshot: Snapshot, plan: CheckPlan, scope: tuple[str, ...] | None = None) -> ValidationReport:
    snapshot, plan = checked(snapshot, Snapshot), validate_plan(plan)
    scope = tuple(sorted({o.target for o in plan.obligations})) if scope is None else scope
    require(type(scope) is tuple and bool(scope) and all(type(s) is str for s in scope), "invalid check scope")
    require(len(set(scope)) == len(scope), "duplicate scope")
    scope = tuple(sorted(scope))
    require(set(scope) <= {o.target for o in plan.obligations}, "scope lacks obligations")
    elements = {e.id: e for e in snapshot.elements}
    outcomes = []
    for obligation in plan.obligations:
        if obligation.target not in scope:
            continue
        status, findings = "satisfied", ()
        if obligation.kind not in SUPPORTED:
            status, findings = "unknown", (f"{obligation.target}:unsupported:{obligation.kind}",)
        elif obligation.target not in elements:
            status, findings = "error", (f"{obligation.target}:missing_target",)
        else:
            values = properties(elements[obligation.target].properties)
            parameters = properties(obligation.parameters)
            if obligation.field not in values:
                status, findings = "error", (f"{obligation.target}:missing_field:{obligation.field}",)
            else:
                value = values[obligation.field]
                if obligation.kind == "integer_range":
                    valid_parameters = (set(parameters) == {"min", "max"}
                                        and type(parameters["min"]) is int
                                        and type(parameters["max"]) is int
                                        and parameters["min"] <= parameters["max"])
                    if not valid_parameters:
                        status, findings = "error", (f"{obligation.id}:invalid_range",)
                    elif type(value) is not int or not parameters["min"] <= value <= parameters["max"]:
                        status, findings = "violated", (f"{obligation.target}:{obligation.field}:range",)
                elif set(parameters) != {"value"}:
                    status, findings = "error", (f"{obligation.id}:invalid_equality",)
                elif type(value) is not type(parameters["value"]) or value != parameters["value"]:
                    status, findings = "violated", (f"{obligation.target}:{obligation.field}:equals",)
        outcomes.append(Outcome(obligation.id, obligation.version, status, findings))
    binding = ReportBinding(digest(snapshot), digest(plan), scope, plan.assumptions, TOOL, VERSION)
    return ValidationReport(binding, tuple(outcomes))
