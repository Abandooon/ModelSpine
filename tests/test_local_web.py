"""Public hand-authored engineering requirements, not heldout or generated tests.

One asset has exactly one label; ready must be true; amount <= explicitly chosen
limit; note is optional. All edit/check/save/load actions are explicitly chosen.
Valid data survives restart; rule/cardinality/unknown/old writes cannot change it.
"""
from copy import deepcopy
import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
import http.client
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))
import local_web as app
import application_spec
import model_review
from domain_checks import check_project
from modelspine_protocols import ArtifactRef, ContractError, decode, digest, dumps, to_data
from modelspine_protocols.application import LocalWebSpec, acceptance_digest, spec_content_hash
from modelspine_protocols.domain_language import ProjectModel
from modelspine_protocols.review import ReviewAction, ProposalAdoption, WHOLE_CANDIDATE
from modelspine_requirements.domain_modeling import prepare_request
from modelspine_implementation.local_runtime import Engine, LOCK, exclusive, safe_path
from modelspine_implementation.local_web import materialize


def engineering(root, *, limit=100, version="1", definition_version="1", old_spec_ref=None):
    """Public requirements and expectations fixed here, independent of generator."""
    text = ("HAND_AUTHORED_ENGINEERING_ONLY. Asset has ready:boolean required, amount:int64 required, optional note:string; "
            "exactly one label per asset, unlimited assets per label. Ready is true. Explicit engineering evolution: "
            "amount <= 100 initially; compatible revision allows 200 (or explicit signed Int64 maximum boundary); "
            "a tightening revision allows 50 and must refuse existing 150 or larger data. "
            "No initial data: operator explicitly enters first complete ProjectModel. Edit all asset/label fields and labels relation. "
            "One Main view with explicit edit/check/save/load tasks. Local JSON at data/projects.json, retain_all_versions. "
            "Bind 127.0.0.1 for single_local_user with session_token; allow edit/check/save/load. "
            "Public acceptance: ready=true, amount=10, one label and missing optional note may save; "
            "ready=false, missing label and unknown ready must be refused. No domain roles, integrations or background tasks.")
    source = text.encode("utf-8")
    request = prepare_request(source, ArtifactRef("local-web-engineering", "source", "1", sha256(source).hexdigest()),
                              request_id="request", scope="hand_authored_engineering_only")
    lit = lambda v: {"op":"literal", "args":[], "symbol":None, "value":v}
    field = lambda v: {"op":"field", "args":[], "symbol":v, "value":None}
    definition = {"schema_version":"finite-domain/0.1", "id":"assets", "version":definition_version,
        "entities":[{"id":"asset", "name":"Asset", "fields":[
            {"id":"ready", "name":"Ready", "value_type":"boolean", "required":True, "nullable":False},
            {"id":"amount", "name":"Amount", "value_type":"integer", "required":True, "nullable":False},
            {"id":"note", "name":"Note", "value_type":"string", "required":False, "nullable":False}]},
            {"id":"label", "name":"Label", "fields":[]}],
        "relations":[{"id":"tagged", "name":"Tagged", "source":"asset", "target":"label",
                      "targets_per_source":{"minimum":1,"maximum":1}, "sources_per_target":{"minimum":0,"maximum":"unbounded"}}],
        "constraints":[{"id":"is-ready", "context":"asset", "applies":lit(True), "assertion":field("ready"), "unless":lit(False)},
                       {"id":"amount-limit", "context":"asset", "applies":lit(True),
                        "assertion":{"op":"le", "args":[field("amount"),lit(limit)], "symbol":None,"value":None}, "unless":lit(False)}],
        "residuals":[]}
    span = {"start_line":1, "end_line":1, "quote":text}
    candidate = {"schema_version":"typed-domain-candidate/0.1", "request_hash":digest(request), "status":"unconfirmed",
                 "definition":definition, "traces":[{"element":i, "evidence":[span]} for i in
                      ("asset","ready","amount","note","label","tagged","is-ready","amount-limit")], "issues":[]}
    if (root / model_review.STATE).exists():
        view = model_review.read_review(root)
        previous_spec = application_spec.read_spec(root)
        old_spec_ref = decode(ArtifactRef, previous_spec["spec_ref"])
        proposal = ReviewAction("model-review/0.1", "change-"+version, view["project_id"],
             decode(ArtifactRef,view["request_ref"]),decode(ArtifactRef,view["candidate_ref"]),decode(ArtifactRef,view["review_ref"]),
             None,"engineering-user","propose_edit","Explicit engineering threshold revision to "+str(limit),(),
             base64.b64encode(dumps(candidate).encode("utf-8")).decode("ascii"))
        model_review.submit_action(root,proposal)
        view = model_review.read_review(root)
        adoption = ProposalAdoption("model-review-adoption/0.1","adopt-"+version,view["project_id"],
             decode(ArtifactRef,view["request_ref"]),decode(ArtifactRef,view["candidate_ref"]),decode(ArtifactRef,view["review_ref"]),
             "engineering-user",decode(ArtifactRef,view["proposals"][-1]["ref"]),"Explicitly adopt engineering revision")
        model_review.adopt_proposal(root,adoption)
        view = model_review.read_review(root)
    else:
        view = model_review.create_review(root, request, dumps(candidate).encode("utf-8"), session_id="engineering")
    project = {"schema_version":"finite-project/0.1", "id":"inventory", "version":version, "definition":view["definition_ref"],
               "objects":[{"id":"a", "entity":"asset", "slots":[{"field":"ready","state":"known","value":True},
                                                                  {"field":"amount","state":"known","value":10}]},
                          {"id":"l", "entity":"label", "slots":[]}],
               "links":[{"relation":"tagged","source":"a","target":"l"}], "population_complete":True}
    expected = [{"obligation":o,"target":t,"status":s} for o,t,s in (
        ("ready","a","satisfied"),("amount","a","satisfied"),("note","a","not_applicable"),
        ("tagged:out","a","satisfied"),("tagged:in","l","satisfied"),
        ("is-ready","a","satisfied"),("amount-limit","a","satisfied"))]
    case = {"ref":{"project_id":view["project_id"],"artifact_id":"public-positive","revision":"1","content_hash":"0"*64},
            "description":"Hand-authored public positive: one ready asset amount 10 with exactly one label; optional note absent",
            "public":True,"steps":["edit","check","save","load"],"project":project,"expected_outcomes":expected}
    from modelspine_protocols.application import PublicAcceptance
    case["ref"]["content_hash"] = acceptance_digest(decode(PublicAcceptance, case))
    spec = {"schema_version":"local-project-web/0.1", "id":"asset-editor", "version":version, "project_id":view["project_id"],
            **{k:view[k] for k in ("request_ref","source_ref","definition_ref","candidate_ref","review_ref")},
            "initial_project_ref":None, "no_initial_data_reason":"Operator explicitly supplies first ProjectModel; no default data",
            "edit_scope":{"entities":["asset","label"],"fields":["ready","amount","note"],"relations":["tagged"]},
            "tasks":[{"id":x,"action":x,"view_id":"main"} for x in ("edit","check","save","load")],
            "views":[{"id":"main","title":"Main","entities":["asset","label"],"fields":["ready","amount","note"],"relations":["tagged"]}],
            "storage":{"kind":"local_json","relative_path":"data/projects.json","retention":"retain_all_versions"},
            "access":{"bind":"127.0.0.1","audience":"single_local_user","credential":"session_token","allowed_actions":["edit","check","save","load"]},
            "evidence":[{"area":area,"ref":view["source_ref"],"quote":text,"reason":"Explicit public engineering requirement"} for area in
                        ("initial_project","edit_scope","tasks","views","storage","access","acceptance")],
            "acceptance_cases":[case],"confirmation_refs":[],"required_unresolved":[],"unsupported_requirements":[]}
    typed = decode(LocalWebSpec, spec)
    confirmation = ReviewAction("model-review/0.1","approve-"+version,view["project_id"],typed.request_ref,typed.candidate_ref,
                                typed.review_ref,None,"engineering-user","confirm","approve-local-web-spec:"+spec_content_hash(typed),
                                (WHOLE_CANDIDATE,),None)
    receipt = model_review.submit_action(root, confirmation)
    spec["review_ref"] = receipt["review_ref"]
    spec["confirmation_refs"] = [receipt["action_ref"]]
    result = application_spec.save_spec(root, decode(LocalWebSpec,spec), expected_spec_ref=old_spec_ref)
    assert result["assessment"]["generation_ready"], result
    return project, result


