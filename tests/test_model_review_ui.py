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


def engineering_project(definition_ref, *, reading=4, state="known", complete=True):
    """Original offline instance fixture using the existing public ProjectModel."""
    return {"schema_version":"finite-project/0.1", "id":"engineering-observation", "version":"1",
            "definition":definition_ref, "objects":[
                {"id":"station", "entity":"$candidate", "slots":[{"field":"reading", "state":state,
                    "value":reading if state == "known" else None}]},
                {"id":"probe", "entity":"peer", "slots":[]}],
            "links":[{"relation":"linked", "source":"station", "target":"probe"}], "population_complete":complete}


def submission(view, identity="project-1", purpose="example", **project_args):
    return {"schema_version":"model-review-project/0.1", "id":identity, "project_id":view["project_id"],
            "request_ref":view["request_ref"], "candidate_ref":view["candidate_ref"], "expected_review_ref":view["review_ref"],
            "actor":"local-reviewer", "purpose":purpose, "project":engineering_project(view["definition_ref"], **project_args)}


def adoption(view, identity="adopt-1", proposal=0):
    return {"schema_version":"model-review-adoption/0.1", "id":identity, "project_id":view["project_id"],
            "request_ref":view["request_ref"], "candidate_ref":view["candidate_ref"], "expected_review_ref":view["review_ref"],
            "actor":"local-reviewer", "proposal_ref":view["proposals"][proposal]["ref"], "text":"明确采纳工程修订；未证明意图忠实"}


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

    def post(self, value, path="/api/action"):
        code, raw = self.request("POST", path, json.dumps(value).encode())
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

    def test_instances_save_check_reopen_positive_negative_unknown(self):
        initial = self.view()
        for i, (reading, state, purpose, expected) in enumerate([
                (4,"known","example","satisfied"), (20,"known","counterexample","violated"),
                (None,"unknown","project","unknown")]):
            value = submission(self.view(), "project-" + str(i), purpose, reading=reading, state=state)
            code, receipt = self.post(value, "/api/project")
            self.assertEqual(code,200)
            reopened = self.view()
            before = (self.root / "model-review.json").read_bytes()
            code, result = self.post({"project_ref":receipt["project_ref"], "expected_review_ref":reopened["review_ref"]}, "/api/project/check")
            self.assertEqual(code,200)
            check=result["check"]
            self.assertEqual(check["purpose"],purpose)
            self.assertEqual(check["candidate_ref"],initial["candidate_ref"])
            self.assertEqual(check["definition_ref"],initial["definition_ref"])
            self.assertEqual(next(r["status"] for r in check["report"]["outcomes"] if r["obligation"] == "range"),expected)
            self.assertIn("period",check["required_residuals"])
            self.assertEqual((self.root / "model-review.json").read_bytes(),before)
        self.assertEqual(len(read_review(self.root)["projects"]),3)
        self.assertEqual(self.post(submission(initial,"stale-instance"),"/api/project")[0],409)

    def test_adopt_history_reset_stale_and_illegal_proposal(self):
        self.assertEqual(self.post(action(self.view()))[0],200)
        self.assertEqual(self.post(action(self.view(),"confirmed","confirm",targets=["$candidate"]))[0],200)
        self.assertEqual(self.post(submission(self.view()),"/api/project")[0],200)
        self.assertEqual(self.post(action(self.view(),"bad","propose_edit",proposal=b'{bad'))[0],200)
        self.assertEqual(self.post(adoption(self.view(),"bad-adopt"),"/api/adopt")[0],400)
        raw=json.loads(base64.b64decode(self.view()["candidate_base64"]))
        raw["definition"]["version"]="2"
        self.assertEqual(self.post(action(self.view(),"good","propose_edit",proposal=dumps(raw).encode()))[0],200)
        old=self.view()
        code,receipt=self.post(adoption(old,proposal=1),"/api/adopt")
        self.assertEqual(code,200)
        new=self.view()
        self.assertEqual(new["candidate_ref"],receipt["next_candidate_ref"])
        self.assertNotEqual(new["candidate_ref"],old["candidate_ref"])
        self.assertEqual(new["source_text"],old["source_text"])
        self.assertEqual(new["history"][0]["view"]["actions"],old["actions"])
        self.assertEqual(new["history"][0]["view"]["projects"],old["projects"])
        self.assertEqual(new["issues"],old["issues"])
        for key in ("confirmations","projects","proposals","actions"):
            self.assertEqual(new[key],[])
        self.assertEqual(new["instance_conformance"],"not_run")
        self.assertEqual(self.post(action(old,"old-after-adopt"))[0],409)
        self.assertEqual(self.post({"project_ref":old["projects"][0]["ref"],"expected_review_ref":new["review_ref"]},"/api/project/check")[0],409)

    def test_new_routes_keep_origin_size_binding_and_write_failure(self):
        view=self.view()
        value=submission(view)
        body=json.dumps(value).encode()
        before=(self.root / "model-review.json").read_bytes()
        for route in ("/api/project","/api/project/check","/api/adopt"):
            self.assertEqual(self.request("POST",route,body,{"Origin":"https://evil.invalid"})[0],403)
            self.assertEqual(self.request("POST",route,body,{"Content-Length":"524289"})[0],413)
        value["project"]["definition"]["content_hash"]="0" * 64
        self.assertEqual(self.post(value,"/api/project")[0],409)
        self.assertEqual((self.root / "model-review.json").read_bytes(),before)
        with patch("model_review.os.replace",side_effect=PermissionError("offline project write failure")):
            code,result=self.post(submission(self.view(),"write-failure"),"/api/project")
        self.assertEqual((code,result["status"]),(500,"error"))
        self.assertEqual((self.root / "model-review.json").read_bytes(),before)


