"""Run: python platform/apps/offline.py [--threshold 250000]."""
import argparse
import json
import sys
from dataclasses import replace
from time import perf_counter

import bootstrap
from modelspine_protocols import (
    CheckPlan, ContractError, Metamodel, Obligation, RunReceipt, SetProperty,
    Snapshot, digest, loads, to_data,
)
from modelspine_assurance import check
from modelspine_generation import compare_reports, construct, plan
from modelspine_kernel import ModelKernel


def load_fixture():
    folder = bootstrap.PLATFORM / "domain-packs" / "order-approval"
    def read(cls, name):
        return loads(cls, (folder / name).read_text(encoding="utf-8"))
    return read(Metamodel, "metamodel.json"), read(Snapshot, "model.json"), read(CheckPlan, "obligations.json")


def demo(threshold: int = 250000):
    started = perf_counter()
    metamodel, snapshot, checks = load_fixture()
    kernel = ModelKernel(snapshot, metamodel, checks, check, frozenset({"local-editor"}))
    evidence = {target: kernel.record_evidence(check(snapshot, checks, (target,)))
                for target in ("approval-policy", "weather", "external-signal")}
    proposal = construct(snapshot, checks, "change-threshold", "approval-policy", "threshold_minor", threshold)
    preview = kernel.preview(proposal)
    report = check(preview.candidate, checks)
    decision = kernel.decide(proposal, report, "local-editor")
    before_commit = kernel.snapshot().revision
    commit = kernel.apply(proposal, decision, "local-editor")
    # A direct illegal product bypasses construction and is still rejected by the independent checker.
    illegal = replace(proposal, proposal_id="illegal-terminal-example",
                      operations=(SetProperty("set_property", "approval-policy", "threshold_minor", -1),))
    fresh_kernel = ModelKernel(snapshot, metamodel, checks, check, frozenset({"local-editor"}))
    illegal_report = check(fresh_kernel.preview(illegal).candidate, checks)
    try:
        construct(snapshot, checks, "excluded", "approval-policy", "threshold_minor", -1)
    except ContractError as exc:
        exclusion = {"code": exc.code, "reason": str(exc)}
    else:
        raise AssertionError("illegal candidate unexpectedly constructed")
    extended = replace(checks, obligations=checks.obligations + (
        Obligation("runtime-approval", "1", "runtime_trace", "approval-policy", "role", ()),))
    unsupported = check(preview.candidate, extended)
    comparison = compare_reports(illegal_report, check(fresh_kernel.preview(proposal).candidate, checks))
    statuses = {item.evidence_id: item for item in commit.evidence_status}
    output = {
        "scenario": "design-model change; no business approval or application delivery",
        "generation_plan": to_data(plan(extended)),
        "preview_revision": preview.candidate.revision,
        "stored_revision_before_commit": before_commit,
        "commit": to_data(commit),
        "evidence_applicability": {target: to_data(statuses[item.id]) for target, item in evidence.items()},
        "construction_exclusion": exclusion,
        "independent_illegal_terminal_report": to_data(illegal_report),
        "unsupported_report": to_data(unsupported),
        "unsupported_residual": unsupported.residual,
        "repair_comparison": to_data(comparison),
    }
    output["receipt"] = to_data(RunReceipt(
        "offline-order-approval", (digest(snapshot), digest(checks), digest(proposal)), (digest(commit),),
        ("Python standard library", "modelspine-field-checker/0.1.0", "finite-field-constructor/0.1.0"),
        int((perf_counter() - started) * 1000), "completed"))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=int, default=250000, help="design threshold in CNY minor units")
    args = parser.parse_args()
    try:
        result = demo(args.threshold)
    except ContractError as exc:
        print(json.dumps({"status": "error", "code": exc.code, "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
