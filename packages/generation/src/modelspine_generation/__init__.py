"""Finite field constructor and domain-independent report regression gate."""
from dataclasses import replace

from modelspine_protocols import (
    ChangeProposal, CheckPlan, GenerationControl, GenerationPlan,
    RepairComparison, SetProperty, Snapshot, ValidationReport, checked, digest,
    properties, ref, require, validate_plan,
)


def plan(check_plan: CheckPlan) -> GenerationPlan:
    check_plan = validate_plan(check_plan)
    supported = {"integer_range", "equals"}
    controls = tuple(GenerationControl(
        o.id, o.version, o.kind, "construction" if o.kind in supported else "terminal-only",
        "finite-field-filter on edited field only" if o.kind in supported else "unsupported",
        "independent terminal check required") for o in check_plan.obligations)
    return GenerationPlan(digest(check_plan), controls,
                          tuple(o.id for o in check_plan.obligations if o.kind not in supported))


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
        params = properties(obligation.parameters)
        if obligation.kind == "integer_range":
            require(set(params) == {"min", "max"} and type(params["min"]) is int
                    and type(params["max"]) is int and params["min"] <= params["max"], "malformed range control")
            require(type(value) is int and params["min"] <= value <= params["max"], "candidate excluded by range")
        elif obligation.kind == "equals":
            require(set(params) == {"value"}, "malformed equality control")
            require(type(value) is type(params["value"]) and value == params["value"], "candidate excluded by equality")
    require(bool(proposal_id), "empty proposal ID")
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