def phase_two_fixture(root):
    """D-authored explicit local configuration; never a language-produced candidate."""
    from modelspine_protocols import decode, to_data
    from modelspine_protocols.application import LocalWebSpec, acceptance_digest
    from modelspine_protocols.domain_language import DomainDefinition, ProjectModel
    from domain_checks import check_project
    request, raw = engineering_input()
    source = ("观测台读数小于10，连接探头。选择单用户127.0.0.1及会话令牌；编辑、检查、保存、载入。"
              "明确将全部观测字段放在观测视图；JSON保存至data/observations.json并保留全部版本。"
              "无初始数据；公开实例读数4满足规则，最大整数为预期违反反例。" + ATTACK)
    request = prepare_request(source.encode(), ArtifactRef("ui-application", "source", "1", sha256(source.encode()).hexdigest()),
                              request_id="ui-application", scope=PROVENANCE)
    candidate = json.loads(raw)
    candidate["request_hash"] = digest(request)
    candidate["issues"] = []
    candidate["definition"]["residuals"] = []
    candidate["traces"] = [{"element":t["element"], "evidence":[{"start_line":1,"end_line":1,"quote":source}]}
                           for t in candidate["traces"] if t["element"] != "period"]
    view = create_review(root, request, dumps(candidate).encode(), session_id="ui-application")
    cases = []
    definition = decode(DomainDefinition, candidate["definition"])
    for name, reading in (("positive", 4), ("negative-int64", 9223372036854775807)):
        project = engineering_project(view["definition_ref"], reading=reading)
        report = to_data(check_project(definition, decode(ProjectModel, project), project_id=view["project_id"]))
        cases.append({"ref":{"project_id":view["project_id"],"artifact_id":"public/"+name,"revision":"1","content_hash":"0"*64},
                      "description":PROVENANCE+" "+name, "public":True,"steps":["edit","check","save","load"],"project":project,
                      "expected_outcomes":[{k:o[k] for k in ("obligation","target","status")} for o in report["outcomes"]]})
    spec = {"schema_version":"local-project-web/0.1","id":"observations","version":"1",
            **{k:view[k] for k in ("project_id","request_ref","source_ref","definition_ref","candidate_ref","review_ref")},
            "initial_project_ref":None,"no_initial_data_reason":"原文明确无初始数据", "edit_scope":{"entities":["$candidate","peer"],"fields":["reading"],"relations":["linked"]},
            "views":[{"id":"observations","title":"观测 "+ATTACK,"entities":["$candidate","peer"],"fields":["reading"],"relations":["linked"]}],
            "tasks":[{"id":x,"action":x,"view_id":"observations"} for x in ("edit","check","save","load")],
            "storage":{"kind":"local_json","relative_path":"data/observations.json","retention":"retain_all_versions"},
            "access":{"bind":"127.0.0.1","audience":"single_local_user","credential":"session_token","allowed_actions":["edit","check","save","load"]},
            "evidence":[{"area":area,"ref":view["source_ref"],"quote":source,"reason":"人工工程原文明确选择此项"}
                        for area in ("initial_project","edit_scope","tasks","views","storage","access","acceptance")],
            "acceptance_cases":cases,"confirmation_refs":[],"required_unresolved":[],"unsupported_requirements":[]}
    dto = decode(LocalWebSpec,spec)
    for item, case in zip(spec["acceptance_cases"],dto.acceptance_cases):
        item["ref"]["content_hash"] = acceptance_digest(case)
    return spec, view


