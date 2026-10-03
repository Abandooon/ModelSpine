"""Prepare then explicitly execute a bounded raw-source/typed-candidate language run."""
import argparse
from contextlib import contextmanager, ExitStack
import base64
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from domain_modeling import load_request
from model_review import create_review, read_review
from modelspine_protocols import ArtifactRef, ContractError, decode, digest, dumps, to_data, require
from modelspine_protocols.review import RevisionProposal
import model_review as review_store
from modelspine_requirements.domain_modeling import ModelingRequest
from modelspine_requirements.revision_request import prepare_execution_revision, verify_execution_revision
from modelspine_requirements.review import review_input, review_ref
from modelspine_requirements.typed_domain import typed_modeling_prompt
from modelspine_requirements.revision_schema import response_format as revision_response_format
from modelspine_requirements.revision_feedback import observe as observe_failure, INSTRUCTIONS as FEEDBACK_INSTRUCTIONS
from modelspine_requirements.review import _inspection
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "adapters"))
from language_response import (VERSION, LanguageError, encoded, extract_response, load_config,
                               post_response, redact, strict_json)

METHOD = "typed-language-run/0.6"
PROMPT_VERSION = "typed-language-assembly/0.1"
OUTPUT_INSTRUCTIONS = """Return one complete compact JSON object, without Markdown or commentary.
Use short unique IDs and no indentation or repeated explanations. Retain every required
JSON key, including null-valued expression fields. Compactness must not remove or weaken
any source condition, exception, uncertainty, question or necessary residual. Do not invent
defaults or replace unsupported semantics with easier rules. Keep concise but faithful
names and issue/residual text; do not abbreviate evidence quotes.
SOURCE_LINES_JSON below is a deterministic presentation of the same INPUT_JSON.text,
not new requirements or instructions. Line numbers use splitlines(), one-based inclusive.
For each evidence span, copy the exact decoded text of the selected complete lines;
join the selected complete lines exactly with LF. Do not add line-number prefixes or
any newline beyond that join result; retain newlines produced by selected empty lines.
Never quote a fragment, paraphrase a quote, or invent a line number. Reuse a source line
where justified, but still provide every required element trace and issue evidence.
Preserve unconfirmed status; matching quotes and valid JSON do not establish fidelity.
"""
REPO = Path(__file__).resolve().parents[1]
METHOD_PATHS = (
    "apps/language_modeling.py", "adapters/language_response.py", "apps/domain_modeling.py",
    "apps/bootstrap.py", "apps/domain_checks.py", "apps/model_review.py",
    "packages/protocols/src/modelspine_protocols/__init__.py",
    "packages/protocols/src/modelspine_protocols/domain_language.py",
    "packages/protocols/src/modelspine_protocols/review.py",
    "packages/requirements/src/modelspine_requirements/__init__.py",
    "packages/requirements/src/modelspine_requirements/domain_modeling.py",
    "packages/requirements/src/modelspine_requirements/typed_domain.py",
    "packages/requirements/src/modelspine_requirements/review.py",
    "packages/protocols/src/modelspine_protocols/finite_execution.py",
    "packages/requirements/src/modelspine_requirements/typed_revision.py",
    "packages/requirements/src/modelspine_requirements/revision_request.py",
    "packages/requirements/src/modelspine_requirements/revision_schema.py",
    "packages/requirements/src/modelspine_requirements/revision_feedback.py",
)

# One audited predecessor, not arbitrary tolerance of historical method drift.
LEGACY_APP_SHA = "493809940e3d7e72a1db672d36fce381ced3b4d576179041340d16db845a1ad7"
FEEDBACK_PATH = "packages/requirements/src/modelspine_requirements/revision_feedback.py"


def now():
    return datetime.now(timezone.utc).isoformat()


def hash_bytes(raw):
    return sha256(raw).hexdigest()


def method_hashes():
    return {p: hash_bytes((REPO / p).read_bytes()) for p in METHOD_PATHS}


