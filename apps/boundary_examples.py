"""Exercise two explicit finite configurations without an application pilot."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap
bootstrap.activate(("protocols", "model-kernel"))
sys.path.insert(0, str(bootstrap.PLATFORM / "adapters"))

from finite_models import check_automaton, check_structure
from fixtures import load_case
from modelspine_kernel import ModelKernel
from modelspine_protocols import (
    ChangeProposal, ContractError, SetDependencies, SetProperty, ref, require, to_data,
)


def run_profile(profile):
    require(profile in ("structural-graph", "finite-automaton"), "unsupported profile", "unsupported")
    metamodel, snapshot, checks = load_case(bootstrap.PLATFORM / "domain-packs" / profile)
    checker = check_structure if profile == "structural-graph" else check_automaton
    kernel = ModelKernel(snapshot, metamodel, checks, checker, frozenset({"local-editor"}))
    initial_report = checker(snapshot, checks)
    kernel.record_evidence(initial_report)
    initial_applicability = kernel.evidence_status()
    if profile == "structural-graph":
        operations = (SetProperty("set_property", "edge-bc", "source", "node-a"),
                      SetDependencies("set_dependencies", "edge-bc", ("node-a", "node-c"), True))
    else:
        operations = (SetProperty("set_property", "step-b", "symbol", "a"),
                      SetProperty("set_property", "machine", "trace", "aa"))
    proposal = ChangeProposal("0.1", "finite-configuration-change", ref(snapshot), operations, ())
    preview = kernel.preview(proposal)
    report = checker(preview.candidate, checks)
    decision = kernel.decide(proposal, report, "local-editor")
    commit = kernel.apply(proposal, decision, "local-editor")
    return {
        "profile": profile,
        "scope": "finite configuration engineering check; no application runtime or research result",
        "initial_report": to_data(initial_report),
        "initial_evidence_applicability": to_data(initial_applicability),
        "proposal": to_data(proposal),
        "preview": to_data(preview),
        "commit": to_data(commit),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=("structural-graph", "finite-automaton"))
    args = parser.parse_args()
    try:
        output = run_profile(args.profile)
    except ContractError as exc:
        print(json.dumps({"status": "error", "code": exc.code, "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
