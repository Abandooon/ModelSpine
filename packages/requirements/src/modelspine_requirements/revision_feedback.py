"""Deterministic checker observations, never requirements or repaired candidates."""
from modelspine_protocols import ContractError, decode, require, to_data
from modelspine_protocols import finite_execution as finite
from modelspine_requirements.review import _inspection
from modelspine_requirements.typed_revision import RevisionCandidate
from modelspine_requirements.domain_modeling import _utf8
import json

INSTRUCTIONS = """checker-feedback-revision/0.1
CHECKER_FEEDBACK_JSON is a tool observation about a failed proposed output, not a user
requirement, confirmed answer, source quotation or stored parent. Do not cite it as
SourceEvidence or ActionEvidence. The current stored parent (still unconfirmed), original source and actual user
question/correction/answer remain those in the revision envelope above.
Re-read the entire original requirements, actual user responses and output contract.
Produce a complete new candidate, not a patch or a minimal error-message workaround.
Reconsider the whole model and rules for coverage and fidelity, not only the reported
failure. Keep genuine unresolved and unsupported obligations; never remove requirements
merely to pass checking. The checker diagnoses formal errors, not intended business meaning.
Return original JSON output only. The host will not repair it or automatically adopt it.
"""


def observe(request, raw, context):
    """Recompute the public inspection and optional leaf-most expression failures."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        require(False, "feedback candidate is not strict UTF-8", "unsupported")
    inspection, _ = _inspection(request, raw, context)
    require(inspection["status"] == "rejected" and inspection["diagnostics"] and
            all(d["code"] == "invalid" for d in inspection["diagnostics"]),
            "feedback requires a reproducible invalid candidate, not unsupported/conflict", "unsupported")
    nodes = []
    try:
        candidate = decode(RevisionCandidate, json.loads(_utf8(raw)))
    except (ValueError, RecursionError):
        candidate = None  # Shape errors already have the authoritative diagnostic.
    if candidate is not None:
        entities = {e.id: e for e in candidate.definition.entities}
        relations = {r.id: r for r in candidate.definition.relations}
        def infer(expr, context_id, env):
            try:
                return finite.expression_type(expr, context_id, entities, relations, env), None
            except ContractError as error:
                return None, {"code": error.code, "message": str(error)}
        def visit(expr, path, context_id, env, depth, remaining):
            remaining[0] -= 1
            require(depth <= 24 and remaining[0] >= 0, "feedback expression resource limit", "unsupported")
            child_errors = False
            for index, arg in enumerate(expr.args):
                bindings = env
                if expr.op == "filter" and index == 1:
                    collection, error = infer(expr.args[0], context_id, env)
                    if error or not collection[0].startswith("set:"):
                        continue
                    bindings = {**env, expr.symbol: collection[0].replace("set:", "object:", 1)}
                child_errors |= visit(arg, path + "/args/" + str(index), context_id, bindings, depth + 1, remaining)
            _, error = infer(expr, context_id, env)
            if error and not child_errors:
                nodes.append({"path": path, "operator": expr.op, **error,
                              "operand_types": [infer(arg, context_id, env)[0] for arg in expr.args]})
            return bool(error) or child_errors
        # Invalid declaration identities are covered by the primary inspection.
        if (len(entities) == len(candidate.definition.entities) and len(relations) == len(candidate.definition.relations)
                and all(r.source in entities and r.target in entities for r in relations.values())):
            for index, rule in enumerate(candidate.definition.constraints):
                if rule.context not in entities:
                    continue
                for name in ("applies", "assertion", "unless"):
                    visit(getattr(rule, name), f"/definition/constraints/{index}/{name}", rule.context, {}, 0, [512])
    return {"kind": "local_checker_observation", "inspection": inspection,
            "expression_diagnostics": to_data(tuple(nodes)), "failed_candidate_text": text,
            "semantic_fidelity": "not_checked", "user_requirement": False}