def language_prompt(request):
    """Append source presentation and output discipline; the typed contract stays intact."""
    original = typed_modeling_prompt(request)
    lines = request.text.splitlines()
    table = {"line_count": len(lines),
             "lines": [{"line": n, "text": text} for n, text in enumerate(lines, 1)]}
    return (original + "\n\n" + PROMPT_VERSION + "\n" + OUTPUT_INSTRUCTIONS
            + "\nSOURCE_LINES_JSON=" + encoded(table).decode("utf-8"))


def safe_path(path):
    path = Path(path)
    if not path.is_absolute():
        raise LanguageError("absolute_run_path_required")
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise LanguageError("redirected_file_path")
    return path


def save(path, raw):
    safe_path(path)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def load(path, limit=4 * 1024 * 1024):
    safe_path(path)
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise LanguageError("artifact_size_limit")
    return raw


@contextmanager
def locked(root):
    safe_path(root)
    try:
        fd = os.open(root / ".run.lock", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise LanguageError("run_busy") from None
    os.close(fd)
    try:
        yield
    finally:
        (root / ".run.lock").unlink()


def prepare_run(run_dir, request_paths, config, *, task_id):
    return _prepare_run(run_dir, request_paths, config, task_id=task_id)


def prepare_revision_run(run_dir, project_dir, config, *, expected_review_ref, action_refs, task_id):
    """Freeze one answer-bound revision; no parent mutation or network request."""
    root = review_store._directory(project_dir)
    with review_store._locked(root):
        session = review_store._load(root)
        envelope = prepare_execution_revision(session, expected_review_ref=expected_review_ref, action_refs=action_refs)
        return _prepare_run(run_dir, (session.request,), config, task_id=task_id,
                            revision={"project_dir": str(root), "envelope": envelope})


def prepare_feedback_run(run_dir, project_dir, config, *, failed_run_dir, expected_failed_plan_sha256,
                         expected_failed_receipt_sha256, expected_review_ref, action_refs, task_id):
    """One explicitly requested feedback slot; diagnostics cannot be supplied by callers."""
    root = review_store._directory(project_dir)
    require(config.max_requests == 1, "feedback requires one request budget")
    with review_store._locked(root):
        session = review_store._load(root)
        envelope = prepare_execution_revision(session, expected_review_ref=expected_review_ref, action_refs=action_refs)
        feedback = _feedback(failed_run_dir, expected_failed_plan_sha256, expected_failed_receipt_sha256,
                             envelope, str(root))
        return _prepare_run(run_dir, (session.request,), config, task_id=task_id,
                            revision={"project_dir": str(root), "envelope": envelope, "feedback": feedback})


def _revision_prompt(envelope, feedback=None):
    if feedback is None:
        return envelope["prompt"]
    return envelope["prompt"] + "\n" + FEEDBACK_INSTRUCTIONS + "\nCHECKER_FEEDBACK_JSON=" + encoded(feedback).decode("utf-8")


def _feedback(run_dir, plan_sha, receipt_sha, envelope, project_dir, depth=0):
    require(depth < 3, "feedback ancestry exceeds three", "unsupported")
    require(type(receipt_sha) is str and len(receipt_sha) == 64, "explicit failed receipt hash required", "conflict")
    result = _verified_revision_result(run_dir, plan_sha, receipt_sha, legacy=True, depth=depth + 1)
    require(result["receipt"]["stop_reasons"] == ["candidate_rejected"], "feedback source is not an isolated candidate failure")
    require(result["envelope"] == envelope and result["plan"]["parent_project_dir"] == project_dir,
            "feedback source/parent/action scope mismatch", "conflict")
    return {"schema_version": "checker-feedback/0.1", "source_run": str(safe_path(run_dir)),
            "source_plan_sha256": plan_sha, "source_receipt_sha256": receipt_sha,
            "response_sha256": hash_bytes(result["response"]), "candidate_sha256": hash_bytes(result["candidate"]),
            "parent_candidate_ref": envelope["context"]["parent_candidate_ref"],
            "parent_review_ref": envelope["context"]["parent_review_ref"],
            "checker_method_sha256": method_hashes(),
            "observation": observe_failure(result["request"], result["candidate"], envelope["context"])}


def _verified_revision_result(run_dir, plan_sha, receipt_sha, *, legacy=False, depth=0):
    """Verify actual input/transport/inspection bytes. This does not mutate a review."""
    require(depth <= 3, "feedback ancestry exceeds three", "unsupported")
    root = safe_path(run_dir)
    with locked(root):
        plan_raw = load(root / "plan.json")
        require(hash_bytes(plan_raw) == plan_sha, "wrong revision plan", "conflict")
        plan = strict_json(plan_raw)
        current = method_hashes()
        old = {p:h for p,h in current.items() if p != FEEDBACK_PATH}
        old["apps/language_modeling.py"] = LEGACY_APP_SHA
        require((plan["method"] == METHOD and plan["method_sha256"] == current) or
                (legacy and plan["method"] == "typed-language-run/0.5" and plan["method_sha256"] == old),
                "incompatible revision/checker method", "conflict")
        require(plan.get("feedback") in (None, "checker-feedback/0.1") and
                (plan["method"] != "typed-language-run/0.5" or not plan.get("feedback")), "unsupported feedback profile", "unsupported")
        require(plan.get("mode") == "answer_revision/0.1" and plan["executable_slots"] == 1 and
                len(plan["items"]) == 1 and plan["automatic_retries"] == 0, "wrong revision scope", "conflict")
        item = plan["items"][0]
        names = {"request.json", "source.txt", "prompt.txt", "payload.json", "revision.json"}
        if plan.get("feedback"):
            names.add("feedback.json")
        require(set(item["files"]) == names and item["slot"] == 1, "wrong revision inputs", "conflict")
        folder = root / "input-1"
        for name, h in item["files"].items():
            require(hash_bytes(load(folder / name)) == h, "revision input changed", "conflict")
        envelope = verify_execution_revision(strict_json(load(folder / "revision.json")))
        request = load_request(folder / "request.json")
        require(to_data(request) == envelope["review_session"]["request"] and digest(request) == item["request_hash"]
                and request.text.encode("utf-8") == load(folder / "source.txt") and
                item["source_ref"] == to_data(request.source) and plan["parent_review_ref"] == envelope["context"]["parent_review_ref"],
                "revision request/source scope mismatch", "conflict")
        feedback = None
        if plan.get("feedback"):
            feedback = strict_json(load(folder / "feedback.json"))
            require(feedback == _feedback(feedback["source_run"], feedback["source_plan_sha256"],
                    feedback["source_receipt_sha256"], envelope, plan["parent_project_dir"], depth),
                    "feedback observation changed", "conflict")
        prompt = _revision_prompt(envelope, feedback)
        config = plan["config"]
        payload = encoded({"model": config["model"], "input": prompt, "store": False, "stream": False,
                           "max_output_tokens": config["max_output_tokens"], "text": {"format": revision_response_format()}})
        require(load(folder / "prompt.txt") == prompt.encode("utf-8") and load(folder / "payload.json") == payload,
                "revision payload changed", "conflict")
        require(plan["endpoint"] == config["base_url"] + "/responses", "revision endpoint mismatch", "conflict")
        attempt = root / "attempts/001"
        require(sorted(p.name for p in (root / "attempts").iterdir()) == ["001"], "wrong revision attempts", "conflict")
        receipt_raw = load(attempt / "receipt.json")
        require((receipt_sha is None or hash_bytes(receipt_raw) == receipt_sha) and
                hash_bytes(receipt_raw) == load(attempt / "receipt.sha256").decode("ascii"), "receipt changed", "conflict")
        receipt = strict_json(receipt_raw)
        require(receipt["method"] == plan["method"] and receipt["adapter"] == plan["adapter"] and
                receipt.get("adoption") == "not_requested", "receipt method/adoption mismatch", "conflict")
        artifacts = {"reservation.json", "response.body", "candidate.raw", "inspection.json"}
        require(set(receipt["artifact_sha256"]) == artifacts, "incomplete revision artifacts", "conflict")
        for name,h in receipt["artifact_sha256"].items():
            require(hash_bytes(load(attempt / name)) == h, "revision output changed", "conflict")
        require(receipt["plan_sha256"] == plan_sha and receipt["slot"] == 1 and
                receipt["payload_sha256"] == hash_bytes(payload) and receipt["request_hash"] == digest(request),
                "receipt request mismatch", "conflict")
        reservation = strict_json(load(attempt / "reservation.json"))
        require(reservation == {k:receipt[k] for k in ("plan_sha256", "slot", "reserved_utc", "payload_sha256", "request_hash")},
                "reservation mismatch", "conflict")
        require(receipt["http_status"] == 200 and receipt["transport_status"] == "received" and
                receipt["response_bytes"] == "original_http_body" and receipt["stop_reasons"] in ([], ["candidate_rejected"]),
                "incomplete/unsafe response cannot be exported", "unsupported")
        response = load(attempt / "response.body")
        candidate = load(attempt / "candidate.raw")
        extracted, info = extract_response(response, config["model"])
        require(extracted == candidate and not info["stop_reasons"] and info["incomplete_details"] is None and
                info["usage"]["output_tokens"] <= config["max_output_tokens"], "response cannot be exported", "unsupported")
        require(all(receipt[k] == v for k,v in info.items() if k != "stop_reasons") and receipt["requested_model"] == config["model"] and
                receipt["received_sha256"] == receipt["stored_sha256"] == hash_bytes(response), "response receipt mismatch", "conflict")
        context = envelope["context"]
        require(receipt["candidate"] == {"path":"candidate.raw", "sha256":hash_bytes(candidate),
                "origin":"response.output.message.output_text_utf8"} and receipt["revision_ref"] == context["ref"] and
                receipt["parent_candidate_ref"] == context["parent_candidate_ref"] and
                receipt["review_ref"] == context["parent_review_ref"] and receipt["review_project"] == plan["parent_project_dir"],
                "receipt context mismatch", "conflict")
        require(receipt["candidate_ref"] == to_data(ArtifactRef(request.source.project_id,
                envelope["review_session"]["id"] + "/generated-proposal/" + root.name, "1", hash_bytes(candidate))),
                "generated candidate identity mismatch", "conflict")
        inspection, _ = _inspection(request, candidate, context)
        require(strict_json(load(attempt / "inspection.json")) == {"generation_provenance":"not_verified", "inspection":inspection},
                "checker diagnostic changed", "conflict")
        stops = [] if inspection["status"] == "valid" else ["candidate_rejected"]
        require(receipt["stop_reasons"] == stops and receipt["continue_allowed"] is (not stops), "receipt outcome mismatch", "conflict")
        return {"plan":plan, "envelope":envelope, "request":request, "receipt":receipt,
                "receipt_raw":receipt_raw, "response":response, "candidate":candidate}


def _prepare_run(run_dir, request_paths, config, *, task_id, revision=None):
    """No network. The newly created run directory is this task's sole budget authority."""
    config.validate()
    root = safe_path(run_dir)
    count = len(request_paths)
    if not task_id.strip() or count not in (1, 2) or config.max_requests < count:
        raise LanguageError("one_or_two_requests_within_budget_and_task_identity_required")
    items = []
    contents = {}
    for index, path in enumerate(request_paths, 1):
        request = path if isinstance(path, ModelingRequest) else load_request(path)
        prompt = _revision_prompt(revision["envelope"], revision.get("feedback")) if revision else language_prompt(request)
        payload = encoded({"model": config.model, "input": prompt, "store": False, "stream": False,
                           "max_output_tokens": config.max_output_tokens,
                           "text": {"format": revision_response_format() if revision else {"type": "json_object"}}})
        files = {"source.txt": request.text.encode("utf-8"), "request.json": dumps(request).encode("utf-8"),
                 "prompt.txt": prompt.encode("utf-8"), "payload.json": payload}
        if revision:
            files["revision.json"] = encoded(revision["envelope"])
            if revision.get("feedback"):
                files["feedback.json"] = encoded(revision["feedback"])
            if any(len(raw) > 4 * 1024 * 1024 for raw in files.values()):
                raise LanguageError("revision_input_size_limit")
        if any(redact(raw, config.key)[1] for raw in files.values()):
            raise LanguageError("credential_in_input")
        prefix = f"input-{index}"
        contents[prefix] = files
        items.append({"slot": index, "request_hash": digest(request), "source_ref": to_data(request.source),
                      "files": {name: hash_bytes(raw) for name, raw in files.items()}})
    if len({item["request_hash"] for item in items}) != count:
        raise LanguageError("duplicate_planned_request")
    plan = {"method": METHOD, "adapter": VERSION, "prompt_version": PROMPT_VERSION,
            "task_id": task_id, "prepared_utc": now(),
            "config": config.public(), "endpoint": config.base_url + "/responses", "items": items,
            "executable_slots": count, "reserved_revision_slots": max(0, config.max_requests - count),
            "automatic_retries": 0, "method_sha256": method_hashes(),
            "source_origin": "host_supplied_not_independently_verified"}
    if revision:
        plan["mode"] = "answer_revision/0.1"
        plan["parent_project_dir"] = revision["project_dir"]
        plan["parent_review_ref"] = revision["envelope"]["context"]["parent_review_ref"]
        if revision.get("feedback"):
            plan["feedback"] = "checker-feedback/0.1"
    plan_raw = encoded(plan)
    if redact(plan_raw, config.key)[1]:
        raise LanguageError("credential_in_plan")
    root.mkdir()  # Exclusive: a second preparation never resets this task's budget.
    for prefix, files in contents.items():
        folder = root / prefix
        folder.mkdir()
        for name, raw in files.items():
            save(folder / name, raw)
    (root / "attempts").mkdir()
    save(root / "plan.json", plan_raw)
    return {"status": "prepared_not_called", "plan_sha256": hash_bytes(plan_raw), "run_dir": str(root),
            "planned_requests": count, "generation_requests": 0}


def execute_next(run_dir, config, *, expected_plan_sha256):
    """One explicit POST at most. Any unsuccessful predecessor stops the batch."""
    config.validate()
    root = safe_path(run_dir)
    with locked(root), ExitStack() as parent_locks:
        plan_raw = load(root / "plan.json")
        if hash_bytes(plan_raw) != expected_plan_sha256:
            raise LanguageError("plan_hash_conflict")
        plan = strict_json(plan_raw)
        if plan["config"] != config.public() or plan["method_sha256"] != method_hashes():
            raise LanguageError("configuration_or_method_conflict")
        revision_mode = plan.get("mode") == "answer_revision/0.1"
        parent_session = None
        if revision_mode:
            # Cooperative parent lock stays held through response persistence. No
            # stale page can replace the parent while this bounded call is running.
            parent = review_store._directory(plan["parent_project_dir"])
            parent_locks.enter_context(review_store._locked(parent))
            parent_session = review_store._load(parent)
            if to_data(review_ref(parent_session)) != plan["parent_review_ref"]:
                raise LanguageError("revision_parent_conflict")
        inputs = []
        # All frozen inputs are one plan: future and past slots are checked too.
        for input_slot, item in enumerate(plan["items"], 1):
            folder = root / f"input-{input_slot}"
            for name, expected in item["files"].items():
                if Path(name).name != name or hash_bytes(load(folder / name)) != expected:
                    raise LanguageError("input_hash_conflict")
            request = load_request(folder / "request.json")
            if revision_mode:
                revision = verify_execution_revision(strict_json(load(folder / "revision.json", review_store.MAX_STORE_BYTES)))
                if revision["review_session"] != to_data(parent_session) or digest(parent_session.request) != digest(request):
                    raise LanguageError("revision_parent_conflict")
                feedback = None
                if plan.get("feedback"):
                    feedback = strict_json(load(folder / "feedback.json"))
                    require(feedback == _feedback(feedback["source_run"], feedback["source_plan_sha256"],
                            feedback["source_receipt_sha256"], revision, str(parent)), "feedback observation changed", "conflict")
                prompt = _revision_prompt(revision, feedback).encode("utf-8")
            else:
                prompt = language_prompt(request).encode("utf-8")
            payload = load(folder / "payload.json")
            expected_payload = encoded({"model": config.model, "input": prompt.decode("utf-8"), "store": False,
                                        "stream": False, "max_output_tokens": config.max_output_tokens,
                                        "text": {"format": revision_response_format() if revision_mode else {"type": "json_object"}}})
            if (digest(request) != item["request_hash"] or prompt != load(folder / "prompt.txt")
                    or request.text.encode("utf-8") != load(folder / "source.txt") or payload != expected_payload):
                raise LanguageError("request_binding_conflict")
            if any(redact(raw, config.key)[1] for raw in (plan_raw, payload)):
                raise LanguageError("credential_in_input")
            inputs.append((request, payload))
        attempts = root / "attempts"
        safe_path(attempts)
        previous = sorted(attempts.iterdir())
        for index, folder in enumerate(previous, 1):
            if folder.name != f"{index:03}":
                raise LanguageError("budget_history_corrupt")
            try:
                receipt_raw = load(folder / "receipt.json")
                if hash_bytes(receipt_raw) != load(folder / "receipt.sha256").decode("ascii"):
                    raise LanguageError("receipt_hash_conflict")
                receipt = strict_json(receipt_raw)
                if receipt["plan_sha256"] != expected_plan_sha256 or receipt["slot"] != index:
                    raise LanguageError("receipt_binding_conflict")
                for name, expected in receipt["artifact_sha256"].items():
                    if Path(name).name != name or hash_bytes(load(folder / name)) != expected:
                        raise LanguageError("receipt_artifact_conflict")
                if not receipt["continue_allowed"]:
                    raise LanguageError("previous_attempt_stopped")
                if revision_mode:
                    # One executable revision slot. Parent head was already checked;
                    # its candidate intentionally remains the OLD candidate until adoption.
                    continue
                review = folder / "review-project"
                if receipt["review_project"] != str(review):
                    raise LanguageError("review_binding_conflict")
                try:
                    view = read_review(review)
                except (ValueError, OSError, RecursionError):
                    # Public recovery checks pending/busy, saved hashes and replay.
                    # Do not expose stored user text through exception messages.
                    raise LanguageError("review_recovery_failed") from None
                request = inputs[index - 1][0]
                expected_request = to_data(ArtifactRef(request.source.project_id, f"language-{index}/request",
                                                       "1", digest(request)))
                if (view["request_ref"] != expected_request or view["candidate_ref"] != receipt["candidate_ref"]
                        or view["candidate_ref"]["content_hash"] != hash_bytes(load(folder / "candidate.raw"))):
                    raise LanguageError("review_binding_conflict")
                # Legal actions change review_ref; immutable request/candidate must not change.
            except FileNotFoundError:
                raise LanguageError("incomplete_attempt_no_automatic_replay") from None
        if len(previous) >= min(plan["executable_slots"], config.max_requests):
            raise LanguageError("planned_budget_exhausted")
        slot = len(previous) + 1
        request, payload = inputs[slot - 1]
        attempt = attempts / f"{slot:03}"
        attempt.mkdir()  # Persistent reservation is consumed even on crash/timeout/write failure.
        reservation = {"plan_sha256": expected_plan_sha256, "slot": slot, "reserved_utc": now(),
                       "payload_sha256": hash_bytes(payload), "request_hash": digest(request)}
        save(attempt / "reservation.json", encoded(reservation))
        start = time.monotonic()
        exchange = post_response(config, payload)
        raw, was_redacted = redact(exchange.raw, config.key)
        save(attempt / "response.body", raw)
        receipt = {**reservation, "method": METHOD, "adapter": VERSION, "requested_model": config.model,
                   "http_status": exchange.http_status, "transport_status": exchange.transport_status,
                   "response_received_utc": now(), "elapsed_seconds": time.monotonic() - start,
                   "received_sha256": hash_bytes(exchange.raw), "stored_sha256": hash_bytes(raw),
                   "response_bytes": "redacted" if was_redacted else "original_http_body",
                   "usage": None, "usage_status": "unknown", "cost": None, "cost_status": "not_measured",
                   "generation_provenance": "not_verified", "call_receipt": "transport_observed",
                   "candidate": None, "review_project": None, "stop_reasons": []}
        candidate = None
        if was_redacted:
            receipt["stop_reasons"].append("credential_echo_redacted")
        elif exchange.transport_status != "received":
            receipt["stop_reasons"].append(exchange.transport_status)
        elif exchange.http_status != 200:
            receipt["stop_reasons"].append("http_failure")
        else:
            try:
                candidate, info = extract_response(raw, config.model)
                receipt.update(info)
                if info["usage"] is not None and info["usage"]["output_tokens"] > config.max_output_tokens:
                    receipt["stop_reasons"].append("reported_output_budget_exceeded")
            except LanguageError as exc:
                receipt["stop_reasons"].append(str(exc))
        if candidate is not None:
            # Exact decoded output_text bytes; no stripping, JSON repair or default candidate.
            if redact(candidate, config.key)[1]:
                receipt["stop_reasons"].append("credential_echo_redacted")
                candidate = None
            else:
                save(attempt / "candidate.raw", candidate)
                receipt["candidate"] = {"path": "candidate.raw", "sha256": hash_bytes(candidate),
                                        "origin": "response.output.message.output_text_utf8"}
                try:
                    if revision_mode:
                        # Pure inspection uses only the previously replayed context;
                        # execution does not append a proposal or adopt it.
                        from modelspine_requirements.review import _inspection
                        inspection, _ = _inspection(request, candidate, revision["context"])
                        receipt["review_project"] = str(parent)
                        receipt["parent_candidate_ref"] = revision["context"]["parent_candidate_ref"]
                        receipt["review_ref"] = revision["context"]["parent_review_ref"]
                        receipt["revision_ref"] = revision["context"]["ref"]
                        receipt["candidate_ref"] = to_data(ArtifactRef(request.source.project_id,
                            parent_session.id + "/generated-proposal/" + root.name, "1", hash_bytes(candidate)))
                        receipt["adoption"] = "not_requested"
                    else:
                        review = attempt / "review-project"
                        review.mkdir()
                        view = create_review(review, request, candidate, session_id=f"language-{slot}")
                        reopened = read_review(review)
                        if view != reopened or view["candidate_ref"]["content_hash"] != hash_bytes(candidate):
                            raise LanguageError("review_identity_conflict")
                        inspection = view["inspection"]
                        receipt["review_project"] = str(review)
                        receipt["candidate_ref"] = view["candidate_ref"]
                        receipt["review_ref"] = view["review_ref"]
                    save(attempt / "inspection.json", encoded({"generation_provenance": "not_verified", "inspection": inspection}))
                    if inspection["status"] != "valid":
                        receipt["stop_reasons"].append("candidate_rejected")
                except (ValueError, OSError, RecursionError):
                    receipt["stop_reasons"].append("review_creation_failed")
        receipt["continue_allowed"] = not receipt["stop_reasons"]
        receipt["completed_utc"] = now()
        receipt["artifact_sha256"] = {p.name: hash_bytes(load(p)) for p in attempt.iterdir() if p.is_file()}
        receipt_raw, sanitized = redact(encoded(receipt), config.key)
        if sanitized:
            raise LanguageError("receipt_requires_redaction_incomplete_attempt")
        save(attempt / "receipt.json", receipt_raw)
        save(attempt / "receipt.sha256", hash_bytes(receipt_raw).encode("ascii"))
        return receipt


def revision_proposal_from_run(run_dir, *, expected_plan_sha256, action_id, actor):
    """Existing valid-only export. A proposal is never an adoption."""
    result = _verified_revision_result(run_dir, expected_plan_sha256, None)
    require(result["receipt"]["continue_allowed"], "stopped revision receipt", "conflict")
    return _result_proposal(run_dir, result, action_id, actor)


def review_proposal_from_run(run_dir, *, expected_plan_sha256, expected_receipt_sha256, action_id, actor):
    """Current-method complete valid/rejected output for explicit unconfirmed review."""
    require(type(expected_receipt_sha256) is str and len(expected_receipt_sha256) == 64,
            "explicit review receipt hash required", "conflict")
    result = _verified_revision_result(run_dir, expected_plan_sha256, expected_receipt_sha256)
    return _result_proposal(run_dir, result, action_id, actor)


def _result_proposal(run_dir, result, action_id, actor):
    envelope = result["envelope"]
    context = envelope["context"]
    # Preserve the original expected head in the DTO. Registration checks current
    # head (or the existing same-ID operation); export itself never changes state.
    response_ref = ArtifactRef(context["parent_request_ref"]["project_id"], "language-receipt/" + Path(run_dir).name,
                               "1", hash_bytes(result["receipt_raw"]))
    from modelspine_requirements.typed_revision import INSTRUCTIONS
    require(hash_bytes(INSTRUCTIONS.encode("utf-8")) == context["method_instructions_sha256"],
            "revision method instructions changed", "conflict")
    return RevisionProposal("model-review-revision-proposal/0.1", action_id, response_ref.project_id,
        decode(ArtifactRef, context["parent_request_ref"]), decode(ArtifactRef, context["parent_candidate_ref"]),
        decode(ArtifactRef, context["parent_review_ref"]), actor,
        tuple(decode(ArtifactRef, r) for r in envelope["action_refs"]), decode(ArtifactRef, context["ref"]),
        response_ref, base64.b64encode(result["candidate"]).decode("ascii"), INSTRUCTIONS)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--request", action="append", required=True, type=Path)
    prepare.add_argument("--task-id", required=True)
    revision_prepare = sub.add_parser("prepare-revision")
    revision_prepare.add_argument("--project-dir", required=True, type=Path)
    revision_prepare.add_argument("--bindings", required=True, type=Path)
    revision_prepare.add_argument("--task-id", required=True)
    execute = sub.add_parser("execute-next")
    execute.add_argument("--expected-plan-sha256", required=True)
    for command in (prepare, revision_prepare, execute):
        command.add_argument("--run-dir", type=Path, required=True)
        command.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        config = load_config(args.env_file)
        if args.command == "prepare":
            result = prepare_run(args.run_dir, args.request, config, task_id=args.task_id)
        elif args.command == "prepare-revision":
            bindings = strict_json(load(args.bindings))
            require(set(bindings) == {"expected_review_ref", "action_refs"}, "invalid revision bindings")
            result = prepare_revision_run(args.run_dir, args.project_dir, config, task_id=args.task_id,
                expected_review_ref=decode(ArtifactRef, bindings["expected_review_ref"]),
                action_refs=tuple(decode(ArtifactRef, r) for r in bindings["action_refs"]))
        else:
            receipt = execute_next(args.run_dir, config, expected_plan_sha256=args.expected_plan_sha256)
            result = {"status": "completed" if receipt["continue_allowed"] else "stopped",
                      "slot": receipt["slot"], "receipt": str(args.run_dir / "attempts" / f"{receipt['slot']:03}" / "receipt.json")}
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["status"] != "stopped" else 1
    except Exception as exc:
        # Never interpolate remote errors, candidate text or credential-bearing arguments.
        code = str(exc) if isinstance(exc, LanguageError) else "local_input_or_io_failure"
        print(json.dumps({"status": "error", "code": code}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
