"""Hand-authored engineering HTTP checks, not language or F2 acceptance."""
import base64
from hashlib import sha256
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))
from model_review_ui import ReviewServer
from model_review import create_review, read_review
from modelspine_protocols import ArtifactRef, digest, dumps
from modelspine_requirements.domain_modeling import prepare_request

PROVENANCE = "hand_authored_engineering_only"
ATTACK = '<img src=x onerror="window.reviewInjected=1"><script>window.reviewInjected=2</script>'


def engineering_input(kind="observatory"):
    """Two original finite examples; no evaluation/heldout data or generated result."""
    source = ("观测台连接探头；读数须小于10；校准周期待澄清。" if kind == "observatory"
              else "档案有名称并关联保管人；保管期限待澄清。") + ATTACK
    raw = source.encode("utf-8")
    request = prepare_request(raw, ArtifactRef("ui-" + kind, "source", "1", sha256(raw).hexdigest()),
                              request_id="review-ui", scope=PROVENANCE)
    span = {"start_line":1, "end_line":1, "quote":source}
    lit = lambda v: {"op":"literal", "args":[], "symbol":None, "value":v}
    field = {"id":"reading", "name":"读数", "value_type":"integer", "required":True, "nullable":False}
    if kind != "observatory":
        field = {"id":"title", "name":"档案名称", "value_type":"string", "required":False, "nullable":True}
    data = {"schema_version":"typed-domain-candidate/0.1", "request_hash":digest(request), "status":"unconfirmed",
            "definition":{"schema_version":"finite-domain/0.1", "id":"ui-definition", "version":"1",
                "entities":[{"id":"$candidate", "name":"观测台" if kind == "observatory" else "档案", "fields":[field]},
                            {"id":"peer", "name":"探头" if kind == "observatory" else "保管人", "fields":[]}],
                "relations":[{"id":"linked", "name":"连接" if kind == "observatory" else "保管", "source":"$candidate", "target":"peer",
                    "targets_per_source":{"minimum":0, "maximum":"unbounded"},
                    "sources_per_target":{"minimum":0, "maximum":1}}],
                "constraints":([{"id":"range", "context":"$candidate", "applies":lit(True),
                    "assertion":{"op":"and", "args":[{"op":"lt", "args":[{"op":"field", "args":[], "symbol":"reading", "value":None},lit(10)], "symbol":None,"value":None},
                        {"op":"or", "args":[lit(True),lit(False)], "symbol":None,"value":None}], "symbol":None,"value":None},
                    "unless":{"op":"eq", "args":[{"op":"field", "args":[], "symbol":"reading", "value":None},lit(-1)], "symbol":None,"value":None}}] if kind == "observatory" else []),
                "residuals":[{"id":"period", "family":"time", "text":"周期待澄清 " + ATTACK, "required":True}]},
            "traces":[], "issues":[{"id":"q-period", "kind":"missing_information", "text":"期限未知",
                "related_ids":["period"], "question":"周期是多少？", "evidence":[span]}]}
    ids = ["$candidate", field["id"], "peer", "linked", "period"] + (["range"] if kind == "observatory" else [])
    data["traces"] = [{"element":i, "evidence":[span]} for i in ids]
    return request, dumps(data).encode("utf-8")


def action(view, identity="http-action", kind="answer", text="尚不确定", targets=None, proposal=None):
    return {"schema_version":view["schema_version"], "id":identity, "project_id":view["project_id"],
            "request_ref":view["request_ref"], "candidate_ref":view["candidate_ref"], "expected_review_ref":view["review_ref"],
            "question_ref":view["questions"][0]["ref"] if kind in ("answer", "decline") else None,
            "actor":"local-reviewer", "kind":kind, "text":text, "targets":targets or [],
            "proposal_base64":base64.b64encode(proposal).decode() if proposal is not None else None}


class ReviewHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        req, raw = engineering_input()
        create_review(self.root, req, raw, session_id="http-engineering")
        self.server = ReviewServer(self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, method="GET", path="/api/review", body=None, headers=None):
        h = {"Origin":self.server.origin, "X-Review-Token":self.server.action_token, "Content-Type":"application/json"}
        h.update(headers or {})
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        conn.request(method, path, body=body, headers=h)
        result = conn.getresponse()
        status, raw = result.status, result.read()
        conn.close()
        return status, raw

    def post(self, value):
        code, raw = self.request("POST", "/api/action", json.dumps(value).encode())
        return code, json.loads(raw)

    def view(self):
        code, raw = self.request()
        self.assertEqual(code, 200)
        return json.loads(raw)["view"]

    def test_roundtrip_reopen_and_target_disambiguation(self):
        initial = self.view()
        self.assertEqual(initial["inspection"]["status"], "valid")
        self.assertEqual(self.post(action(initial))[0], 200)
        for i, (kind, targets, proposal) in enumerate([
            ("decline", None, None), ("confirm", ["$candidate"], None),
            ("confirm", ["review:candidate"], None), ("propose_edit", None, b'{invalid <script>')]):
            self.assertEqual(self.post(action(self.view(), str(i), kind, "修改或确认", targets, proposal))[0], 200)
        reopened = read_review(self.root)
        self.assertEqual(reopened["candidate_ref"], initial["candidate_ref"])
        self.assertEqual(reopened["revision_status"], "pending")
        self.assertEqual(reopened["questions"][0]["resolution"], "unresolved")
        self.assertEqual([c["targets"] for c in reopened["confirmations"]], [["$candidate"], ["review:candidate"]])
        self.assertEqual(reopened["proposals"][0]["inspection"]["status"], "rejected")
        self.assertEqual(reopened["proposals"][0]["adoption"], "pending")

    def test_stale_page_conflict_and_question_binding(self):
        old = self.view()
        self.assertEqual(self.post(action(old))[0], 200)
        before = (self.root / "model-review.json").read_bytes()
        self.assertEqual(self.post(action(old, "stale"))[0], 409)
        bad = action(self.view(), "wrong-question")
        bad["question_ref"]["content_hash"] = "0" * 64
        self.assertEqual(self.post(bad)[0], 409)
        self.assertEqual((self.root / "model-review.json").read_bytes(), before)

    def test_foreign_and_malformed_http_do_not_write(self):
        body = json.dumps(action(self.view())).encode()
        before = (self.root / "model-review.json").read_bytes()
        for headers, expected in [({"Origin":"https://evil.invalid"},403), ({"Host":"evil.invalid"},403),
                ({"X-Review-Token":"wrong"},403), ({"Sec-Fetch-Site":"cross-site"},403),
                ({"Content-Type":"text/plain"},415), ({"Content-Length":"524289"},413),
                ({"Transfer-Encoding":"chunked"},400), ({"Content-Length":"-1"},411)]:
            with self.subTest(headers=headers):
                self.assertEqual(self.request("POST", "/api/action", body, headers)[0], expected)
        self.assertEqual(self.request("POST", "/api/action", b'{bad')[0],400)
        self.assertEqual(self.request("PUT", "/api/action", body)[0],501)
        self.assertEqual(self.request("GET", "/api/review?project_dir=C:/")[0],404)
        self.assertEqual(self.request("GET", "/api/review", headers={"X-Review-Token":""})[0],403)
        self.assertEqual((self.root / "model-review.json").read_bytes(), before)

    def test_lock_and_actual_replace_failure_never_return_recorded(self):
        value = action(self.view())
        before = (self.root / "model-review.json").read_bytes()
        lock = self.root / ".model-review.lock"
        lock.write_text("engineering lock")
        code, result = self.post(value)
        self.assertEqual((code,result["code"]), (423,"busy"))
        lock.unlink()
        with patch("model_review.os.replace", side_effect=PermissionError("engineering injected replace failure")):
            code, result = self.post(value)
        self.assertEqual(code, 500)
        self.assertEqual(result["status"], "error")
        self.assertEqual((self.root / "model-review.json").read_bytes(), before)
        self.assertTrue((self.root / ".model-review.pending").exists())
        self.assertEqual(self.request()[0],500)

    def test_invalid_candidate_still_served_with_diagnostics(self):
        other = self.root / "invalid"
        other.mkdir()
        req, _ = engineering_input("archive")
        create_review(other, req, b'\xff<script>bad</script>', session_id="invalid")
        with ReviewServer(other) as server:
            view = read_review(server.project_dir)
            self.assertEqual(view["inspection"]["status"], "rejected")
            self.assertTrue(view["inspection"]["diagnostics"])
            self.assertEqual(view["terms"], [])
            self.assertEqual(base64.b64decode(view["candidate_base64"]), b'\xff<script>bad</script>')

    def test_get_page_and_layout_assets_do_not_change_store(self):
        before = (self.root / "model-review.json").read_bytes()
        for path in ("/", "/review.js", "/review.css", "/api/review"):
            self.assertEqual(self.request(path=path)[0],200)
        self.assertEqual((self.root / "model-review.json").read_bytes(),before)


if __name__ == "__main__":
    unittest.main()
