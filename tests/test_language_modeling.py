"""Synthetic transport engineering only. No live API and no independent semantic answers."""
from dataclasses import replace
import http.client
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))
import language_modeling as app
import language_response as wire
from modelspine_protocols import ArtifactRef, ContractError, decode, dumps, digest
from modelspine_protocols.review import ReviewAction
import model_review
from modelspine_requirements.domain_modeling import prepare_request

KEY = "offline-engineering-secret-NOT-A-REAL-KEY"


def candidate(request):
    return wire.encoded({"schema_version": "typed-domain-candidate/0.1", "request_hash": digest(request),
                         "status": "unconfirmed", "definition": {"schema_version": "finite-domain/0.1",
                         "id": "engineering", "version": "1", "entities": [{"id": "item", "name": "物件", "fields": []}],
                         "relations": [], "constraints": [], "residuals": []},
                         "traces": [{"element": "item", "evidence": [{"start_line": 1, "end_line": 1,
                                                                 "quote": request.text.strip()}]}], "issues": []})


def envelope(raw, **changes):
    data = {"id": "offline-response", "object": "response", "model": "gpt-6-luna", "status": "completed",
            "error": None, "incomplete_details": None,
            "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
            "output": [{"type": "message", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "text": raw.decode("utf-8")}]}]}
    data.update(changes)
    return wire.encoded(data)


def http_response(body, framing):
    """Actual stdlib parsing/reads, backed by a finite byte stream (no network)."""
    class MemorySocket:
        def makefile(self, mode):
            return io.BytesIO(b"HTTP/1.1 200 OK\r\n" + framing + b"\r\n" + body)
    response = http.client.HTTPResponse(MemorySocket())
    response.begin()
    return response


class LanguageRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = wire.Config("https://api.openai-proxy.org", "https://api.openai-proxy.org/v1", KEY, "gpt-6-luna", 3, 4096)
        self.requests = []
        self.paths = []
        for n in (1, 2):
            raw = f"工程原文物件{n}\n".encode()
            request = prepare_request(raw, ArtifactRef("engineering", f"source-{n}", "1", app.hash_bytes(raw)),
                                      request_id=f"req-{n}", scope="engineering transport only")
            path = self.root / f"request-{n}.json"
            path.write_text(dumps(request), encoding="utf-8")
            self.requests.append(request)
            self.paths.append(path)
        self.run = self.root / "run"
        self.prepared = app.prepare_run(self.run, self.paths, self.config, task_id="offline-test")
        self.expected = self.prepared["plan_sha256"]

    def execute(self, raw=None, status=200, transport="received"):
        if raw is None:
            raw = envelope(candidate(self.requests[0]))
        with patch.object(app, "post_response", return_value=wire.Exchange(status, raw, transport)) as post:
            receipt = app.execute_next(self.run, self.config, expected_plan_sha256=self.expected)
            self.assertEqual(post.call_count, 1)
            self.assertEqual(post.call_args.args[1], (self.run / "input-1/payload.json").read_bytes())
            self.assertEqual(json.loads(post.call_args.args[1])["text"], {"format": {"type": "json_object"}})
        return receipt

    def test_prepare_is_network_free_and_exact_prompt_payload(self):
        payload = wire.strict_json((self.run / "input-1/payload.json").read_bytes())
        self.assertEqual(payload["input"], app.language_prompt(self.requests[0]))
        self.assertTrue(payload["input"].startswith(app.typed_modeling_prompt(self.requests[0]) + "\n\n"))
        self.assertEqual(set(payload), {"model", "input", "store", "stream", "max_output_tokens", "text"})
        self.assertEqual(payload["text"], {"format": {"type": "json_object"}})
        self.assertEqual((self.run / "input-1/source.txt").read_bytes(), self.requests[0].text.encode())
        self.assertFalse(payload["store"])
        self.assertNotIn(self.requests[1].text, payload["input"])
        self.assertEqual(list((self.run / "attempts").iterdir()), [])

    def test_single_input_budget_one_is_persistent_and_cannot_send_second(self):
        config = replace(self.config, max_requests=1)
        run = self.root / "single-run"
        with patch.object(app, "post_response") as post:
            prepared = app.prepare_run(run, self.paths[:1], config, task_id="engineering-only-remaining-one")
            post.assert_not_called()
        plan = json.loads((run / "plan.json").read_bytes())
        self.assertEqual(prepared["planned_requests"], 1)
        self.assertEqual((len(plan["items"]), plan["executable_slots"], plan["reserved_revision_slots"]), (1, 1, 0))
        with patch.object(app, "post_response", return_value=wire.Exchange(200, envelope(candidate(self.requests[0])), "received")) as post:
            receipt = app.execute_next(run, config, expected_plan_sha256=prepared["plan_sha256"])
            self.assertTrue(receipt["continue_allowed"])
            with self.assertRaisesRegex(wire.LanguageError, "planned_budget_exhausted"):
                app.execute_next(run, config, expected_plan_sha256=prepared["plan_sha256"])
            self.assertEqual(post.call_count, 1)
        code = ("import sys;sys.path.insert(0," + repr(str(app.REPO / 'apps')) + ");import language_modeling as a;"
                "from language_response import Config;"
                "c=Config('https://api.openai-proxy.org','https://api.openai-proxy.org/v1','offline-unused','gpt-6-luna',1,4096);"
                "a.execute_next(" + repr(str(run)) + ",c,expected_plan_sha256=" + repr(prepared["plan_sha256"]) + ")")
        result = subprocess.run([sys.executable, "-B", "-I", "-c", code], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"planned_budget_exhausted", result.stderr)
        self.assertEqual([p.name for p in (run / "attempts").iterdir()], ["001"])

    def test_prepare_rejects_empty_excess_and_over_budget_inputs_before_writing(self):
        for number, (paths, budget, task) in enumerate((([], 1, "task"), (self.paths * 2, 3, "task"),
                                                       (self.paths, 1, "task"), (self.paths[:1], 1, " "))):
            run = self.root / f"invalid-{number}"
            with self.subTest(number=number), patch.object(app, "post_response") as post:
                with self.assertRaises(wire.LanguageError):
                    app.prepare_run(run, paths, replace(self.config, max_requests=budget), task_id=task)
                self.assertFalse(run.exists())
                post.assert_not_called()

    def test_line_presentation_is_exact_without_changing_typed_prompt_or_source(self):
        raw = ' 甲\t"引文"\r\n\r\n乙\\字\u2028丙\n'.encode('utf-8')
        request = prepare_request(raw, ArtifactRef("engineering", "line-source", "1", app.hash_bytes(raw)),
                                  request_id="lines", scope="source presentation only")
        prompt = app.language_prompt(request)
        self.assertTrue(prompt.startswith(app.typed_modeling_prompt(request) + "\n\n"))
        table = json.loads(prompt.rsplit("\nSOURCE_LINES_JSON=", 1)[1])
        expected = [' 甲\t"引文"', '', '乙\\字', '丙']
        self.assertEqual(table["line_count"], 4)
        self.assertEqual(table["lines"], [{"line": n, "text": text} for n, text in enumerate(expected, 1)])
        self.assertEqual([x["text"].encode('utf-8') for x in table["lines"]],
                         [line.encode('utf-8') for line in request.text.splitlines()])
        self.assertEqual(request.text.encode('utf-8'), raw)

        from modelspine_requirements.typed_domain import inspect_typed_candidate
        source = b"Alpha\n\nBeta\n"
        request = prepare_request(source, ArtifactRef("engineering", "empty-line", "1", app.hash_bytes(source)),
                                  request_id="empty-line", scope="engineering source evidence only")
        table = json.loads(app.language_prompt(request).rsplit("\nSOURCE_LINES_JSON=", 1)[1])
        quote = "\n".join(row["text"] for row in table["lines"][:2])
        self.assertEqual(quote, "Alpha\n")
        data = json.loads(candidate(request))
        span = {"start_line": 1, "end_line": 2, "quote": quote}
        data["traces"][0]["evidence"] = [span]
        self.assertEqual(inspect_typed_candidate(request, wire.encoded(data)).language, "valid")
        for wrong_quote in ("Alpha", "Alpha\n\n"):
            span["quote"] = wrong_quote
            with self.assertRaises(ContractError):
                inspect_typed_candidate(request, wire.encoded(data))

    def test_line_presentation_does_not_repair_generated_fragment_quote(self):
        data = json.loads(candidate(self.requests[0]))
        data["traces"][0]["evidence"][0]["quote"] = self.requests[0].text[:2]
        raw = wire.encoded(data)
        receipt = self.execute(envelope(raw))
        self.assertEqual((self.run / "attempts/001/candidate.raw").read_bytes(), raw)
        self.assertIn("candidate_rejected", receipt["stop_reasons"])
        self.assertEqual(app.read_review(Path(receipt["review_project"]))["inspection"]["status"], "rejected")

    def test_valid_response_same_candidate_review_and_unverified_check(self):
        receipt = self.execute()
        raw = (self.run / "attempts/001/candidate.raw").read_bytes()
        self.assertEqual(raw, candidate(self.requests[0]))
        view = app.read_review(Path(receipt["review_project"]))
        self.assertEqual(view["candidate_ref"]["content_hash"], app.hash_bytes(raw))
        self.assertEqual(view["inspection"]["status"], "valid")
        self.assertEqual(view["inspection"]["requirement_fidelity"], "not_checked")
        self.assertEqual(receipt["generation_provenance"], "not_verified")
        self.assertIsNone(receipt["cost"])
        self.assertTrue(receipt["continue_allowed"])

    def test_same_candidate_is_readable_via_existing_D_http_entry(self):
        from model_review_ui import ReviewServer
        import base64
        receipt = self.execute()
        with ReviewServer(Path(receipt["review_project"])) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                connection.request("GET", "/api/review", headers={"X-Review-Token": server.action_token})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                rendered = json.loads(response.read())
                self.assertEqual(base64.b64decode(rendered["view"]["candidate_base64"]), candidate(self.requests[0]))
                self.assertEqual(rendered["view"]["candidate_ref"], receipt["candidate_ref"])
                self.assertTrue(rendered["presentation"])
            finally:
                connection.close()
                server.shutdown()
                thread.join(timeout=5)

    def test_invalid_json_fences_and_wrong_binding_are_preserved_not_repaired(self):
        raw = b'```json\n{}\n```'
        receipt = self.execute(envelope(raw))
        self.assertEqual((self.run / "attempts/001/candidate.raw").read_bytes(), raw)
        self.assertIn("candidate_rejected", receipt["stop_reasons"])
        self.assertEqual(app.read_review(Path(receipt["review_project"]))["inspection"]["status"], "rejected")
        with patch.object(app, "post_response") as post:
            with self.assertRaisesRegex(wire.LanguageError, "previous_attempt_stopped"):
                app.execute_next(self.run, self.config, expected_plan_sha256=self.expected)
            post.assert_not_called()

    def test_wrong_request_candidate_rejected_in_existing_checker(self):
        receipt = self.execute(envelope(candidate(self.requests[1])))
        self.assertIn("candidate_rejected", receipt["stop_reasons"])
        view = app.read_review(Path(receipt["review_project"]))
        self.assertEqual(view["inspection"]["diagnostics"][0]["code"], "conflict")

    def test_response_model_difference_and_missing_usage_visible_but_stop(self):
        receipt = self.execute(envelope(candidate(self.requests[0]), model="different-model", usage=None))
        self.assertEqual(receipt["returned_model"], "different-model")
        self.assertEqual(receipt["usage_status"], "unknown")
        self.assertIsNone(receipt["usage"])
        self.assertIn("response_model_mismatch", receipt["stop_reasons"])
        self.assertIn("usage_unknown", receipt["stop_reasons"])
        self.assertIsNotNone(receipt["review_project"])

    def test_truncated_generation_keeps_partial_text_in_review(self):
        receipt = self.execute(envelope(b'{"schema_version":', status="incomplete",
                                       incomplete_details={"reason": "max_output_tokens"}))
        self.assertIn("response_not_completed", receipt["stop_reasons"])
        self.assertIsNotNone(receipt["review_project"])

    def test_http_error_and_credential_echo_do_not_leak(self):
        raw = ("failure Bearer " + KEY).encode()
        receipt = self.execute(raw, status=401)
        self.assertEqual(receipt["response_bytes"], "redacted")
        self.assertNotEqual(receipt["received_sha256"], receipt["stored_sha256"])
        self.assertIn("credential_echo_redacted", receipt["stop_reasons"])
        for path in self.run.rglob("*"):
            if path.is_file():
                self.assertNotIn(KEY.encode(), path.read_bytes())
        self.assertNotIn(KEY, repr(self.config))

    def test_timeout_counted_and_stops(self):
        receipt = self.execute(b"partial", status=None, transport="timeout")
        self.assertEqual(receipt["stop_reasons"], ["timeout"])
        self.assertTrue((self.run / "attempts/001/reservation.json").exists())

    def test_http_failure_keeps_envelope_and_does_not_extract_default_candidate(self):
        raw = b'{"error":{"message":"synthetic unavailable"}}'
        receipt = self.execute(raw, status=503)
        self.assertEqual(receipt["http_status"], 503)
        self.assertEqual(receipt["stop_reasons"], ["http_failure"])
        self.assertIsNone(receipt["candidate"])
        self.assertEqual((self.run / "attempts/001/response.body").read_bytes(), raw)

    def test_actual_partial_transport_body_is_saved_and_batch_stops(self):
        receipt = self.execute(b"prefix-partial", transport="truncated_http_body")
        self.assertEqual((self.run / "attempts/001/response.body").read_bytes(), b"prefix-partial")
        self.assertEqual(receipt["stop_reasons"], ["truncated_http_body"])
        self.assertIsNone(receipt["review_project"])

    def test_persistent_budget_two_calls_no_third_and_no_reset(self):
        bodies = [envelope(candidate(request)) for request in self.requests]
        # Exercise the actual adapter/Request construction, with only I/O replaced.
        with patch.object(wire.urllib.request, "build_opener") as build:
            build.return_value.open.side_effect = [
                http_response(body, f"Content-Length: {len(body)}\r\n".encode()) for body in bodies]
            for slot in (1, 2):
                second = app.execute_next(self.run, self.config, expected_plan_sha256=self.expected)
                self.assertTrue(second["continue_allowed"])
                sent = build.return_value.open.call_args.args[0]
                self.assertEqual(sent.data, (self.run / f"input-{slot}/payload.json").read_bytes())
                self.assertEqual(json.loads(sent.data)["text"], {"format": {"type": "json_object"}})
            self.assertEqual(build.return_value.open.call_count, 2)
            with self.assertRaisesRegex(wire.LanguageError, "planned_budget_exhausted"):
                app.execute_next(self.run, self.config, expected_plan_sha256=self.expected)
            self.assertEqual(build.return_value.open.call_count, 2)
        self.assertEqual(second["slot"], 2)
        code = ("import sys;sys.path.insert(0," + repr(str(app.REPO / 'apps')) + ");import language_modeling as a;"
                "from language_response import Config;"
                "c=Config('https://api.openai-proxy.org','https://api.openai-proxy.org/v1','offline-unused','gpt-6-luna',3,4096);"
                "a.execute_next(" + repr(str(self.run)) + ",c,expected_plan_sha256=" + repr(self.expected) + ")")
        result = subprocess.run([sys.executable, "-B", "-I", "-c", code], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"planned_budget_exhausted", result.stderr)
        with self.assertRaises(FileExistsError):
            app.prepare_run(self.run, self.paths, self.config, task_id="offline-test")
        self.assertEqual(len(list((self.run / "attempts").iterdir())), 2)

    def test_json_mode_tamper_or_delete_rejected_even_with_rehashed_plan(self):
        for label in ("changed", "deleted"):
            with self.subTest(label=label), patch.object(app, "post_response") as post:
                run = self.root / label
                app.prepare_run(run, self.paths, self.config, task_id="offline-format-binding")
                path = run / "input-1/payload.json"
                payload = json.loads(path.read_bytes())
                if label == "changed":
                    payload["text"]["format"]["type"] = "text"
                else:
                    del payload["text"]
                path.write_bytes(wire.encoded(payload))
                plan_path = run / "plan.json"
                plan = json.loads(plan_path.read_bytes())
                plan["items"][0]["files"]["payload.json"] = app.hash_bytes(path.read_bytes())
                plan_path.write_bytes(wire.encoded(plan))
                with self.assertRaisesRegex(wire.LanguageError, "request_binding_conflict"):
                    app.execute_next(run, self.config, expected_plan_sha256=app.hash_bytes(plan_path.read_bytes()))
                post.assert_not_called()
                self.assertEqual(list((run / "attempts").iterdir()), [])

    def test_json_mode_failures_preserved_consume_slot_and_never_fallback(self):
        refusal = [{"type": "message", "role": "assistant", "status": "completed",
                    "content": [{"type": "refusal", "refusal": "engineering refusal"}]}]
        cases = (
            ("unsupported", 400, b'{"error":{"message":"unsupported text.format"}}', "http_failure", None),
            ("refusal", 200, envelope(b"", output=refusal), "unsupported_output_shape", None),
            ("incomplete", 200, envelope(b'{"', status="incomplete"), "response_not_completed", b'{"'),
            ("non_json", 200, envelope(b'{"issues":['), "candidate_rejected", b'{"issues":['),
            ("wrong_typed_shape", 200, envelope(b'{}'), "candidate_rejected", b'{}'),
        )
        for label, status, raw, reason, extracted in cases:
            with self.subTest(label=label):
                run = self.root / label
                prepared = app.prepare_run(run, self.paths, self.config, task_id="offline-format-failure")
                with patch.object(app, "post_response", return_value=wire.Exchange(status, raw, "received")) as post:
                    receipt = app.execute_next(run, self.config, expected_plan_sha256=prepared["plan_sha256"])
                    self.assertFalse(receipt["continue_allowed"])
                    self.assertIn(reason, receipt["stop_reasons"])
                    self.assertEqual(json.loads(post.call_args.args[1])["text"], {"format": {"type": "json_object"}})
                    self.assertEqual((run / "attempts/001/response.body").read_bytes(), raw)
                    self.assertEqual(receipt["response_bytes"], "original_http_body")
                    if extracted is None:
                        self.assertIsNone(receipt["candidate"])
                        self.assertIsNone(receipt["review_project"])
                    else:
                        self.assertEqual((run / "attempts/001/candidate.raw").read_bytes(), extracted)
                        view = app.read_review(Path(receipt["review_project"]))
                        self.assertEqual(view["inspection"]["status"], "rejected")
                    with self.assertRaisesRegex(wire.LanguageError, "previous_attempt_stopped"):
                        app.execute_next(run, self.config, expected_plan_sha256=prepared["plan_sha256"])
                    self.assertEqual(post.call_count, 1)
                self.assertEqual([p.name for p in (run / "attempts").iterdir()], ["001"])
                self.assertTrue((run / "attempts/001/reservation.json").is_file())

    def test_tampered_request_plan_method_and_configuration_refuse_before_network(self):
        with patch.object(app, "post_response") as post:
            for expected, cfg in (("0" * 64, self.config), (self.expected, replace(self.config, max_output_tokens=4000))):
                with self.assertRaises(wire.LanguageError):
                    app.execute_next(self.run, cfg, expected_plan_sha256=expected)
            with patch.object(app, "method_hashes", return_value={}):
                with self.assertRaises(wire.LanguageError):
                    app.execute_next(self.run, self.config, expected_plan_sha256=self.expected)
            (self.run / "input-1/request.json").write_bytes((self.run / "input-2/request.json").read_bytes())
            with self.assertRaisesRegex(wire.LanguageError, "input_hash_conflict"):
                app.execute_next(self.run, self.config, expected_plan_sha256=self.expected)
            post.assert_not_called()

    def test_write_failure_crash_and_corruption_never_refund_or_replay(self):
        original_save = app.save
        def fail(path, raw):
            if path.name == "response.body":
                raise OSError("offline write failure")
            original_save(path, raw)
        with patch.object(app, "save", side_effect=fail):
            with self.assertRaises(OSError):
                self.execute()
        with patch.object(app, "post_response") as post:
            with self.assertRaisesRegex(wire.LanguageError, "incomplete_attempt"):
                app.execute_next(self.run, self.config, expected_plan_sha256=self.expected)
            post.assert_not_called()

    def test_receipt_corruption_and_busy_lock_stop(self):
        self.execute()
        (self.run / "attempts/001/receipt.json").write_bytes(b'{')
        with self.assertRaisesRegex(wire.LanguageError, "receipt_hash_conflict"):
            app.execute_next(self.run, self.config, expected_plan_sha256=self.expected)
        (self.run / ".run.lock").write_bytes(b"")
        with self.assertRaisesRegex(wire.LanguageError, "run_busy"):
            app.execute_next(self.run, self.config, expected_plan_sha256=self.expected)

    def assert_preflight_stops(self, code):
        before = list((self.run / "attempts").iterdir())
        with patch.object(app, "post_response", side_effect=AssertionError("network reached before preflight rejection")) as post:
            with self.assertRaisesRegex((wire.LanguageError, ContractError), code):
                app.execute_next(self.run, self.config, expected_plan_sha256=self.expected)
            post.assert_not_called()
        self.assertEqual(list((self.run / "attempts").iterdir()), before)

    def test_aud01_truncated_mixed_escape_echo_is_redacted_on_disk(self):
        mixed = ''.join(c if i % 2 else '\\u%04x' % ord(c) for i, c in enumerate(KEY))
        raw = ('{"error":{"message":"' + mixed + '"}').encode()
        receipt = self.execute(raw, status=401)
        saved = (self.run / "attempts/001/response.body").read_bytes()
        self.assertEqual(receipt["response_bytes"], "redacted")
        self.assertEqual(receipt["received_sha256"], app.hash_bytes(raw))
        self.assertEqual(receipt["stored_sha256"], app.hash_bytes(saved))
        self.assertNotEqual(receipt["received_sha256"], receipt["stored_sha256"])
        self.assertIn("credential_echo_redacted", receipt["stop_reasons"])
        self.assertFalse(receipt["continue_allowed"])
        # Decode the received JSON string tokens even though the envelope is incomplete.
        import re
        for path in self.run.rglob("*"):
            if path.is_file():
                data = path.read_bytes()
                self.assertNotIn(KEY.encode(), data)
                for token in re.findall(rb'"(?:[^"\\]|\\.)*"', data):
                    self.assertNotIn(KEY, json.loads(token))
        self.assert_preflight_stops("previous_attempt_stopped")

    def test_aud02_complete_json_with_short_http_body_stops_next_slot(self):
        body = envelope(candidate(self.requests[0]))
        response = http_response(body, f"Content-Length: {len(body) + 100}\r\n".encode())
        with patch.object(wire.urllib.request, "build_opener") as build:
            build.return_value.open.return_value = response
            receipt = app.execute_next(self.run, self.config, expected_plan_sha256=self.expected)
            self.assertEqual(build.return_value.open.call_count, 1)
        self.assertEqual(receipt["transport_status"], "truncated_http_body")
        self.assertEqual((self.run / "attempts/001/response.body").read_bytes(), body)
        self.assertFalse(receipt["continue_allowed"])
        self.assertIsNone(receipt["candidate"])
        self.assertTrue(response.isclosed())
        self.assert_preflight_stops("previous_attempt_stopped")

    def test_aud01_truncated_outer_nested_mixed_echo_redacted_on_disk(self):
        mixed = ''.join(c if i % 2 == 0 else '\\u%04x' % ord(c) for i, c in enumerate(KEY))
        inner = '{"error":"' + mixed + '"}'
        full = json.dumps({"output_text": inner}).encode()
        raw = full[:-3]
        receipt = self.execute(raw, status=400)
        saved = (self.run / "attempts/001/response.body").read_bytes()
        self.assertEqual(receipt["response_bytes"], "redacted")
        self.assertEqual(receipt["received_sha256"], app.hash_bytes(raw))
        self.assertEqual(receipt["stored_sha256"], app.hash_bytes(saved))
        # Reattach ONLY the known test suffix to detect recoverable fake secrets.
        # Production storage/extraction never completes the received response.
        self.assertNotIn(KEY, json.loads(json.loads(saved + full[-3:])["output_text"])["error"])
        self.assertIn("credential_echo_redacted", receipt["stop_reasons"])
        self.assert_preflight_stops("previous_attempt_stopped")

    def test_aud04_input_two_corrupt_before_slot_one(self):
        (self.run / "input-2/source.txt").write_bytes(b"changed")
        self.assert_preflight_stops("input_hash_conflict")

    def test_aud04_input_one_corrupt_before_slot_two(self):
        self.execute()
        (self.run / "input-1/source.txt").write_bytes(b"changed")
        self.assert_preflight_stops("input_hash_conflict")

    def first_review_with_question(self):
        data = json.loads(candidate(self.requests[0]))
        data["issues"] = [{"id": "q", "kind": "missing_information", "text": "待回答",
                           "related_ids": ["item"], "question": "物件是什么？",
                           "evidence": data["traces"][0]["evidence"]}]
        receipt = self.execute(envelope(wire.encoded(data)))
        self.assertTrue(receipt["continue_allowed"])
        project = Path(receipt["review_project"])
        view = app.read_review(project)
        action = ReviewAction("model-review/0.1", "answer-1", view["project_id"],
                              decode(ArtifactRef, view["request_ref"]), decode(ArtifactRef, view["candidate_ref"]),
                              decode(ArtifactRef, view["review_ref"]), decode(ArtifactRef, view["questions"][0]["ref"]),
                              "engineering-actor", "answer", "尚不确定", (), None)
        return project, view, action

    def test_aud04_formal_action_replace_failure_pending_stops_network(self):
        project, _, action = self.first_review_with_question()
        with patch.object(model_review.os, "replace", side_effect=OSError("synthetic replace failure")):
            with self.assertRaises(OSError):
                model_review.submit_action(project, action)
        self.assertTrue((project / model_review.PENDING).is_file())
        with self.assertRaises(ContractError) as caught:
            app.read_review(project)
        self.assertEqual(caught.exception.code, "incomplete_write")
        self.assert_preflight_stops("review_recovery_failed")

    def test_aud04_legitimate_answer_new_review_version_allows_slot_two(self):
        project, view, action = self.first_review_with_question()
        model_review.submit_action(project, action)
        updated = app.read_review(project)
        self.assertNotEqual(updated["review_ref"], view["review_ref"])
        self.assertEqual(updated["candidate_ref"], view["candidate_ref"])
        with patch.object(app, "post_response", return_value=wire.Exchange(200, envelope(candidate(self.requests[1])), "received")) as post:
            receipt = app.execute_next(self.run, self.config, expected_plan_sha256=self.expected)
            self.assertEqual(post.call_count, 1)
        self.assertTrue(receipt["continue_allowed"])

    def test_aud04_valid_store_with_wrong_request_rejected(self):
        receipt = self.execute()
        other = self.root / "other-review"
        other.mkdir()
        app.create_review(other, self.requests[1], candidate(self.requests[1]), session_id="language-1")
        (Path(receipt["review_project"]) / model_review.STATE).write_bytes((other / model_review.STATE).read_bytes())
        self.assert_preflight_stops("review_binding_conflict")

    def test_aud04_valid_store_with_wrong_candidate_rejected(self):
        receipt = self.execute()
        other = self.root / "other-review"
        other.mkdir()
        app.create_review(other, self.requests[0], candidate(self.requests[0]) + b"\n", session_id="language-1")
        (Path(receipt["review_project"]) / model_review.STATE).write_bytes((other / model_review.STATE).read_bytes())
        self.assert_preflight_stops("review_binding_conflict")

    def test_aud04_public_recovery_corrupt_and_busy_store_stop_network(self):
        receipt = self.execute()
        project = Path(receipt["review_project"])
        state = project / model_review.STATE
        original = state.read_bytes()
        state.write_bytes(b'{')
        self.assert_preflight_stops("review_recovery_failed")
        state.write_bytes(original)
        lock = project / model_review.LOCK
        lock.write_bytes(b'')
        self.assert_preflight_stops("review_recovery_failed")
        self.assertTrue(lock.is_file())


