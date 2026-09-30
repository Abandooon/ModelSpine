"""Synthetic transport engineering only. No live API and no independent semantic answers."""
from dataclasses import replace
import http.client
import json
from pathlib import Path
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
from modelspine_protocols import ArtifactRef, dumps, digest
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
        return receipt

    def test_prepare_is_network_free_and_exact_prompt_payload(self):
        payload = wire.strict_json((self.run / "input-1/payload.json").read_bytes())
        self.assertEqual(payload["input"], app.typed_modeling_prompt(self.requests[0]))
        self.assertEqual(set(payload), {"model", "input", "store", "stream", "max_output_tokens"})
        self.assertEqual((self.run / "input-1/source.txt").read_bytes(), self.requests[0].text.encode())
        self.assertFalse(payload["store"])
        self.assertNotIn(self.requests[1].text, payload["input"])
        self.assertEqual(list((self.run / "attempts").iterdir()), [])

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
        self.execute()
        with patch.object(app, "post_response", return_value=wire.Exchange(200, envelope(candidate(self.requests[1])), "received")):
            second = app.execute_next(self.run, self.config, expected_plan_sha256=self.expected)
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


class TransportTests(unittest.TestCase):
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
            # read is called on the object returned by open, not its __enter__ result.
            response = build.return_value.open.return_value
            response.code = 200
            response.read.side_effect = [b"prefix-", http.client.IncompleteRead(b"partial", 100)]
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
