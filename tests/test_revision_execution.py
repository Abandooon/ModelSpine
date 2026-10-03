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


def schema_accepts(value, node, definitions):
    """Test-only interpreter for the small emitted schema vocabulary, not a product validator."""
    if "$ref" in node: return schema_accepts(value, definitions[node["$ref"].split("/")[-1]], definitions)
    if "anyOf" in node: return any(schema_accepts(value, n, definitions) for n in node["anyOf"])
    types = node["type"] if isinstance(node["type"], list) else [node["type"]]
    kind = {dict:"object", list:"array", str:"string", int:"integer", bool:"boolean", type(None):"null"}.get(type(value))
    # JSON Schema integer is mathematical; the local DTO parser is stricter.
    if type(value) is float and value.is_integer(): kind="integer"
    if kind not in types or ("enum" in node and value not in node["enum"]): return False
    if kind == "object":
        return (set(node["required"]) <= set(value) <= set(node["properties"]) and
                all(schema_accepts(v, node["properties"][k], definitions) for k,v in value.items()))
    if kind == "array":
        return (node.get("minItems",0) <= len(value) <= node.get("maxItems",float("inf")) and
                all(schema_accepts(v,node["items"],definitions) for v in value))
    return True


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
        self.assertTrue(INSTRUCTIONS.startswith("typed-domain-revision-proposal/0.2\n"))
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

    def test_schema_closed_DTO_coverage_unions_and_recursive_expression(self):
        from dataclasses import fields
        from typing import get_args, get_type_hints
        from modelspine_requirements import typed_revision as t
        from modelspine_protocols import finite_execution as f
        from modelspine_protocols.domain_language import Bounds, BinaryRelation, Residual
        schema=app.revision_response_format()["schema"]; defs=schema["$defs"]
        expression_branches=[branch for name,node in defs.items() if name.endswith("Expr")
                             for branch in node.get("anyOf",[node]) if "properties" in branch]
        for name,cls in (("ArtifactRef",ArtifactRef),("SourceSpan",t.SourceSpan),("SourceEvidence",t.SourceEvidence),
                         ("ActionEvidence",t.ActionEvidence),("Trace",t.Trace),("Issue",t.Issue),
                         ("Field",f.Field),("EntityType",f.EntityType),("Cardinality",Bounds),
                         ("BinaryRelation",BinaryRelation),("Residual",Residual),("Constraint",f.Constraint),
                         ("DomainDefinition",f.DomainDefinition),(None,t.RevisionCandidate)):
            node=schema if name is None else defs[name]
            for branch in node.get("anyOf",[node]):
                self.assertEqual(set(branch["properties"]),{x.name for x in fields(cls)},name)
                self.assertEqual(set(branch["required"]),set(branch["properties"]));self.assertIs(branch["additionalProperties"],False)
        for branch in expression_branches:
            self.assertEqual(set(branch["properties"]),{x.name for x in fields(f.Expression)})
        ops={op for b in expression_branches for op in b["properties"]["op"]["enum"]}
        self.assertEqual(ops,set(get_args(get_type_hints(f.Expression)["op"])))
        for name,cls,key in (("Field",f.Field,"value_type"),("Issue",t.Issue,"kind"),
                             ("SourceEvidence",t.SourceEvidence,"kind"),("ActionEvidence",t.ActionEvidence,"kind"),
                             ("ActionEvidence",t.ActionEvidence,"part"),("DomainDefinition",f.DomainDefinition,"schema_version"),
                             (None,t.RevisionCandidate,"schema_version"),(None,t.RevisionCandidate,"status")):
            node=schema if name is None else defs[name]
            self.assertEqual(set(node["properties"][key]["enum"]),set(get_args(get_type_hints(cls)[key])))
        self.assertEqual({s for b in defs["Constraint"]["anyOf"] for s in b["properties"]["scope"]["enum"]},
                         set(get_args(get_type_hints(f.Constraint)["scope"])))
        self.assertEqual(defs["Constraint"]["anyOf"][0]["properties"]["operation"],{"type":"null"})
        self.assertEqual(defs["Constraint"]["anyOf"][1]["properties"]["operation"],{"type":"string"})
        self.assertEqual(defs["Cardinality"]["properties"]["maximum"]["anyOf"],
                         [{"type":"integer"},{"type":"string","enum":["unbounded"]}])
        def walk(node):
            if isinstance(node,dict):
                if "$ref" in node:self.assertIn(node["$ref"].split("/")[-1],defs)
                if node.get("type")=="object":
                    self.assertIs(node["additionalProperties"],False);self.assertEqual(set(node["required"]),set(node["properties"]))
                for v in node.values():walk(v)
            elif isinstance(node,list):
                for v in node:walk(v)
        walk(schema)
        raw=json.loads(candidate(self.envelope));self.assertTrue(schema_accepts(raw,schema,defs))
        for path in (("definition","residuals"),("traces",0,"evidence"),("revision_ref","revision")):
            data=json.loads(candidate(self.envelope));parent=data
            for key in path[:-1]:parent=parent[key]
            del parent[path[-1]];self.assertFalse(schema_accepts(data,schema,defs))
        for value in (None,"A question?"):self.assertTrue(schema_accepts(value,defs["Issue"]["properties"]["question"],defs))
        for value in (None,True,"7",7):
            e={"op":"duration","args":[],"symbol":None,"value":value}
            self.assertEqual(schema_accepts(e,defs["AnyExpr"],defs),type(value) is int)
        raw["traces"].append("explanation");self.assertFalse(schema_accepts(raw,schema,defs))
        data=json.loads(candidate(self.envelope));data["traces"][0]["evidence"][0]["span"]["start_line"]=1.0
        self.assertTrue(schema_accepts(data,schema,defs))
        with self.assertRaises(ContractError):inspect_revision_candidate(decode(review.ModelingRequest,self.envelope["review_session"]["request"]),wire.encoded(data),self.envelope["context"])
        # Fresh format values must not share mutable state across calls.
        schema["required"].clear();self.assertEqual(len(app.revision_response_format()["schema"]["required"]),7)

    def test_grouped_schema_preserves_every_operator_and_legal_nested_categories(self):
        from typing import get_args,get_type_hints
        from modelspine_protocols import finite_execution as f
        from test_finite_execution import ex
        d,_=fixture();entity=replace(d.entities[0],fields=d.entities[0].fields+(
            f.Field("n","Number","integer",True,False),f.Field("s","Text","string",True,False),
            f.Field("b","Flag","boolean",True,False),f.Field("maybe","Optional flag","boolean",False,True),
            f.Field("maybe_time","Optional time","instant",False,True)))
        entities={entity.id:entity,d.entities[1].id:d.entities[1]};relations={r.id:r for r in d.relations}
        root=ex("self");member=ex("var",symbol="entry");lit=lambda v:ex("literal",value=v)
        get=lambda key:ex("get",root,symbol=key)
        nav=ex("navigate",root,symbol="contains:out")
        filtered=ex("filter",nav,ex("eq",ex("get",ex("var",symbol="member"),symbol="quality"),lit("eligible")),symbol="member")
        instant=ex("instant",value="2026-01-01T00:00:00Z");duration=ex("duration",value=7)
        count=ex("count",filtered);maybe=get("maybe")
        typed=[(root,"object:bundle"),(member,"object:event"),(nav,"set:event"),(filtered,"set:event"),
               (ex("navigate",member,symbol="contains:in"),"set:bundle"),(count,"integer"),
               (lit(7),"integer"),(lit("text"),"string"),(lit(True),"boolean"),
               (get("n"),"integer"),(get("s"),"string"),(get("b"),"boolean"),(maybe,"boolean"),
               (instant,"instant"),(duration,"duration"),(get("deadline"),"instant"),(get("maybe_time"),"instant")]
        for op in ("and","or","implies"):
            typed.append((ex(op,ex("is_null",maybe),ex("le",count,get("n"))),"boolean"))
        typed.append((ex("not",ex("eq",get("b"),lit(False))),"boolean"))
        for operand in (root,nav,filtered,maybe,instant,duration,lit(7),lit("x")):
            typed.append((ex("is_null",operand),"boolean"))
        pairs=[(count,get("n")),(instant,get("deadline")),(duration,ex("sub",instant,get("deadline")))]
        for op in ("eq","lt","le"):
            typed.extend((ex(op,a,b),"boolean") for a,b in pairs)
        typed.extend([(ex("eq",get("s"),lit("x")),"boolean"),(ex("eq",maybe,get("b")),"boolean"),
                      (ex("eq",ex("and",lit(True),ex("is_null",nav)),ex("lt",count,lit(9))),"boolean")])
        for op in ("add","sub"):
            typed.extend([(ex(op,count,get("n")),"integer"),(ex(op,duration,ex("sub",instant,get("deadline"))),"duration"),
                          (ex(op,get("maybe_time"),duration),"instant")])
        typed.append((ex("sub",instant,get("deadline")),"duration"))
        defs=app.revision_response_format()["schema"]["$defs"]
        group={"integer":"IntExpr","string":"StringExpr","boolean":"BoolExpr","instant":"InstantExpr","duration":"DurationExpr"}
        seen=set()
        def visit(expr):
            seen.add(expr.op)
            for arg in expr.args:visit(arg)
        for expr,kind in typed:
            with self.subTest(op=expr.op,kind=kind):
                actual=f.expression_type(expr,"bundle",entities,relations,{"entry":"object:event"})
                self.assertEqual(actual[0],kind)
                name="ObjectExpr" if kind.startswith("object:") else "SetExpr" if kind.startswith("set:") else group[kind]
                self.assertTrue(schema_accepts(to_data(expr),defs[name],defs))
                self.assertTrue(schema_accepts(to_data(expr),defs["AnyExpr"],defs))
                extra=to_data(expr);extra["args"].append(to_data(lit(True)))
                self.assertFalse(schema_accepts(extra,defs["AnyExpr"],defs))
                visit(expr)
        self.assertEqual(seen,set(get_args(get_type_hints(f.Expression)["op"])))
        # No Get branch in Duration; finite Field has no Duration value_type.
        self.assertFalse(schema_accepts(to_data(get("deadline")),defs["DurationExpr"],defs))

    def test_grouped_schema_excludes_known_wrong_categories_but_keeps_local_type_boundary(self):
        from modelspine_protocols import finite_execution as f
        from test_finite_execution import ex
        d,_=fixture();root=ex("self");yes=ex("literal",value=True)
        nav=ex("navigate",root,symbol="contains:out");filtered=ex("filter",nav,yes,symbol="x")
        instant=ex("instant",value="2026-01-01T00:00:00Z");duration=ex("duration",value=7)
        defs=app.revision_response_format()["schema"]["$defs"]
        rejected=[ex("and",filtered,yes),ex("count",yes),ex("eq",root,root),ex("le",root,instant),
                  ex("get",yes,symbol="deadline"),ex("navigate",yes,symbol="contains:out"),ex("not",nav)]
        for expr in rejected:
            with self.subTest(expr=expr):self.assertFalse(schema_accepts(to_data(expr),defs["AnyExpr"],defs))
        entity=replace(d.entities[0],fields=d.entities[0].fields+(f.Field("maybe","Maybe","boolean",False,True),))
        entities={entity.id:entity,d.entities[1].id:d.entities[1]};relations={r.id:r for r in d.relations}
        admitted=[ex("and",ex("get",root,symbol="deadline"),yes),
                  ex("and",ex("get",root,symbol="maybe"),yes),
                  ex("var",symbol="unbound"),ex("filter",yes,nav,symbol="x"),
                  ex("filter",nav,nav,symbol="x"),ex("add",duration,instant),ex("add",instant,instant)]
        for expr in admitted:
            with self.subTest(expr=expr):
                self.assertTrue(schema_accepts(to_data(expr),defs["AnyExpr"],defs))
                with self.assertRaises(ContractError):f.expression_type(expr,"bundle",entities,relations)
        # Constraint roots cannot be Object/Set even though AnyExpr includes them.
        for expr in (root,nav):self.assertFalse(schema_accepts(to_data(expr),defs["BoolExpr"],defs))

    def test_readable_parent_projection_is_exact_and_recomputed(self):
        projection=self.envelope["parent_projection"]
        raw=base64.b64decode(self.envelope["context"]["parent_candidate_base64"])
        self.assertEqual(projection["text"].encode(),raw)
        self.assertEqual(projection["raw_sha256"],app.hash_bytes(raw))
        self.assertEqual(projection["candidate_ref"],self.envelope["context"]["parent_candidate_ref"])
        self.assertEqual(projection["text_status"],"exact_utf8")
        self.assertNotIn(self.envelope["context"]["parent_candidate_base64"],self.envelope["prompt"])
        for field in ("text","raw_sha256","text_status","candidate_ref"):
            changed=json.loads(wire.encoded(self.envelope));changed["parent_projection"][field]="forged"
            with self.subTest(field=field),self.assertRaises(ContractError):verify_execution_revision(changed)
        other=self.root/"invalid-parent";other.mkdir()
        review.create_review(other,decode(review.ModelingRequest,self.envelope["review_session"]["request"]),b"\xffbroken",session_id="invalid")
        v=review.read_review(other)
        op=replace(self.operation,request_ref=decode(ArtifactRef,v["request_ref"]),candidate_ref=decode(ArtifactRef,v["candidate_ref"]),expected_review_ref=decode(ArtifactRef,v["review_ref"]))
        recorded=review.record_clarification(other,op)
        stored=(other/review.STATE).read_bytes()
        with review._locked(other),self.assertRaises(ContractError) as error:
            prepare_execution_revision(review._load(other),expected_review_ref=decode(ArtifactRef,recorded["review_ref"]),action_refs=(decode(ArtifactRef,recorded["action_ref"]),))
        self.assertEqual(error.exception.code,"unsupported")
        self.assertEqual((other/review.STATE).read_bytes(),stored)
        self.assertEqual(base64.b64decode(review.read_review(other)["candidate_base64"]),b"\xffbroken")

    def test_schema_payload_tampering_and_rehashed_inputs_stop_before_POST(self):
        original={p:p.read_bytes() for p in self.run.rglob("*") if p.is_file()}
        for case in ("format","schema","prompt","projection","method","plan"):
            for p,raw in original.items():p.write_bytes(raw)
            plan=json.loads(original[self.run/"plan.json"])
            file="payload.json" if case in ("format","schema") else "prompt.txt" if case=="prompt" else "revision.json"
            if case in ("format","schema"):
                payload=json.loads((self.run/"input-1"/file).read_bytes())
                if case=="format":payload["text"]["format"]={"type":"json_object"}
                else:payload["text"]["format"]["schema"]["$defs"]["DomainDefinition"]["required"].remove("residuals")
                raw=wire.encoded(payload)
            elif case=="prompt":raw=b"forged prompt"
            elif case=="projection":
                env=json.loads(wire.encoded(self.envelope));env["parent_projection"]["text"]="forged";raw=wire.encoded(env)
            else:raw=None
            if raw is not None:
                (self.run/"input-1"/file).write_bytes(raw);plan["items"][0]["files"][file]=app.hash_bytes(raw)
            if case=="method":plan["method_sha256"]["packages/requirements/src/modelspine_requirements/revision_schema.py"]="0"*64
            (self.run/"plan.json").write_bytes(wire.encoded(plan))
            expected=app.hash_bytes(wire.encoded(plan)) if case!="plan" else "0"*64
            with self.subTest(case=case),patch.object(app,"post_response") as post:
                with self.assertRaises((wire.LanguageError,ContractError)):app.execute_next(self.run,self.config,expected_plan_sha256=expected)
                post.assert_not_called()
            self.assertFalse(list((self.run/"attempts").iterdir()))

    def test_strict_format_reaches_transport_failures_preserve_raw_and_never_fallback(self):
        for case in ("http400","refusal","incomplete","missing_residuals","trace_string"):
            run=self.root/("format-"+case)
            prepared=app.prepare_revision_run(run,self.parent,self.config,expected_review_ref=decode(ArtifactRef,self.record["review_ref"]),action_refs=(decode(ArtifactRef,self.record["action_ref"]),),task_id="engineering-only-"+case)
            env=json.loads((run/"input-1/revision.json").read_bytes());data=json.loads(candidate(env))
            if case=="missing_residuals":del data["definition"]["residuals"]
            if case=="trace_string":data["traces"].append("not an object")
            raw=wire.encoded(data);body=response(raw)
            if case=="http400":body=b'{"error":"unsupported json_schema"}'
            if case=="incomplete":body=response(raw,status="incomplete")
            if case=="refusal":
                r=json.loads(body);r["output"][0]["content"]=[{"type":"refusal","refusal":"cannot comply"}];body=wire.encoded(r)
            with patch.object(app,"post_response",return_value=wire.Exchange(400 if case=="http400" else 200,body,"received")) as post:
                result=app.execute_next(run,self.config,expected_plan_sha256=prepared["plan_sha256"])
                sent=json.loads(post.call_args.args[1]);self.assertEqual(sent["text"]["format"],app.revision_response_format())
                self.assertFalse(result["continue_allowed"])
                with self.assertRaises(wire.LanguageError):app.execute_next(run,self.config,expected_plan_sha256=prepared["plan_sha256"])
                self.assertEqual(post.call_count,1)
            self.assertEqual((run/"attempts/001/response.body").read_bytes(),body)
            if case not in ("http400","refusal"):self.assertEqual((run/"attempts/001/candidate.raw").read_bytes(),raw)
            self.assertEqual(review.read_review(self.parent)["candidate_ref"],self.view["candidate_ref"])

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

    def test_pre_schema_method_registered_and_adopted_reopen_with_current_code(self):
        from modelspine_requirements import typed_revision
        # Engineering old-method history, not a real generated candidate or copied source snapshot.
        old="typed-domain-revision-proposal/0.1.2\nFrozen engineering method before structured output."
        with patch.object(typed_revision,"INSTRUCTIONS",old):
            self.run=self.root/"old-method"
            self.prepared=app.prepare_revision_run(self.run,self.parent,self.config,
                expected_review_ref=decode(ArtifactRef,self.record["review_ref"]),
                action_refs=(decode(ArtifactRef,self.record["action_ref"]),),task_id="engineering-old-method")
            self.envelope=json.loads((self.run/"input-1/revision.json").read_bytes())
            self.execute();proposal=self.propose();review.submit_revision_proposal(self.parent,proposal)
        for adopted in (False,True):
            v=review.read_review(self.parent)
            if adopted:
                op=ProposalAdoption("model-review-adoption/0.1","adopt-old",v["project_id"],
                    decode(ArtifactRef,v["request_ref"]),decode(ArtifactRef,v["candidate_ref"]),
                    decode(ArtifactRef,v["review_ref"]),"user",decode(ArtifactRef,v["proposals"][-1]["ref"]),"Engineering explicit adoption")
                review.adopt_proposal(self.parent,op);v=review.read_review(self.parent)
            stored=(self.parent/review.STATE).read_bytes()
            run=subprocess.run([sys.executable,"-B","-I",str(app.REPO/"apps/model_review.py"),"show",
                                "--project-dir",str(self.parent)],capture_output=True)
            self.assertEqual(run.returncode,0,run.stderr.decode());self.assertEqual(json.loads(run.stdout),v)
            self.assertEqual((self.parent/review.STATE).read_bytes(),stored)

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

    def failed_output(self, envelope=None):
        data=json.loads(candidate(envelope or self.envelope))
        data["definition"]["constraints"][0]["assertion"]={"op":"eq","args":[
            {"op":"get","args":[{"op":"self","args":[],"symbol":None,"value":None}],"symbol":"deadline","value":None},
            {"op":"literal","args":[],"symbol":None,"value":"2000-01-01T00:00:00Z"}],"symbol":None,"value":None}
        return wire.encoded(data)

    def prepare_feedback(self, name="feedback", source=None, prepared=None):
        source=self.run if source is None else source;prepared=self.prepared if prepared is None else prepared
        target=self.root/name
        result=app.prepare_feedback_run(target,self.parent,self.config,failed_run_dir=source,
            expected_failed_plan_sha256=prepared["plan_sha256"],expected_failed_receipt_sha256=app.hash_bytes((source/"attempts/001/receipt.json").read_bytes()),
            expected_review_ref=decode(ArtifactRef,self.record["review_ref"]),action_refs=(decode(ArtifactRef,self.record["action_ref"]),),task_id="engineering-one-explicit-feedback")
        return target,result

    def test_feedback_recomputed_attribution_complete_raw_and_valid_explicit_adoption(self):
        raw=self.failed_output();self.execute(raw)
        stored=(self.parent/review.STATE).read_bytes();run,prepared=self.prepare_feedback()
        feedback=json.loads((run/"input-1/feedback.json").read_bytes())
        obs=feedback["observation"]
        self.assertFalse(obs["user_requirement"]);self.assertEqual(obs["failed_candidate_text"].encode(),raw)
        diag=obs["expression_diagnostics"][0]
        self.assertEqual(diag["path"],"/definition/constraints/0/assertion")
        self.assertEqual(diag["operand_types"],[["instant",False],["string",False]])
        env=json.loads((run/"input-1/revision.json").read_bytes());self.assertEqual(env,self.envelope)
        self.assertIn("Re-read the entire original requirements",(run/"input-1/prompt.txt").read_text(encoding="utf-8"))
        self.assertNotIn("checker",env["context"]["responses"][0]["verbatim"]["answer"])
        good=candidate(env)
        with patch.object(app,"post_response",return_value=wire.Exchange(200,response(good),"received")) as post:
            result=app.execute_next(run,self.config,expected_plan_sha256=prepared["plan_sha256"])
            self.assertTrue(result["continue_allowed"]);self.assertEqual(post.call_count,1)
            with self.assertRaises(wire.LanguageError):app.execute_next(run,self.config,expected_plan_sha256=prepared["plan_sha256"])
            self.assertEqual(post.call_count,1)
        self.assertEqual((self.parent/review.STATE).read_bytes(),stored)
        proposal=app.review_proposal_from_run(run,expected_plan_sha256=prepared["plan_sha256"],
            expected_receipt_sha256=app.hash_bytes((run/"attempts/001/receipt.json").read_bytes()),action_id="feedback-result",actor="host")
        self.assertEqual(base64.b64decode(proposal.proposal_base64),good)
        review.submit_revision_proposal(self.parent,proposal);view=review.read_review(self.parent)
        self.assertEqual(view["candidate_ref"],self.view["candidate_ref"])
        action=ProposalAdoption("model-review-adoption/0.1","adopt-feedback",view["project_id"],decode(ArtifactRef,view["request_ref"]),
            decode(ArtifactRef,view["candidate_ref"]),decode(ArtifactRef,view["review_ref"]),"user",decode(ArtifactRef,view["proposals"][-1]["ref"]),"Engineering explicit adoption")
        review.adopt_proposal(self.parent,action)
        self.assertEqual(base64.b64decode(review.read_review(self.parent)["candidate_base64"]),good)

    def test_rejected_complete_result_exports_unconfirmed_but_cannot_be_adopted(self):
        raw=self.failed_output();result=self.execute(raw);self.assertEqual(result["stop_reasons"],["candidate_rejected"])
        receipt=(self.run/"attempts/001/receipt.json").read_bytes()
        with self.assertRaises(ContractError):self.propose()
        with self.assertRaises(ContractError):app.review_proposal_from_run(self.run,expected_plan_sha256=self.prepared["plan_sha256"],
            expected_receipt_sha256=None,action_id="missing-authority",actor="host")
        with self.assertRaises(ContractError):app.prepare_feedback_run(self.root/"missing-authority",self.parent,self.config,
            failed_run_dir=self.run,expected_failed_plan_sha256=self.prepared["plan_sha256"],expected_failed_receipt_sha256=None,
            expected_review_ref=decode(ArtifactRef,self.record["review_ref"]),action_refs=(decode(ArtifactRef,self.record["action_ref"]),),task_id="engineering")
        proposal=app.review_proposal_from_run(self.run,expected_plan_sha256=self.prepared["plan_sha256"],
            expected_receipt_sha256=app.hash_bytes(receipt),action_id="invalid-result",actor="host")
        review.submit_revision_proposal(self.parent,proposal);v=review.read_review(self.parent)
        self.assertEqual(v["candidate_ref"],self.view["candidate_ref"])
        self.assertEqual(v["proposals"][-1]["inspection"]["status"],"rejected")
        action=ProposalAdoption("model-review-adoption/0.1","reject-adoption",v["project_id"],decode(ArtifactRef,v["request_ref"]),
            decode(ArtifactRef,v["candidate_ref"]),decode(ArtifactRef,v["review_ref"]),"user",decode(ArtifactRef,v["proposals"][-1]["ref"]),"Cannot adopt invalid proposal")
        with self.assertRaises(ContractError):review.adopt_proposal(self.parent,action)
        self.assertEqual((self.run/"attempts/001/receipt.json").read_bytes(),receipt)

    def test_feedback_and_export_reject_corrupt_inputs_receipt_checker_scope_and_stale_head(self):
        self.execute(self.failed_output());run,prepared=self.prepare_feedback()
        original={p:p.read_bytes() for p in self.run.rglob("*") if p.is_file()}
        receipt_sha=app.hash_bytes(original[self.run/"attempts/001/receipt.json"])
        for name in ("input-1/source.txt","input-1/payload.json","attempts/001/candidate.raw","attempts/001/response.body", "attempts/001/inspection.json","attempts/001/receipt.json"):
            path=self.run/name;path.write_bytes(original[path]+b"changed")
            with self.subTest(name=name),patch.object(app,"post_response") as post:
                with self.assertRaises((wire.LanguageError,ContractError)):app.execute_next(run,self.config,expected_plan_sha256=prepared["plan_sha256"])
                post.assert_not_called()
            path.write_bytes(original[path])
        plan=json.loads(original[self.run/"plan.json"]);plan["method_sha256"]["packages/protocols/src/modelspine_protocols/finite_execution.py"]="0"*64
        (self.run/"plan.json").write_bytes(wire.encoded(plan))
        with self.assertRaises(ContractError):app.prepare_feedback_run(self.root/"wrong-checker",self.parent,self.config,failed_run_dir=self.run,
            expected_failed_plan_sha256=app.hash_bytes(wire.encoded(plan)),expected_failed_receipt_sha256=receipt_sha,
            expected_review_ref=decode(ArtifactRef,self.record["review_ref"]),action_refs=(decode(ArtifactRef,self.record["action_ref"]),),task_id="engineering")
        (self.run/"plan.json").write_bytes(original[self.run/"plan.json"])
        # Rehashing a forged observation cannot make it a recomputed checker fact.
        feedback=json.loads((run/"input-1/feedback.json").read_bytes());feedback["observation"]["inspection"]["diagnostics"][0]["message"]="invented"
        (run/"input-1/feedback.json").write_bytes(wire.encoded(feedback));plan=json.loads((run/"plan.json").read_bytes())
        plan["items"][0]["files"]["feedback.json"]=app.hash_bytes(wire.encoded(feedback));(run/"plan.json").write_bytes(wire.encoded(plan))
        with patch.object(app,"post_response") as post:
            with self.assertRaises(ContractError):app.execute_next(run,self.config,expected_plan_sha256=app.hash_bytes(wire.encoded(plan)))
            post.assert_not_called()
        v=review.read_review(self.parent);review.submit_action(self.parent,ReviewAction("model-review/0.1","new-head",v["project_id"],decode(ArtifactRef,v["request_ref"]),
            decode(ArtifactRef,v["candidate_ref"]),decode(ArtifactRef,v["review_ref"]),None,"user","confirm","",("review:candidate",),None))
        with self.assertRaises(ContractError):self.prepare_feedback("stale")
        self.assertFalse(list((run/"attempts").iterdir()))

    def test_feedback_chain_bounded_and_nonreproducible_failures_stop(self):
        self.execute(self.failed_output());source=self.run;prepared=self.prepared
        for index in range(3):
            run,current=self.prepare_feedback("chain-"+str(index),source,prepared)
            env=json.loads((run/"input-1/revision.json").read_bytes())
            with patch.object(app,"post_response",return_value=wire.Exchange(200,response(self.failed_output(env)),"received")):
                result=app.execute_next(run,self.config,expected_plan_sha256=current["plan_sha256"])
            self.assertEqual(result["stop_reasons"],["candidate_rejected"]);source,prepared=run,current
        with self.assertRaises(ContractError) as error:self.prepare_feedback("fourth",source,prepared)
        self.assertEqual(error.exception.code,"unsupported");self.assertFalse((self.root/"fourth").exists())
        from modelspine_requirements.revision_feedback import observe
        request=decode(review.ModelingRequest,self.envelope["review_session"]["request"])
        with self.assertRaises(ContractError):observe(request,b"\xff",self.envelope["context"])
        data=json.loads(candidate(self.envelope));data["revision_ref"]=self.view["candidate_ref"]
        with self.assertRaises(ContractError):observe(request,wire.encoded(data),self.envelope["context"])

    def test_unsafe_transport_results_never_export_to_review(self):
        for case in ("http","refusal","incomplete","credential"):
            run=self.root/("unsafe-"+case);prepared=app.prepare_revision_run(run,self.parent,self.config,
                expected_review_ref=decode(ArtifactRef,self.record["review_ref"]),action_refs=(decode(ArtifactRef,self.record["action_ref"]),),task_id="engineering")
            env=json.loads((run/"input-1/revision.json").read_bytes());body=response(candidate(env));http=200
            if case=="http":http=400
            if case=="incomplete":body=response(candidate(env),status="incomplete")
            if case=="credential":body=response(candidate(env),echo=self.config.key)
            if case=="refusal":
                value=json.loads(body);value["output"][0]["content"]=[{"type":"refusal","refusal":"no"}];body=wire.encoded(value)
            with patch.object(app,"post_response",return_value=wire.Exchange(http,body,"received")):app.execute_next(run,self.config,expected_plan_sha256=prepared["plan_sha256"])
            with self.subTest(case=case),self.assertRaises(ContractError):app.review_proposal_from_run(run,expected_plan_sha256=prepared["plan_sha256"],
                expected_receipt_sha256=app.hash_bytes((run/"attempts/001/receipt.json").read_bytes()),action_id="unsafe",actor="host")


if __name__ == "__main__": unittest.main(verbosity=2)
