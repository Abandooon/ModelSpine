"""Replay caller-supplied bytes; no transport, provider receipt, or generation claim."""
from base64 import b64encode
from hashlib import sha256

from studies.construction import run as single
import candidate_batch
from modelspine_protocols import digest, loads, require, to_data
from support.task_oracle import EvaluationSpec


def replay_candidates(inputs, request, payload_bytes, expected_request_hash, *, checkpoint=None):
    """One fixed payload, three independent conditions, with separate reference facts.

    expected_request_hash comes from the caller's prior request evidence, never
    from rebuilding a request after seeing this payload. A supplied checkpoint
    must persist the record atomically or raise; recording failures propagate.
    """
    require(type(payload_bytes) is bytes, "replay requires original payload bytes")
    record = {
        "schema": "candidate-replay/0.1", "payload_origin": "caller_supplied",
        "request": to_data(request), "request_hash": digest(request),
        "expected_request_hash": expected_request_hash,
        "raw_payload": {"encoding": "base64", "content": b64encode(payload_bytes).decode("ascii"),
                        "sha256": sha256(payload_bytes).hexdigest(), "byte_length": len(payload_bytes)},
        "planned_batches": 1, "planned_trials": list(single.CONDITIONS), "planned": len(single.CONDITIONS),
        "api_calls_during_replay": 0, "api_cost_during_replay": 0,
        "source_generation_usage": None, "source_generation_cost": None,
        "source_generation_reason": "not established by a caller-supplied payload",
        "provider": None, "model": None, "backend_receipt": None,
        "selection_status": "not_run", "selection": None, "valid_batches": 0,
        "catalog_size": len(request.options), "returned_options": None,
        "max_considered_options": request.space.max_options, "exhaustion_scope": "backend_batch",
        "trials": [], "active_trial": None, "run_status": "in_progress", "error": None,
    }

    def persist():
        observed = record["trials"] + ([record["active_trial"]] if record["active_trial"] else [])
        record.update(started=sum(t.get("started") is True for t in observed),
                      terminal=sum(t.get("started") is True for t in record["trials"]),
                      not_started=sum(t.get("status") == "not_started" for t in record["trials"]),
                      app_returned=sum(t.get("returned") is True for t in observed),
                      saved=sum(t.get("saved") is True for t in observed),
                      reference_error_trials=sum(t.get("reference_status") == "error" for t in observed))
        if checkpoint is not None:
            checkpoint(record)

    # This preserves even non-UTF8 or malformed payloads before the parser runs.
    persist()
    phase = "request_binding"
    try:
        require(expected_request_hash == record["request_hash"], "original request hash mismatch", "conflict")
        phase = "reference_binding"
        pinned = single.reference_spec()
        require(loads(EvaluationSpec, pinned.content.decode("utf-8")).task_ref == inputs[0].task_ref == request.task_ref,
                "reference task does not match replay task", "conflict")
        record["reference_ref"] = to_data(pinned.spec_ref)
        phase = "selection"
        selection = candidate_batch.parse_candidate_selection(request, payload_bytes)
    except Exception as exc:
        record.update(run_status="error", error={"phase": phase, "exception_type": type(exc).__name__,
                                                "code": getattr(exc, "code", None), "reason": str(exc)})
        if phase == "selection":
            record["selection_status"] = "response_invalid"
        record["trials"] = [{"id": condition, "condition": condition, "planned": True, "started": False,
                             "app_started": False, "returned": False, "saved": None, "counts": None,
                             "status": "not_started", "reason": f"{phase}: {exc}", "reference_status": "not_run",
                             "api_calls_during_replay": 0}
                            for condition in single.CONDITIONS]
        persist()
        return record
    record.update(selection_status="valid", selection=to_data(selection), valid_batches=1,
                  returned_options=len(selection.option_ids))
    persist()
    for condition in single.CONDITIONS:
        batch_result = None

        def execute_app(actual_condition, actual_inputs, fault=None):
            nonlocal batch_result
            require(fault is None, "replay does not inject controller fault profiles")
            overrides = {}
            if actual_condition != "dag-construction":
                overrides = {
                    "controller": lambda option: single.ordinary_control(
                        actual_inputs[2], request.space, option, terminal_only=actual_condition == "terminal-only"),
                    "construction_plan": single.control_plan(actual_inputs[0].contract.plan,
                                                             ordinary=actual_condition == "ordinary-rule"),
                }
            batch_result = candidate_batch.run_candidate_selection(actual_inputs, request, selection, **overrides)
            return batch_result.app_result

        def trial_record(trial):
            # The inherited zeroes describe only the no-network replay, never
            # the unknown original generation cost of this supplied payload.
            value = {key: item for key, item in trial.items() if key not in ("llm_calls", "paid_api_cost")}
            value.update(api_calls_during_replay=0, api_cost_during_replay=0, app_started=True,
                         batch_request_hash=selection.request_hash, batch_response_hash=selection.response_hash,
                         exhaustion_scope="backend_batch")
            if batch_result is not None:
                value["batch"] = {"request_hash": batch_result.request_hash, "response_hash": batch_result.response_hash,
                                  "catalog_size": batch_result.catalog_size, "returned_options": batch_result.returned_options,
                                  "max_considered_options": batch_result.max_considered_options,
                                  "exhaustion_scope": batch_result.exhaustion_scope}
            return value

        def app_checkpoint(trial):
            record["active_trial"] = trial_record(trial)
            persist()

        record["active_trial"] = {"id": condition, "condition": condition, "planned": True, "started": True,
                                  "app_started": None, "reference_status": "not_run", "api_calls_during_replay": 0}
        persist()
        trial = single.observe_trial(condition, condition, inputs, pinned,
                                     checkpoint=app_checkpoint, execute_app=execute_app)
        record["trials"].append(trial_record(trial))
        record["active_trial"] = None
        persist()
    record["run_status"] = ("error" if any(t["status"] == "error" for t in record["trials"]) else
                            "reference_error" if record["reference_error_trials"] else "complete")
    persist()
    return record