class TransportTests(unittest.TestCase):
    def test_aud01_mixed_json_escape_case_short_escapes_and_negative_control(self):
        key = 'fake/a"b\\c-Z'
        spellings = [json.dumps(key)[1:-1],
                     ''.join('\\u%04X' % ord(c) if i % 2 else json.dumps(c)[1:-1]
                             for i, c in enumerate(key)),
                     json.dumps(key)[1:-1].replace('/', '\\/')]
        for spelling in spellings:
            for suffix in ('"}', '"', ''):
                with self.subTest(spelling=spelling, suffix=suffix):
                    raw = ('{"detail":"' + spelling + suffix).encode()
                    safe, changed = wire.redact(raw, key)
                    self.assertTrue(changed)
                    self.assertIn(b'[REDACTED_CREDENTIAL]', safe)
                    self.assertNotIn(key.encode(), safe)
        raw = b'{"detail":"fake/a different value"'
        self.assertEqual(wire.redact(raw, key), (raw, False))

    def test_aud01_bounded_nested_strings_complete_and_truncated_controls(self):
        mixed = ''.join(c if i % 2 == 0 else '\\u%04x' % ord(c) for i, c in enumerate(KEY))
        for depth in range(1, 5):
            nested = '{"error":"' + mixed + '"}'
            normal = '{"error":"ordinary \\u0061 text"}'
            for _ in range(depth):
                nested = json.dumps({"text": nested})
                normal = json.dumps({"text": normal})
            for cut in range(0, 6):
                with self.subTest(depth=depth, cut=cut):
                    full = nested.encode()
                    raw = full[:-cut] if cut else full
                    safe, hit = wire.redact(raw, KEY)
                    self.assertTrue(hit)
                    decoded = (safe + full[-cut:] if cut else safe).decode()
                    for _ in range(depth):
                        decoded = json.loads(decoded)["text"]
                    self.assertNotIn(KEY, json.loads(decoded)["error"])
                    control = normal.encode()[:-cut] if cut else normal.encode()
                    self.assertEqual(wire.redact(control, KEY), (control, False))

    def test_aud02_real_http_response_complete_length_and_eof_delimited(self):
        body = b'{"engineering":true}'
        for framing in (f"Content-Length: {len(body)}\r\n".encode(), b""):
            with self.subTest(framing=framing), patch.object(wire.urllib.request, "build_opener") as build:
                response = http_response(body, framing)
                build.return_value.open.return_value = response
                cfg = wire.Config("https://api.openai-proxy.org", "https://api.openai-proxy.org/v1", KEY, "gpt-6-luna", 3, 4096)
                result = wire.post_response(cfg, b'{}')
                self.assertEqual((result.transport_status, result.raw), ("received", body))
                self.assertTrue(response.isclosed())

    def test_aud02_real_chunked_body_complete_and_early_eof(self):
        cfg = wire.Config("https://api.openai-proxy.org", "https://api.openai-proxy.org/v1", KEY, "gpt-6-luna", 3, 4096)
        for body, expected in ((b'3\r\nabc\r\n0\r\n\r\n', "received"),
                               (b'5\r\nabc', "truncated_http_body")):
            with self.subTest(body=body), patch.object(wire.urllib.request, "build_opener") as build:
                response = http_response(body, b'Transfer-Encoding: chunked\r\n')
                build.return_value.open.return_value = response
                result = wire.post_response(cfg, b'{}')
                self.assertEqual((result.transport_status, result.raw), (expected, b'abc'))
                self.assertTrue(response.isclosed())

    def test_incremental_transport_still_bounds_size_time_and_http_error_body(self):
        cfg = wire.Config("https://api.openai-proxy.org", "https://api.openai-proxy.org/v1", KEY, "gpt-6-luna", 3, 4096)
        for limit, timeout, expected, length in ((16, 120, "response_size_limit", 17),
                                                 (100, 0, "timeout", 21)):
            with self.subTest(expected=expected), patch.object(wire.urllib.request, "build_opener") as build:
                response = http_response(b'x' * 21, b'Content-Length: 21\r\n')
                build.return_value.open.return_value = response
                with patch.object(wire, "MAX_ENVELOPE_BYTES", limit), patch.object(wire, "TIMEOUT_SECONDS", timeout):
                    result = wire.post_response(cfg, b'{}')
                self.assertEqual((result.transport_status, len(result.raw)), (expected, length))
                self.assertTrue(response.isclosed())
        with patch.object(wire.urllib.request, "build_opener") as build:
            response = http_response(b'error', b'Content-Length: 5\r\n')
            build.return_value.open.side_effect = urllib.error.HTTPError(cfg.base_url, 503, 'synthetic', {}, response)
            result = wire.post_response(cfg, b'{}')
            self.assertEqual((result.http_status, result.transport_status, result.raw), (503, 'received', b'error'))
            self.assertTrue(response.isclosed())

    def test_aud03_real_http_socket_timeout_preserves_21_bytes(self):
        reader, writer = socket.socketpair()
        self.addCleanup(reader.close)
        self.addCleanup(writer.close)
        reader.settimeout(0.05)
        body = b'123456789012345678901'
        writer.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 121\r\n\r\n" + body)
        response = http.client.HTTPResponse(reader)
        response.begin()
        with patch.object(wire.urllib.request, "build_opener") as build:
            build.return_value.open.return_value = response
            cfg = wire.Config("https://api.openai-proxy.org", "https://api.openai-proxy.org/v1", KEY, "gpt-6-luna", 3, 4096)
            result = wire.post_response(cfg, b'{}')
            self.assertEqual(build.return_value.open.call_count, 1)
        self.assertEqual(result.transport_status, "timeout")
        self.assertEqual(result.raw, body)
        self.assertTrue(response.isclosed())

    def test_configuration_missing_empty_model_limits_and_no_secret_exception(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / ".env"
            values = dict(zip(wire.NAMES, ["https://api.openai-proxy.org", "https://api.openai-proxy.org/v1", KEY, "gpt-6-luna", "3", "4096"]))
            for key, value in (("MODELSPINE_MODEL", ""), ("MODELSPINE_MAX_REQUESTS", "4"), ("MODELSPINE_MAX_OUTPUT_TOKENS", "4097")):
                changed = {**values, key: value}
                path.write_text("\n".join(k + "=" + v for k, v in changed.items()), encoding="utf-8")
                with self.assertRaises(wire.LanguageError) as caught:
                    wire.load_config(path)
                self.assertNotIn(KEY, str(caught.exception))
            path.write_text("MODELSPINE_API_KEY=" + KEY)
            with self.assertRaisesRegex(wire.LanguageError, "missing_configuration"):
                wire.load_config(path)
            path.write_text("\n".join(k + "=" + v for k, v in values.items()))
            self.assertEqual(wire.load_config(path).model, "gpt-6-luna")

    def test_redirect_handler_rejects_before_authorization_can_be_forwarded(self):
        request = urllib.request.Request("https://api.openai-proxy.org/v1/responses", headers={"Authorization": "Bearer " + KEY})
        for code in (301, 302, 303, 307, 308):
            with self.assertRaises(urllib.error.HTTPError):
                wire.NoRedirect().redirect_request(request, None, code, "redirect", {}, "https://untrusted.invalid/")

    def test_transport_timeout_and_http_partial_have_no_retry(self):
        cfg = wire.Config("https://api.openai-proxy.org", "https://api.openai-proxy.org/v1", KEY, "gpt-6-luna", 3, 4096)
        with patch.object(wire.urllib.request, "build_opener") as build:
            opener = build.return_value
            opener.open.side_effect = urllib.error.URLError(TimeoutError(KEY))
            result = wire.post_response(cfg, b'{}')
            self.assertEqual(result.transport_status, "timeout")
            self.assertEqual(opener.open.call_count, 1)
        with patch.object(wire.urllib.request, "build_opener") as build:
            response = build.return_value.open.return_value.__enter__.return_value
            # read1 is called on the object returned by open, not its __enter__ result.
            response = build.return_value.open.return_value
            response.code = 200
            response.read1.side_effect = [b"prefix-", http.client.IncompleteRead(b"partial", 100)]
            result = wire.post_response(cfg, b'{}')
            self.assertEqual(result.transport_status, "truncated_http_body")
            self.assertEqual(result.raw, b"prefix-partial")

    def test_closed_extraction_rejects_alternatives_and_duplicate_envelope(self):
        good = json.loads(envelope(b'{}'))
        for output in ([], good["output"] * 2, [{"type": "function_call"}],
                       [{"type": "message", "role": "assistant", "content": [{"type": "refusal", "refusal": "no"}]}]):
            raw, info = wire.extract_response(wire.encoded({**good, "output": output}), "gpt-6-luna")
            self.assertIsNone(raw)
            self.assertIn("unsupported_output_shape", info["stop_reasons"])
        with self.assertRaises(wire.LanguageError):
            wire.extract_response(b'{"output":[],"output":[]}', "gpt-6-luna")

    def test_json_escaped_key_echo_redaction(self):
        raw = ('{"detail":"' + KEY[:7] + ''.join('\\u%04x' % ord(c) for c in KEY[7:]) + '"}').encode()
        safe, changed = wire.redact(raw, KEY)
        self.assertTrue(changed)
        self.assertNotIn(KEY, json.loads(safe)["detail"])
        safe, changed = wire.redact(envelope(raw), KEY)
        self.assertTrue(changed)
        nested = json.loads(safe)["output"][0]["content"][0]["text"]
        self.assertNotIn(KEY, json.loads(nested)["detail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