class Service:
    def __init__(self, root):
        self.command = [sys.executable,"-B","-I",str(root / "run.py"),"serve","--stop-on-stdin-eof"]
        self.process = subprocess.Popen(self.command, cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.first_line = self.process.stdout.readline()
        result = json.loads(self.first_line)
        assert result["status"] == "serving", result
        self.url = result["url"]
        url = urlsplit(self.url)
        self.token, self.port, self.host = url.fragment, url.port, url.netloc

    def call(self, path="/api/state", body=None, *, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1",self.port,timeout=15)
        base = {"X-Session-Token":self.token, "Origin":"http://"+self.host}
        if body is not None:
            base["Content-Type"] = "application/json"
        base.update(headers or {})
        conn.request("GET" if body is None else "POST",path,None if body is None else dumps(body).encode("utf-8"),base)
        response = conn.getresponse()
        raw = response.read()
        status = response.status
        conn.close()
        return status, json.loads(raw)

    def stop(self):
        self.process.stdin.close()
        self.process.wait(timeout=15)
        self.stdout, self.stderr = self.process.stdout.read(), self.process.stderr.read()
        self.process.stdout.close(); self.process.stderr.close()
        assert self.process.returncode == 0, self.stderr


class LocalWebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.review = self.root / "review"; self.review.mkdir()
        self.project, self.spec = engineering(self.review)
        self.result = app.generate(self.review,self.root,"release")
        self.assertEqual(self.result["status"],"generated",self.result)
        self.release = self.root / "release"

    def body(self, project=None, revision=0, action="save"):
        return {"task_id":action,"expected_revision":revision,"project_text":dumps(project or self.project)}

    def test_actual_save_reject_concurrency_restart_and_boundaries(self):
        service = Service(self.release)
        try:
            self.assertEqual(service.call()[1]["revision"],0)
            self.assertEqual(service.call("/api/save",self.body())[0],200)
            original = (self.release / "data/projects.json").read_bytes()
            for fault in ("rule","cardinality","unknown","integer"):
                bad = deepcopy(self.project); bad["version"]="2"
                if fault == "rule": bad["objects"][0]["slots"][0]["value"]=False
                if fault == "cardinality": bad["links"]=[]
                if fault == "unknown": bad["objects"][0]["slots"][0].update(state="unknown",value=None)
                if fault == "integer": bad["objects"][0]["slots"][1]["value"]=2**63
                status, report = service.call("/api/save",self.body(bad,1))
                self.assertEqual(status,422,(fault,report))
                self.assertEqual((self.release / "data/projects.json").read_bytes(),original)
            second=deepcopy(self.project); second["version"]="2"
            self.assertEqual(service.call("/api/save",self.body(second,0))[0],409)
            self.assertEqual(service.call("/api/save",self.body(second,1))[0],200)
            self.assertEqual(service.call("/api/save",self.body(second,1))[0],409)
            def compete(version):
                candidate=deepcopy(self.project); candidate["version"]=version
                return service.call("/api/save",self.body(candidate,2))[0]
            with ThreadPoolExecutor(max_workers=2) as pool:
                statuses=list(pool.map(compete,("3a","3b")))
            self.assertEqual(sorted(statuses),[200,409])
            for headers in ({"Host":"evil.invalid"},{"Origin":"http://evil.invalid"},{"X-Session-Token":"forged"}):
                self.assertEqual(service.call(headers=headers)[0],403)
            self.assertEqual(service.call("/api/../settings.json")[0],404)
            self.assertEqual(service.call("/api/save",self.body(second,2),headers={"Content-Length":str(3*1024*1024)})[0],413)
            with self.assertRaises(ContractError) as raised:
                app.generate(self.review,self.root,"busy",old_root=self.release,expected_manifest_hash=self.result["manifest_sha256"])
            self.assertEqual(raised.exception.code,"busy")
        finally:
            service.stop()
        reopened = Service(self.release)
        try:
            result=reopened.call()[1]
            self.assertEqual(result["revision"],3)
            self.assertIn(json.loads(result["project_text"])["version"],("3a","3b"))
        finally:
            reopened.stop()

    def test_spec_gate_and_output_paths(self):
        with self.assertRaises(ContractError): app.generate(self.review,self.root,"release")
        with self.assertRaises(ContractError): app.generate(self.review,self.root,"../escape")
        stored = application_spec.read_spec(self.review)
        forged=deepcopy(stored); forged["spec"]["storage"]=None
        with patch.object(application_spec,"read_spec",return_value=forged):
            with self.assertRaises(ContractError): app.load_spec(self.review)
        forged=deepcopy(stored); forged["spec_ref"]["content_hash"]="0"*64
        with patch.object(application_spec,"read_spec",return_value=forged):
            with self.assertRaises(ContractError): app.load_spec(self.review)
        self.assertFalse((self.root / "escape").exists())

    def test_compatible_update_preserves_human_data_and_tightening_refuses(self):
        engine=Engine(self.release,check_project)
        self.assertEqual(engine.execute("save",self.body())[0],200)
        original=(self.release / "data/projects.json").read_bytes()
        (self.release / "notes.txt").write_text("Human owned, keep exactly",encoding="utf-8")
        review2=self.review
        project2,_=engineering(review2,limit=200,version="2",definition_version="2")
        update=app.generate(review2,self.root,"release2",old_root=self.release,expected_manifest_hash=self.result["manifest_sha256"])
        self.assertEqual(update["status"],"generated",update)
        self.assertEqual((self.release / "data/projects.json").read_bytes(),original)
        self.assertEqual((self.root / "release2/notes.txt").read_bytes(),(self.release / "notes.txt").read_bytes())
        newer=Engine(self.root / "release2",check_project)
        self.assertEqual(newer.store()["entries"][0],json.loads(original)["entries"][0])
        project2["version"]="2";project2["objects"][0]["slots"][1]["value"]=150
        self.assertEqual(newer.execute("save",self.body(project2,2))[0],200)
        old_trial=deepcopy(self.project);old_trial["version"]="2";old_trial["objects"][0]["slots"][1]["value"]=150
        self.assertEqual(engine.execute("save",self.body(old_trial,1))[0],422)
        review3=self.review
        engineering(review3,limit=50,version="3",definition_version="3")
        with self.assertRaises(ContractError) as error:
            app.generate(review3,self.root,"release3",old_root=self.root / "release2",expected_manifest_hash=update["manifest_sha256"])
        self.assertEqual(error.exception.code,"data_conflict")
        self.assertFalse((self.root / "release3").exists())
        (self.release / "client.js").write_text("human edit",encoding="utf-8")
        with self.assertRaises(ContractError):
            app.generate(review2,self.root,"conflict",old_root=self.release,expected_manifest_hash=self.result["manifest_sha256"])
        self.assertFalse((self.root / "conflict").exists())

    def test_atomic_failure_scope_and_incomplete_stop(self):
        engine=Engine(self.release,check_project)
        data=(self.release / "data/projects.json").read_bytes()
        with patch("modelspine_implementation.local_runtime.os.replace",side_effect=OSError("injected atomic failure")):
            with self.assertRaises(OSError): engine.execute("save",self.body())
        self.assertEqual((self.release / "data/projects.json").read_bytes(),data)
        with self.assertRaises(ContractError) as error: engine.state()
        self.assertEqual(error.exception.code,"incomplete_write")

    def test_ready_split_views_without_executable_path_rejected_before_generation(self):
        saved=application_spec.read_spec(self.review)
        spec=deepcopy(saved["spec"])
        spec["version"]="split-views"
        spec["views"]=[{"id":"main","title":"Assets","entities":["asset"],"fields":["ready","amount","note"],"relations":["tagged"]},
                       {"id":"labels","title":"Labels","entities":["label"],"fields":[],"relations":[]}]
        typed=decode(LocalWebSpec,spec)
        approval=ReviewAction("model-review/0.1","approve-split",typed.project_id,typed.request_ref,typed.candidate_ref,
                              typed.review_ref,None,"engineering-user","confirm","approve-local-web-spec:"+spec_content_hash(typed),
                              (WHOLE_CANDIDATE,),None)
        receipt=model_review.submit_action(self.review,approval)
        spec["review_ref"]=receipt["review_ref"];spec["confirmation_refs"]=[receipt["action_ref"]]
        ready=application_spec.save_spec(self.review,decode(LocalWebSpec,spec),expected_spec_ref=decode(ArtifactRef,saved["spec_ref"]))
        self.assertTrue(ready["assessment"]["generation_ready"])
        with self.assertRaises(ContractError) as error: app.generate(self.review,self.root,"split")
        self.assertEqual(error.exception.code,"unsupported")
        self.assertIn("one complete",str(error.exception))
        self.assertFalse((self.root / "split").exists())

    def test_exact_runtime_closure_missing_extra_and_tampered_hash_refuse_before_write(self):
        plan=app.load_spec(self.review)
        sources=app.runtime_sources()
        required={"domain_checks.py", "modelspine_protocols/__init__.py", "modelspine_protocols/domain_language.py",
                  "modelspine_protocols/finite_execution.py"}
        self.assertEqual(set(sources),required)
        variants=[]
        for missing in required:
            variant=dict(sources);del variant[missing];variants.append(variant)
        variants.append({**sources,"extra.py":sources["domain_checks.py"]})
        changed=deepcopy(sources);changed["modelspine_protocols/finite_execution.py"]["sha256"]="0"*64
        variants.append(changed)
        for index,variant in enumerate(variants):
            with self.subTest(index=index),self.assertRaises(ContractError):
                materialize(self.root,"bad-source-"+str(index),plan,variant,checker=check_project)
            self.assertFalse((self.root / ("bad-source-"+str(index))).exists())
        for name,source in sources.items():
            self.assertEqual((self.release / name).read_bytes(),source["bytes"])
            self.assertEqual(sha256(source["bytes"]).hexdigest(),source["sha256"])

    def test_v2_refused_before_spec_read_and_before_materialization(self):
        plan=app.load_spec(self.review)
        view=model_review.read_review(self.review)
        definition=deepcopy(plan.definition);definition["schema_version"]="finite-domain/0.2"
        definition["constraints"]=definition["constraints"][:1]
        definition["constraints"][0].update(scope="invariant",operation=None,
            assertion={"op":"get","args":[{"op":"self","args":[],"symbol":None,"value":None}],"symbol":"ready","value":None})
        from modelspine_protocols.finite_execution import decode_definition, validate_definition
        validate_definition(decode_definition(definition))  # Valid v2, not a malformed v1.
        view["inspection"]["checks"]["candidate"]["definition"]=definition
        from modelspine_protocols.application import assess_application
        assessment=assess_application(decode(LocalWebSpec,plan.spec),view,checker=check_project)
        self.assertFalse(assessment["generation_ready"])
        self.assertIn("unsupported_definition_profile",assessment["blockers"])
        with patch.object(model_review,"read_review",return_value=view),patch.object(application_spec,"read_spec") as read_spec:
            with self.assertRaises(ContractError) as error: app.generate(self.review,self.root,"v2")
            self.assertEqual(error.exception.code,"unsupported")
            read_spec.assert_not_called()
        with self.assertRaises(ContractError) as error:
            materialize(self.root,"v2-direct",replace(plan,definition=definition),app.runtime_sources(),checker=check_project)
        self.assertEqual(error.exception.code,"unsupported")
        self.assertFalse((self.root / "v2").exists())
        self.assertFalse((self.root / "v2-direct").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
