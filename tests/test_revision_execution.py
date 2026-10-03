"""Answer -> fake transport -> explicit adoption, hand_authored_engineering_only."""
import base64
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))
import language_modeling as app
import language_response as wire
import model_review as review
from modelspine_protocols import ArtifactRef, ContractError, decode, digest, dumps, to_data
from modelspine_protocols.review import ExternalClarification, ProposalAdoption, ProjectSubmission, ReviewAction
from modelspine_protocols.domain_language import definition_ids
from modelspine_protocols.application import LocalWebSpec, assess_application
from modelspine_requirements.revision_request import prepare_execution_revision, verify_execution_revision
from modelspine_requirements.typed_revision import inspect_revision_candidate

sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_finite_execution import fixture


def response(raw, **updates):
    data={"id":"engineering","object":"response","model":"gpt-6-luna","status":"completed","error":None,
          "incomplete_details":None,"usage":{"input_tokens":12,"output_tokens":20,"total_tokens":32},
          "output":[{"type":"message","role":"assistant","status":"completed",
                     "content":[{"type":"output_text","text":raw.decode()}]}]}
    data.update(updates)
    return wire.encoded(data)


def candidate(envelope):
    definition,_=fixture()
    ctx=envelope["context"]
    ref=ctx["responses"][0]
    action={"kind":"action","question_ref":ref["question_ref"],"action_ref":ref["action_ref"],
            "part":"answer","quote":ref["verbatim"].get("answer","")}
    source={"kind":"source","source_ref":ctx["original_source_ref"],
            "span":{"start_line":1,"end_line":1,"quote":ctx["original_source_text"]}}
    return wire.encoded({"schema_version":"typed-domain-revision/0.1","request_hash":digest(decode(
        review.ModelingRequest,envelope["review_session"]["request"])),"revision_ref":ctx["ref"],"status":"unconfirmed",
        "definition":to_data(definition),"traces":[{"element":key,"evidence":[source,action]} for key in definition_ids(definition)],"issues":[]})


class RevisionExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.parent=self.root/"project";self.parent.mkdir()
        self.view=review.engineering_demo(self.parent)["reopened"]
        self.operation=ExternalClarification("model-review-clarification/0.1","clarification",self.view["project_id"],
            decode(ArtifactRef,self.view["request_ref"]),decode(ArtifactRef,self.view["candidate_ref"]),
            decode(ArtifactRef,self.view["review_ref"]),"New composite question?","coordinator",
            "Correction: ownership is explicit.","coordinator","answer","Adopt the corrected requirement.","user",
            "Coordinator interpretation, not user wording.","coordinator")
        self.record=review.record_clarification(self.parent,self.operation)
        self.config=wire.Config("https://api.openai-proxy.org","https://api.openai-proxy.org/v1","fake-offline-secret-only",
                                "gpt-6-luna",1,40960)
        self.run=self.root/"run"
        self.prepared=app.prepare_revision_run(self.run,self.parent,self.config,
            expected_review_ref=decode(ArtifactRef,self.record["review_ref"]),action_refs=(decode(ArtifactRef,self.record["action_ref"]),),
            task_id="engineering-allocation:one-slot:not-a-real-budget")
        self.envelope=json.loads((self.run/"input-1/revision.json").read_bytes())

    def execute(self, raw=None, http=200, status="received", envelope_updates=None):
        raw=candidate(self.envelope) if raw is None else raw
        with patch.object(app,"post_response",return_value=wire.Exchange(http,response(raw,**(envelope_updates or {})),status)) as post:
            result=app.execute_next(self.run,self.config,expected_plan_sha256=self.prepared["plan_sha256"])
        self.assertEqual(post.call_count,1)
        self.assertEqual(post.call_args.args[1],(self.run/"input-1/payload.json").read_bytes())
        return result

    def test_prompt_declares_reference_targets_and_presence_without_domain_answers(self):
        from modelspine_requirements.typed_revision import INSTRUCTIONS
        self.assertTrue(INSTRUCTIONS.startswith("typed-domain-revision-proposal/0.1.2\n"))
        for text in ("Constraint.context must equal an existing Entity.id, never its name/display label.",
                     "get.symbol must be a declared Field.id belonging to the operand object's inferred entity type.",
                     "var.symbol must exactly equal a lexically enclosing filter.symbol",
                     "trace.element and each issue.related_ids entry reference an existing definition element",
                     "same selected response entry", "including revision and content_hash",
                     "A required field can carry state=unknown",
                     "pre-answer correction it adopts", "coordinator interpretation is not a substitute"):
            self.assertIn(text,INSTRUCTIONS)
        self.assertTrue(self.envelope["prompt"].startswith(INSTRUCTIONS))
        self.assertEqual(json.loads((self.run/"input-1/payload.json").read_bytes())["input"],self.envelope["prompt"])
        for business_answer in ("e3", "上传批次", "f1", "required=true"):
            self.assertNotIn(business_answer,INSTRUCTIONS)

    def test_display_names_and_wrong_reference_families_still_rejected(self):
        request=decode(review.ModelingRequest,self.envelope["review_session"]["request"])
        raw=candidate(self.envelope)
        self.assertEqual(inspect_revision_candidate(request,raw,self.envelope["context"]).language,"valid")
        for case in ("context","relation_endpoint","trace","issue","revision_ref","evidence_ref"):
            data=json.loads(raw)
            if case=="context": data["definition"]["constraints"][0]["context"]="Document bundle"
            elif case=="relation_endpoint": data["definition"]["relations"][0]["source"]="Document bundle"
            elif case=="trace": data["traces"][0]["element"]="Document bundle"
            elif case=="issue": data["issues"]=[{"id":"unresolved","kind":"ambiguity","text":"engineering issue",
                "related_ids":["Document bundle"],"question":None,"evidence":data["traces"][0]["evidence"]}]
            elif case=="revision_ref": data["revision_ref"]=self.envelope["context"]["parent_candidate_ref"]
            else: data["traces"][0]["evidence"][1]["question_ref"]=self.envelope["context"]["responses"][0]["action_ref"]
            with self.subTest(case=case),self.assertRaises(ContractError):
                inspect_revision_candidate(request,wire.encoded(data),self.envelope["context"])

    def test_prompt_leaf_values_and_time_arithmetic_match_static_contract(self):
        from modelspine_requirements.typed_revision import INSTRUCTIONS
        from modelspine_protocols import finite_execution as f
        from test_finite_execution import ex
        self.assertIn("Exactly three leaf operators carry non-null value",INSTRUCTIONS)
        self.assertIn("Every other operator has value=null",INSTRUCTIONS)
        self.assertIn("There is no implicit Int-to-Duration or String-to-Instant conversion",INSTRUCTIONS)
        self.assertNotIn("Except literals all values null",INSTRUCTIONS)
        infer=lambda e:f.expression_type(e,"bundle",{}, {})
        for op,value,kind in (("literal",-7,"integer"),("literal",True,"boolean"),
                              ("literal","2026-01-01T00:00:00Z","string"),
                              ("instant","2026-01-01T00:00:00Z","instant"),("duration",-7,"duration")):
            with self.subTest(op=op,value=value): self.assertEqual(infer(ex(op,value=value)),(kind,False))
        for e in (ex("literal"),ex("instant"),ex("duration"),ex("duration",value=True),
                  ex("duration",value="7"),ex("duration",value=2**63),ex("instant",value=7),
                  ex("not",ex("literal",value=True),value=True)):
            with self.subTest(expr=e),self.assertRaises(ContractError):infer(e)
        time=ex("instant",value="2026-01-01T00:00:00Z")
        self.assertEqual(infer(ex("add",time,ex("duration",value=-7))),("instant",False))
        with self.assertRaises(ContractError):infer(ex("add",time,ex("literal",value=-7)))
        with self.assertRaises(ContractError):infer(ex("add",ex("duration",value=-7),time))

    def test_object_arrays_reject_explanation_strings_without_removing_them(self):
        from modelspine_requirements.typed_revision import INSTRUCTIONS
        self.assertIn("never an explanation string or a JSON-encoded string",INSTRUCTIONS)
        request=decode(review.ModelingRequest,self.envelope["review_session"]["request"])
        original=candidate(self.envelope)
        self.assertEqual(inspect_revision_candidate(request,original,self.envelope["context"]).language,"valid")
        for path in (("traces",),("issues",),("definition","constraints"),("definition","entities"),
                     ("traces",0,"evidence"),("definition","constraints",0,"assertion","args")):
            data=json.loads(original);items=data
            for key in path:items=items[key]
            items.append("Engineering explanation, not a schema object.")
            raw=wire.encoded(data)
            with self.subTest(path=path),self.assertRaises(ContractError):
                inspect_revision_candidate(request,raw,self.envelope["context"])
            self.assertIn(b"Engineering explanation",raw)

    def propose(self):
        return app.revision_proposal_from_run(self.run,expected_plan_sha256=self.prepared["plan_sha256"],action_id="generated",actor="host")

    def adopt(self):
        operation=self.propose();review.submit_revision_proposal(self.parent,operation)
        view=review.read_review(self.parent)
        adoption=ProposalAdoption("model-review-adoption/0.1","adopt",view["project_id"],decode(ArtifactRef,view["request_ref"]),
            decode(ArtifactRef,view["candidate_ref"]),decode(ArtifactRef,view["review_ref"]),"user",
            decode(ArtifactRef,view["proposals"][-1]["ref"]),"Explicitly adopt proposed revision, not semantic acceptance")
        return adoption,review.adopt_proposal(self.parent,adoption)

    def test_exact_context_raw_and_no_head_change_until_explicit_actions_then_restart(self):
        initial=(self.parent/review.STATE).read_bytes()
        context=self.envelope["context"]
        self.assertEqual(context["original_source_text"],self.view["source_text"])
        self.assertNotIn("Adopt the corrected",context["original_source_text"])
        self.assertEqual(context["responses"][0]["verbatim"]["correction"],self.operation.correction_text)
        self.assertNotIn("interpretation",context["responses"][0]["verbatim"])
        self.assertEqual(verify_execution_revision(self.envelope),self.envelope)
        result=self.execute()
        self.assertTrue(result["continue_allowed"])
        self.assertEqual((self.parent/review.STATE).read_bytes(),initial)
        self.assertEqual((self.run/"attempts/001/candidate.raw").read_bytes(),candidate(self.envelope))
        operation=self.propose();r=review.submit_revision_proposal(self.parent,operation)
        pending=review.read_review(self.parent)
        self.assertEqual(pending["candidate_ref"],self.view["candidate_ref"])
        self.assertNotEqual(pending["review_ref"],self.record["review_ref"])
        self.assertEqual(review.submit_revision_proposal(self.parent,operation)["status"],"already_recorded")
        adoption,receipt=self.adopt()
        current=review.read_review(self.parent)
        self.assertNotEqual(current["candidate_ref"],self.view["candidate_ref"])
        self.assertEqual(current["parent_candidate_ref"],self.view["candidate_ref"])
        self.assertEqual(current["source_text"],self.view["source_text"])
        self.assertEqual(current["confirmations"],[])
        self.assertEqual(current["history"][-1]["view"]["actions"][-2]["action"]["question_text"],self.operation.question_text)
        saved=(self.parent/review.STATE).read_bytes()
        cli=subprocess.run([sys.executable,"-B","-I",str(Path(review.__file__)),"show","--project-dir",str(self.parent)],capture_output=True)
        self.assertEqual(cli.returncode,0,cli.stderr)
        self.assertEqual(json.loads(cli.stdout),current)
        self.assertEqual(saved,(self.parent/review.STATE).read_bytes())
        self.assertEqual(review.adopt_proposal(self.parent,adoption)["status"],"already_recorded")
        with self.assertRaises(ContractError): review.adopt_proposal(self.parent,replace(adoption,id="stale"))

    def test_bad_output_is_preserved_and_not_registered_or_repaired(self):
        before=(self.parent/review.STATE).read_bytes()
        result=self.execute(b'{"partial":')
        self.assertIn("candidate_rejected",result["stop_reasons"])
        self.assertEqual((self.run/"attempts/001/candidate.raw").read_bytes(),b'{"partial":')
        self.assertEqual((self.parent/review.STATE).read_bytes(),before)
        with self.assertRaises(ContractError): self.propose()
        with patch.object(app,"post_response") as post:
            with self.assertRaises(wire.LanguageError): app.execute_next(self.run,self.config,expected_plan_sha256=self.prepared["plan_sha256"])
            post.assert_not_called()

    def test_transport_failure_does_not_adopt_and_consumes_attempt(self):
        before=(self.parent/review.STATE).read_bytes()
        result=self.execute(http=400)
        self.assertEqual(result["stop_reasons"],["http_failure"])
        self.assertEqual(len(list((self.run/"attempts").iterdir())),1)
        self.assertEqual((self.parent/review.STATE).read_bytes(),before)
        with self.assertRaises(ContractError): self.propose()

    def test_stale_parent_stops_before_transport(self):
        current=review.read_review(self.parent)
        op=ReviewAction("model-review/0.1","confirm",current["project_id"],decode(ArtifactRef,current["request_ref"]),
            decode(ArtifactRef,current["candidate_ref"]),decode(ArtifactRef,current["review_ref"]),None,"user","confirm","",("review:candidate",),None)
        review.submit_action(self.parent,op)
        with patch.object(app,"post_response") as post:
            with self.assertRaises(wire.LanguageError): app.execute_next(self.run,self.config,expected_plan_sha256=self.prepared["plan_sha256"])
            post.assert_not_called()
        self.assertEqual(list((self.run/"attempts").iterdir()),[])

    def test_decline_unknown_and_external_question_are_not_old_issue_answers(self):
        current=review.read_review(self.parent)
        question=current["questions"][-1]
        self.assertEqual(question["kind"],"external_clarification")
        self.assertNotEqual(question["ref"],current["questions"][0]["ref"])
        unknown=replace(self.operation,id="unknown",expected_review_ref=decode(ArtifactRef,current["review_ref"]),
                        response_text="Unknown; I cannot decide.",interpretation_text="",interpretation_actor="")
        result=review.record_clarification(self.parent,unknown)
        declined=replace(unknown,id="declined",expected_review_ref=decode(ArtifactRef,result["review_ref"]),
                         response_kind="decline",response_text="")
        end=review.record_clarification(self.parent,declined)
        with review._locked(self.parent):
            session=review._load(self.parent)
            envelope=prepare_execution_revision(session,expected_review_ref=decode(ArtifactRef,end["review_ref"]),
                action_refs=(decode(ArtifactRef,result["action_ref"]),decode(ArtifactRef,end["action_ref"])))
        self.assertEqual(envelope["context"]["responses"][0]["verbatim"]["answer"],unknown.response_text)
        self.assertEqual(envelope["context"]["responses"][1]["verbatim"]["decline"],"")
        self.assertNotIn("answer",envelope["context"]["responses"][1]["verbatim"])
        self.assertEqual(review.read_review(self.parent)["candidate_ref"],self.view["candidate_ref"])
        with self.assertRaises(ContractError): review.record_clarification(self.parent,replace(declined,id="empty",response_kind="answer"))

    def test_incomplete_response_never_yields_adoptable_proposal(self):
        result=self.execute(envelope_updates={"status":"incomplete","incomplete_details":{"reason":"max_output_tokens"}})
        self.assertFalse(result["continue_allowed"])
        self.assertTrue((self.run/"attempts/001/candidate.raw").exists())
        with self.assertRaises(ContractError): self.propose()

    def test_persisted_registered_and_adopted_history_pins_original_method(self):
        from modelspine_requirements import typed_revision
        self.execute();proposal=self.propose()
        with self.assertRaises(ContractError):
            review.submit_revision_proposal(self.parent,replace(proposal,method_instructions=proposal.method_instructions+"\nforged"))
        review.submit_revision_proposal(self.parent,proposal)
        for adopted in (False,True):
            if adopted: self.adopt()
            before=review.read_review(self.parent)
            raw=(self.parent/review.STATE).read_bytes()
            with patch.object(typed_revision,"INSTRUCTIONS",typed_revision.INSTRUCTIONS+"\nPrompt-only clarification."):
                self.assertEqual(review.read_review(self.parent),before)
                with review._locked(self.parent):
                    session=review._load(self.parent)
                    fresh=prepare_execution_revision(session,expected_review_ref=review.review_ref(session),
                        action_refs=(decode(ArtifactRef,self.record["action_ref"]),))
                self.assertNotEqual(fresh["context"]["method_instructions_sha256"],self.envelope["context"]["method_instructions_sha256"])
            self.assertEqual((self.parent/review.STATE).read_bytes(),raw)

    def test_reservation_failure_keeps_consumed_slot_without_network(self):
        with patch.object(app.os,"fsync",side_effect=OSError("engineering reservation fsync")), patch.object(app,"post_response") as post:
            with self.assertRaises(OSError): app.execute_next(self.run,self.config,expected_plan_sha256=self.prepared["plan_sha256"])
            post.assert_not_called()
        with patch.object(app,"post_response") as post:
            with self.assertRaises(wire.LanguageError): app.execute_next(self.run,self.config,expected_plan_sha256=self.prepared["plan_sha256"])
            post.assert_not_called()
        self.assertEqual(len(list((self.run/"attempts").iterdir())),1)

    def test_wrong_proposal_and_adoption_write_failure_preserve_head(self):
        self.execute(); proposal=self.propose()
        for wrong in (replace(proposal,revision_ref=replace(proposal.revision_ref,content_hash="0"*64)),
                      replace(proposal,action_refs=(replace(proposal.action_refs[0],artifact_id="forged"),))):
            with self.assertRaises(ContractError): review.submit_revision_proposal(self.parent,wrong)
        review.submit_revision_proposal(self.parent,proposal)
        view=review.read_review(self.parent)
        adoption=ProposalAdoption("model-review-adoption/0.1","adoption-failed",view["project_id"],decode(ArtifactRef,view["request_ref"]),
            decode(ArtifactRef,view["candidate_ref"]),decode(ArtifactRef,view["review_ref"]),"user",decode(ArtifactRef,view["proposals"][-1]["ref"]),"explicit")
        before=(self.parent/review.STATE).read_bytes()
        with patch.object(review.os,"replace",side_effect=OSError("injected adoption persistence failure")):
            with self.assertRaises(OSError): review.adopt_proposal(self.parent,adoption)
        self.assertEqual(before,(self.parent/review.STATE).read_bytes())
        with self.assertRaises(ContractError): review.read_review(self.parent)

    def test_wrong_action_candidate_question_source_and_quote_rejected(self):
        request=decode(review.ModelingRequest,self.envelope["review_session"]["request"])
        original=json.loads(candidate(self.envelope))
        for key in ("action_ref","question_ref"):
            data=json.loads(candidate(self.envelope));data["traces"][0]["evidence"][1][key]["content_hash"]="0"*64
            with self.assertRaises(ContractError): inspect_revision_candidate(request,wire.encoded(data),self.envelope["context"])
        for kind in ("quote","source","parent"):
            data=json.loads(candidate(self.envelope))
            if kind=="quote": data["traces"][0]["evidence"][1]["quote"]=self.operation.interpretation_text
            if kind=="source": data["traces"][0]["evidence"][0]["source_ref"]["revision"]="wrong"
            if kind=="parent": data["revision_ref"]["content_hash"]="0"*64
            with self.assertRaises(ContractError): inspect_revision_candidate(request,wire.encoded(data),self.envelope["context"])
        with self.assertRaises(ContractError): review.record_clarification(self.parent,replace(self.operation,id="wrong",candidate_ref=replace(self.operation.candidate_ref,content_hash="0"*64)))
        with self.assertRaises(ContractError): app.prepare_revision_run(self.root/"bad",self.parent,self.config,
            expected_review_ref=decode(ArtifactRef,self.record["review_ref"]),action_refs=(replace(decode(ArtifactRef,self.record["action_ref"]),project_id="other"),),task_id="test")

    def test_saved_instance_scoped_check_and_v1_application_rejection(self):
        self.execute();self.adopt();view=review.read_review(self.parent)
        d,p=fixture();p=replace(p,definition=decode(ArtifactRef,view["definition_ref"]))
        submission=ProjectSubmission("model-review-project/0.1","instance",view["project_id"],decode(ArtifactRef,view["request_ref"]),
            decode(ArtifactRef,view["candidate_ref"]),decode(ArtifactRef,view["review_ref"]),"tester","example",p)
        saved=review.save_project(self.parent,submission)
        result=review.check_saved_eligibility(self.parent,decode(ArtifactRef,saved["project_ref"]),
            expected_review_ref=decode(ArtifactRef,saved["review_ref"]),operation="publish",target="bundle-1")
        self.assertEqual(result["action_execution"],"not_run")
        self.assertEqual(next(r["status"] for r in result["report"]["outcomes"] if r["obligation"]=="can-publish"),"satisfied")
        view=review.read_review(self.parent)
        spec=LocalWebSpec("local-project-web/0.1","app","1",view["project_id"],*(decode(ArtifactRef,view[k]) for k in
            ("request_ref","source_ref","definition_ref","candidate_ref","review_ref")),None,None,None,(),(),None,None,(),(),(),(),())
        assessment=assess_application(spec,view)
        self.assertFalse(assessment["generation_ready"])
        self.assertIn("unsupported_definition_profile",assessment["blockers"])

    def test_no_new_budget_after_success_and_persistence_failure_is_visible(self):
        self.execute()
        with patch.object(app,"post_response") as post:
            with self.assertRaises(wire.LanguageError): app.execute_next(self.run,self.config,expected_plan_sha256=self.prepared["plan_sha256"])
            post.assert_not_called()
        before=(self.parent/review.STATE).read_bytes()
        proposal=self.propose()
        with patch.object(review.os,"replace",side_effect=OSError("engineering replace failure")):
            with self.assertRaises(OSError): review.submit_revision_proposal(self.parent,proposal)
        self.assertEqual(before,(self.parent/review.STATE).read_bytes())
        self.assertTrue((self.parent/review.PENDING).exists())
        with self.assertRaises(ContractError) as error: review.read_review(self.parent)
        self.assertEqual(error.exception.code,"incomplete_write")


if __name__ == "__main__": unittest.main(verbosity=2)