class PhaseTwoHTTPTests(unittest.TestCase):
    request = ReviewHTTPTests.request
    post = ReviewHTTPTests.post
    view = ReviewHTTPTests.view
    tearDown = ReviewHTTPTests.tearDown

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.spec, self.initial = phase_two_fixture(self.root)
        self.server = ReviewServer(self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def prepare(self, spec=None, head=None, version=None):
        return self.post({"spec":spec or self.spec,"expected_spec_ref":head,"next_version":version},"/api/spec/prepare")

    def test_draft_specific_confirmation_save_reopen_and_conflicts(self):
        self.assertEqual(json.loads(self.request(path="/api/spec")[1])["status"], "not_saved")
        code, saved = self.post({"spec":self.spec,"expected_spec_ref":None},"/api/spec/save")
        self.assertEqual(code,200)
        self.assertEqual(saved["assessment"]["blockers"],["missing_spec_confirmation"])
        code, prepared = self.prepare(head=saved["spec_ref"],version="2")
        self.assertEqual(code,200)
        self.assertIn("9223372036854775807",prepared["spec_text"])
        query = {"spec":json.loads(prepared["spec_text"]),"expected_spec_ref":saved["spec_ref"],"content_hash":prepared["content_hash"],"id":"explicit-approval"}
        changed = json.loads(json.dumps(query));changed["spec"]["views"][0]["title"]="changed"
        self.assertEqual(self.post(changed,"/api/spec/confirm")[0],409)
        code, confirmed = self.post(query,"/api/spec/confirm")
        self.assertEqual(code,200)
        code, ready = self.post({"spec":json.loads(confirmed["spec_text"]),"expected_spec_ref":saved["spec_ref"]},"/api/spec/save")
        self.assertEqual(code,200)
        self.assertTrue(ready["assessment"]["generation_ready"])
        reopened = json.loads(self.request(path="/api/spec")[1])
        self.assertEqual(reopened["spec_ref"],ready["spec_ref"])
        self.assertTrue(reopened["assessment"]["generation_ready"])
        self.assertEqual(self.post({"spec":self.spec,"expected_spec_ref":saved["spec_ref"]},"/api/spec/save")[0],409)
        self.assertEqual(self.prepare(json.loads(confirmed["spec_text"]),saved["spec_ref"],"3")[0],409)

    def test_generic_confirmation_unknown_negative_and_foreign_requests(self):
        code, receipt = self.post(action(self.initial,"general",kind="confirm",targets=["review:candidate"]))
        self.assertEqual(code,200)
        self.spec.update(review_ref=receipt["review_ref"],confirmation_refs=[receipt["action_ref"]])
        prepared = self.prepare()[1]
        self.assertIn("spec_confirmation_binding",prepared["assessment"]["blockers"])
        self.spec["acceptance_cases"] = self.spec["acceptance_cases"][1:]
        self.assertIn("missing_successful_public_acceptance",self.prepare()[1]["assessment"]["blockers"])
        project=self.spec["acceptance_cases"][0]["project"]
        project["objects"][0]["slots"][0].update(state="unknown",value=None)
        blockers=self.prepare()[1]["assessment"]["blockers"]
        self.assertIn("acceptance_outcome_mismatch",blockers)
        self.assertIn("missing_successful_public_acceptance",blockers)
        self.assertEqual(self.request(path="/api/spec",headers={"X-Review-Token":"wrong"})[0],403)
        raw=json.dumps({"spec":self.spec,"expected_spec_ref":None})
        self.assertEqual(self.request("POST","/api/spec/save",raw,{"Origin":"https://evil.invalid"})[0],403)
        self.assertFalse((self.root/"application-spec.json").exists())

    def test_export_actual_answers_decline_verify_and_stale_head(self):
        from modelspine_protocols import decode
        from modelspine_protocols.review import ReviewAction
        from modelspine_requirements.revision_request import verify_revision_request
        from model_review import submit_action
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            req,raw=engineering_input()
            view=create_review(root,req,raw,session_id="export-engineering")
            refs=[]
            for kind in ("answer","decline"):
                receipt=submit_action(root,decode(ReviewAction,action(view,kind,kind,text=ATTACK if kind=="answer" else "")))
                refs.append(receipt["action_ref"]);view=read_review(root)
            original=self.server.project_dir;self.server.project_dir=root
            try:
                query={"expected_review_ref":view["review_ref"],"action_refs":refs}
                code,response=self.post(query,"/api/revision/export")
                self.assertEqual(code,200)
                envelope=verify_revision_request(json.loads(response["envelope_text"]))
                self.assertEqual(envelope["action_refs"],refs)
                self.assertEqual(envelope["context"]["generation_status"],"not_run")
                self.assertIsNone(envelope["context"]["next_candidate_ref"])
                bad={**query,"output_path":"C:/should-not-write.json"}
                self.assertEqual(self.post(bad,"/api/revision/export")[0],400)
                submit_action(root,decode(ReviewAction,action(view,"new",kind="confirm",targets=["review:candidate"])))
                self.assertEqual(self.post(query,"/api/revision/export")[0],409)
            finally:self.server.project_dir=original


if __name__ == "__main__":
    unittest.main()
