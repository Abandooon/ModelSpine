"""Finite field constructor and domain-independent report regression gate."""
from dataclasses import replace

from modelspine_protocols import (
    ChangeProposal, CheckPlan, GenerationControl, GenerationPlan,
    RepairComparison, SetProperty, Snapshot, ValidationReport, checked, digest,
    properties, ref, require, validate_plan,
)


def _control_parameters(obligation):
    params = properties(obligation.parameters)
    if obligation.kind == "integer_range":
        require(set(params) == {"min", "max"} and type(params["min"]) is int
                and type(params["max"]) is int and params["min"] <= params["max"], "malformed range control")
    elif obligation.kind == "equals":
        require(set(params) == {"value"}, "malformed equality control")
    return params


def plan(check_plan: CheckPlan, *, target: str, field: str) -> GenerationPlan:
    check_plan = validate_plan(check_plan)
    require(type(target) is str and bool(target) and type(field) is str and bool(field),
            "invalid construction target/field")
    supported = {"integer_range", "equals"}
    controls, residual = [], []
    for obligation in check_plan.obligations:
        matches = (obligation.target, obligation.field) == (target, field)
        controlled = matches and obligation.kind in supported
        if controlled:
            _control_parameters(obligation)
        else:
            residual.append(obligation.id)
        mechanism = ("finite-field-filter on edited field only" if controlled else
                     "outside edited field" if not matches else "unsupported")
        controls.append(GenerationControl(
            obligation.id, obligation.version, obligation.kind,
            "construction" if controlled else "terminal-only", mechanism,
            "independent terminal check required"))
    return GenerationPlan(digest(check_plan), tuple(controls), tuple(residual))


def construct(snapshot: Snapshot, check_plan: CheckPlan, proposal_id: str,
              target: str, field: str, value: str | int | bool) -> ChangeProposal:
    snapshot, check_plan = checked(snapshot, Snapshot), validate_plan(check_plan)
    require(type(value) in (str, int, bool), "unsupported candidate value")
    element = next((e for e in snapshot.elements if e.id == target), None)
    require(element is not None, "missing construction target", "not_found")
    values = properties(element.properties)
    require(field in values and type(value) is type(values[field]), "field/type outside constructor support")
    if type(value) is int:
        require(-(2**63) <= value < 2**63, "integer outside supported range")
    # Deliberately separate from assurance.check: terminal validation must catch bypassed construction.
    for obligation in check_plan.obligations:
        if (obligation.target, obligation.field) != (target, field):
            continue
        params = _control_parameters(obligation)
        if obligation.kind == "integer_range":
            require(type(value) is int and params["min"] <= value <= params["max"], "candidate excluded by range")
        elif obligation.kind == "equals":
            require(type(value) is type(params["value"]) and value == params["value"], "candidate excluded by equality")
    require(type(proposal_id) is str and bool(proposal_id), "invalid proposal ID")
    return ChangeProposal("0.1", proposal_id, ref(snapshot),
                          (SetProperty("set_property", target, field, value),), element.sources)


def compare_reports(before: ValidationReport, after: ValidationReport) -> RepairComparison:
    before, after = checked(before, ValidationReport), checked(after, ValidationReport)

    def reject(reason):
        return RepairComparison("rejected", reason, after.residual)

    if replace(before.binding, candidate_hash=after.binding.candidate_hash) != after.binding:
        return reject("incomparable checking context")
    old, new = ({o.obligation_id: o for o in r.outcomes} for r in (before, after))
    if not old or len(old) != len(before.outcomes) or len(new) != len(after.outcomes):
        return reject("empty/duplicate obligation coverage")
    if set(old) != set(new) or any(old[k].obligation_version != new[k].obligation_version for k in old):
        return reject("obligation coverage/version changed")
    evaluated = {"satisfied", "violated"}
    if any(old[k].status in evaluated and new[k].status not in evaluated for k in old):
        return reject("lost evaluated coverage")
    if any(new[k].status not in evaluated and new[k].status != old[k].status for k in old):
        return reject("changed unevaluated state is not repair progress")
    # Include obligation identity: resolving one finding cannot hide the same text on another rule.
    def errors(report):
        return {(o.obligation_id, finding) for o in report.outcomes if o.status in ("violated", "error")
                for finding in (o.findings or (o.status,))}
    if errors(after) - errors(before):
        return reject("new diagnostic")
    if any(old[k].status == "satisfied" and new[k].status != "satisfied" for k in old):
        return reject("satisfied obligation regressed")
    if any(old[k].status != "satisfied" and new[k].status == "satisfied" for k in old) or errors(after) < errors(before):
        return RepairComparison("repair_progress", "strict improvement; no delivery authorization", after.residual)
    return reject("no strict improvement")
