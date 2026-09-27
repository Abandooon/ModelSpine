"""Raw-text CLI boundaries; hand-authored payloads are not extraction evidence."""
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps"))
import domain_modeling as app
from modelspine_protocols import ArtifactRef, ContractError, digest, dumps


class DomainModelingAppTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="modelspine-domain-app-")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.source = ROOT / "tests/fixtures/domain-modeling/sources/equipment-base.txt"

    def cli(self, *arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = app.main([str(argument) for argument in arguments])
            except SystemExit as exc:
                code = exc.code
        return code, stdout.getvalue(), stderr.getvalue()

    def prepare_arguments(self, source, output):
        return ("prepare", "--source", source, "--project", "raw-domain-test",
                "--source-id", "equipment-source", "--source-version", "1",
                "--request-id", "request-one", "--scope", "从原文提出领域概念与规则",
                "--output", output)

    def prepared(self):
        path = self.folder / "request.json"
        code, stdout, stderr = self.cli(*self.prepare_arguments(self.source, path))
        self.assertEqual((code, stdout, stderr), (0, "", ""))
        return path

    def manual_response(self, request_path):
        request = app.load_request(request_path)
        lines = request.text.splitlines()
        # Intentionally incomplete: this exercises inspection, not the semantic oracle.
        candidate = {
            "schema_version": "domain-modeling-candidate/0.1",
            "id": "handwritten-contract-sample", "version": "1",
            "request_hash": digest(request), "status": "unconfirmed",
            "concepts": [{"id": "member", "name": "成员", "description": "手工合同样例",
                          "evidence": [{"start_line": 1, "end_line": 1, "quote": lines[0]}]}],
            "attributes": [], "relations": [],
            "rules": [{"id": "unexecuted-rule", "text": lines[3], "related_ids": ["member"],
                       "formalization": "not_formalized",
                       "evidence": [{"start_line": 4, "end_line": 4, "quote": lines[3]}]}],
            "issues": [{"id": "incomplete", "kind": "missing_information",
                        "text": "手工样例没有枚举完整领域内容", "related_ids": [], "question": None,
                        "evidence": [{"start_line": 1, "end_line": 1, "quote": lines[0]}]}],
        }
        path = self.folder / "manual-response.json"
        path.write_text(json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
        return path

    def test_prepare_executable_pins_real_source_without_a_model(self):
        output = self.folder / "prepared-by-cli.json"
        result = subprocess.run(
            [sys.executable, "-B", "-I", str(ROOT / "apps/domain_modeling.py"),
             *map(str, self.prepare_arguments(self.source, output))],
            cwd=self.folder, capture_output=True, encoding="utf-8", timeout=20)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        request = json.loads(output.read_text(encoding="utf-8"))
        raw = self.source.read_bytes()
        self.assertEqual(request["text"].encode("utf-8"), raw)
        self.assertEqual(request["source"]["content_hash"], sha256(raw).hexdigest())
        self.assertEqual(request["id"], "request-one")
        self.assertEqual(set(request), {"schema_version", "id", "source", "text", "scope"})

    def test_prompt_reads_only_pinned_request_and_contains_no_reference_answers(self):
        request_path = self.prepared()
        original_open = Path.open
        read_paths = []

        def request_only(path, *args, **kwargs):
            self.assertEqual(path.resolve(), request_path.resolve(),
                             "prompt must not read semantic expectations or other fixtures")
            read_paths.append(path.resolve())
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", request_only):
            code, stdout, stderr = self.cli("prompt", "--request", request_path)
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(read_paths, [request_path.resolve()])
        instructions, input_json = stdout.rsplit("\nINPUT_JSON=", 1)
        self.assertEqual(json.loads(input_json), json.loads(request_path.read_text(encoding="utf-8")))
        self.assertIn("unconfirmed", instructions)
        for answer_marker in ("equipment-base", "history-not-active", "must_not_assert",
                              "paired_changes", "观测队", "音频档案系统", "器材室"):
            self.assertNotIn(answer_marker, instructions)

    def test_exact_request_byte_limit_round_trips_file_and_redirected_stdout(self):
        source = self.folder / "boundary-source.txt"
        raw = b"item\n"
        source.write_bytes(raw)
        reference = ArtifactRef("raw-domain-test", "equipment-source", "1", sha256(raw).hexdigest())
        probe = app.prepare_request(raw, reference, request_id="request-one", scope="x")
        scope = "x" * (app.MAX_REQUEST_BYTES - len(dumps(probe).encode("utf-8")) + 1)
        expected = app.prepare_request(raw, reference, request_id="request-one", scope=scope)
        self.assertEqual(len(dumps(expected).encode("utf-8")), app.MAX_REQUEST_BYTES)

        output = self.folder / "maximum-request.json"
        arguments = list(self.prepare_arguments(source, output))
        arguments[arguments.index("--scope") + 1] = scope
        code, stdout, stderr = self.cli(*arguments)
        self.assertEqual((code, stdout, stderr), (0, "", ""))
        self.assertEqual(output.stat().st_size, app.MAX_REQUEST_BYTES)
        self.assertEqual(app.load_request(output), expected)

        code, stdout, stderr = self.cli(*arguments[:-2])
        self.assertEqual((code, stderr), (0, ""))
        redirected = self.folder / "redirected-request.json"
        redirected.write_bytes(stdout.encode("utf-8"))
        self.assertEqual(redirected.stat().st_size, app.MAX_REQUEST_BYTES)
        self.assertEqual(redirected.read_bytes(), output.read_bytes())
        self.assertEqual(app.load_request(redirected), expected)

        for request_path in (output, redirected):
            with self.subTest(request=request_path.name):
                code, prompt, stderr = self.cli("prompt", "--request", request_path)
                self.assertEqual((code, stderr), (0, ""))
                self.assertEqual(json.loads(prompt.rsplit("\nINPUT_JSON=", 1)[1]),
                                 json.loads(output.read_text(encoding="utf-8")))

    def test_manual_candidate_inspection_does_not_certify_generation_semantics_or_commit(self):
        request_path = self.prepared()
        response_path = self.manual_response(request_path)
        output = self.folder / "inspection.json"
        originals = {path: path.read_bytes() for path in (request_path, response_path)}
        before = set(self.folder.iterdir())
        code, stdout, stderr = self.cli("inspect", "--request", request_path,
                                       "--response", response_path, "--output", output)
        self.assertEqual((code, stdout, stderr), (0, "", ""))
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["mode"], "external-candidate-inspection")
        self.assertEqual(report["generation_provenance"], "not_verified")
        self.assertIs(report["model_committed"], False)
        inspection = report["inspection"]
        self.assertEqual(inspection["structure"], "valid")
        self.assertEqual(inspection["semantics"], "not_checked")
        self.assertEqual(inspection["rule_execution"], "not_implemented")
        self.assertEqual(inspection["candidate"]["status"], "unconfirmed")
        self.assertEqual(inspection["unresolved_ids"], ["incomplete"])
        self.assertEqual(inspection["response_hash"], sha256(originals[response_path]).hexdigest())
        self.assertEqual(set(self.folder.iterdir()) - before, {output})
        self.assertEqual({path: path.read_bytes() for path in originals}, originals)

    def test_changed_source_or_other_request_rejects_old_response(self):
        request_path = self.prepared()
        response_path = self.manual_response(request_path)
        original = request_path.read_text(encoding="utf-8")
        for change in ("tampered-source", "repinned-source", "other-request"):
            with self.subTest(change=change):
                request = json.loads(original)
                if change == "other-request":
                    request["id"] = "request-two"
                else:
                    request["text"] += "补充要求：器材另有标签。\n"
                    if change == "repinned-source":
                        request["source"]["content_hash"] = sha256(request["text"].encode("utf-8")).hexdigest()
                changed = self.folder / (change + ".json")
                changed.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
                output = self.folder / (change + "-inspection.json")
                code, stdout, stderr = self.cli("inspect", "--request", changed,
                                               "--response", response_path, "--output", output)
                self.assertEqual((code, stdout), (2, ""))
                self.assertEqual(json.loads(stderr)["code"], "conflict")
                self.assertFalse(output.exists())

    def test_missing_or_empty_input_fails_without_fallback(self):
        request_path = self.prepared()
        missing = self.folder / "absent.json"
        empty = self.folder / "empty-response.json"
        empty.write_bytes(b"")
        cases = (
            ("prepare", *self.prepare_arguments(missing, self.folder / "missing-source-result.json")),
            ("prompt", "prompt", "--request", missing),
            ("missing-response", "inspect", "--request", request_path, "--response", missing),
            ("empty-response", "inspect", "--request", request_path, "--response", empty),
            ("omitted-response", "inspect", "--request", request_path),
        )
        for label, *arguments in cases:
            with self.subTest(input=label):
                code, stdout, stderr = self.cli(*arguments)
                self.assertEqual((code, stdout), (2, ""))
                self.assertTrue(stderr)
                if label != "omitted-response":
                    self.assertEqual(json.loads(stderr)["status"], "error")
        self.assertFalse((self.folder / "missing-source-result.json").exists())
        self.assertFalse(missing.exists())

    def test_existing_output_is_rejected_and_original_bytes_survive(self):
        request_path = self.prepared()
        response_path = self.manual_response(request_path)
        output = self.folder / "existing-evidence.bin"
        sentinel = b"original evidence\x00\xff\r\n"
        output.write_bytes(sentinel)
        cases = (self.prepare_arguments(self.source, output),
                 ("prompt", "--request", request_path, "--output", output),
                 ("inspect", "--request", request_path, "--response", response_path, "--output", output))
        for arguments in cases:
            with self.subTest(command=arguments[0]):
                code, stdout, stderr = self.cli(*arguments)
                self.assertEqual((code, stdout), (2, ""))
                self.assertEqual(json.loads(stderr)["code"], "io_error")
                self.assertEqual(output.read_bytes(), sentinel)

    def test_unencodable_candidate_is_rejected_without_creating_output(self):
        request_path = self.prepared()
        response_path = self.manual_response(request_path)
        candidate = json.loads(response_path.read_text(encoding="utf-8"))
        candidate["concepts"][0]["description"] = "\ud800"
        response_path.write_bytes(json.dumps(candidate, ensure_ascii=True).encode("ascii"))
        output = self.folder / "surrogate-inspection.json"
        code, stdout, stderr = self.cli("inspect", "--request", request_path,
                                       "--response", response_path, "--output", output)
        self.assertEqual((code, stdout), (2, ""))
        self.assertEqual(json.loads(stderr)["code"], "invalid")
        self.assertFalse(output.exists())

        direct_output = self.folder / "surrogate-output.txt"
        with self.assertRaises(ContractError) as caught:
            app._write(direct_output, "\ud800")
        self.assertEqual(caught.exception.code, "invalid")
        self.assertFalse(direct_output.exists())

    def test_oversized_source_request_and_response_are_rejected_before_output(self):
        request_path = self.prepared()
        source = self.folder / "oversized-source.txt"
        request = self.folder / "oversized-request.json"
        response = self.folder / "oversized-response.json"
        for path, limit in ((source, app.MAX_SOURCE_BYTES), (request, app.MAX_REQUEST_BYTES),
                            (response, app.MAX_RESPONSE_BYTES)):
            path.write_bytes(b"x" * (limit + 1))
        output = self.folder / "oversized-result.json"
        cases = (self.prepare_arguments(source, output),
                 ("prompt", "--request", request, "--output", output),
                 ("inspect", "--request", request_path, "--response", response, "--output", output))
        for arguments in cases:
            with self.subTest(command=arguments[0]):
                code, stdout, stderr = self.cli(*arguments)
                self.assertEqual((code, stdout), (2, ""))
                self.assertEqual(json.loads(stderr)["code"], "unsupported")
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
