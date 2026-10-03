"""Hand-authored engineering only: document bundles and audit events, no river vocabulary."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))
import bootstrap
bootstrap.activate(("requirements",))
from domain_checks import check_project, check_eligibility
from modelspine_protocols import ArtifactRef, ContractError, digest, to_data
from modelspine_protocols.domain_language import BinaryRelation, Bounds, Residual, Instance, Slot, Link, ProjectModel
from modelspine_protocols import finite_execution as f


def ex(op, *args, symbol=None, value=None):
    return f.Expression(op, args, symbol, value)


def fixture(count=2, maximum=4):
    root = ex("self")
    member = ex("var", symbol="entry")
    submitted = ex("get", root, symbol="deadline")
    occurred = ex("get", member, symbol="occurred")
    predicate = ex("and", ex("eq", ex("get", member, symbol="quality"), ex("literal", value="eligible")),
                   ex("and", ex("le", ex("sub", submitted, ex("duration", value=600)), occurred), ex("le", occurred, submitted)))
    count_expr = ex("count", ex("filter", ex("navigate", root, symbol="contains:out"), predicate, symbol="entry"))
    rule = f.Constraint("can-publish", "bundle", "eligibility", "publish", ex("literal", value=True),
                        ex("and", ex("le", ex("literal", value=2), count_expr), ex("le", count_expr, ex("literal", value=maximum))),
                        ex("literal", value=False))
    definition = f.DomainDefinition(f.PROFILE, "documents", "1", (
        f.EntityType("bundle", "Document bundle", (f.Field("deadline", "Deadline", "instant", True, False),)),
        f.EntityType("event", "Audit event", (f.Field("occurred", "Occurrence", "instant", True, False),
                                               f.Field("quality", "Quality", "string", True, False)))),
        (BinaryRelation("contains", "Bundle events", "bundle", "event", Bounds(0, "unbounded"), Bounds(1, 1)),),
        (rule,), (Residual("retention", "lifecycle", "Retain historical events", True),))
    objects = [Instance("bundle-1", "bundle", (Slot("deadline", "known", "2026-10-03T12:00:00Z"),))]
    for n in range(count):
        objects.append(Instance(f"event-{n}", "event", (Slot("occurred", "known", "2026-10-03T11:50:00Z"),
                                                        Slot("quality", "known", "eligible"))))
    project = ProjectModel("finite-project/0.1", "example", "1", ArtifactRef("engineering", definition.id, definition.version, digest(definition)),
                           tuple(objects), tuple(Link("contains", "bundle-1", f"event-{n}") for n in range(count)), True)
    return definition, project


def slot(project, identity, field, state, value=None):
    return replace(project, objects=tuple(replace(o, slots=tuple(Slot(field, state, value) if s.field == field else s for s in o.slots))
                                          if o.id == identity else o for o in project.objects))


def status(definition, project):
    report = check_eligibility(definition, project, project_id="engineering", operation="publish", target="bundle-1")
    return next(r.status for r in report.report.outcomes if r.obligation == "can-publish")


class FiniteExecutionTests(unittest.TestCase):
    def test_recursion_boundary_both_public_definition_entries(self):
        d,_=fixture()
        for depth in (24,25,500):
            expr=ex("literal",value=True)
            data={"op":"literal","args":[],"symbol":None,"value":True}
            for _ in range(depth):
                expr=ex("not",expr)
                data={"op":"not","args":[data],"symbol":None,"value":None}
            obj=replace(d,constraints=(replace(d.constraints[0],assertion=expr),))
            raw=to_data(d);raw["constraints"][0]["assertion"]=data
            for call in (lambda:f.validate_definition(obj),lambda:f.validate_definition(f.decode_definition(raw))):
                if depth==24: call()
                else:
                    with self.assertRaises(ContractError) as error: call()
                    self.assertEqual(error.exception.code,"unsupported")

    def test_count_boundaries_and_changed_upper_without_storage_invariant(self):
        for n, expected in ((0,"violated"),(1,"violated"),(2,"satisfied"),(4,"satisfied"),(5,"violated")):
            with self.subTest(n=n):
                d,p=fixture(n)
                self.assertEqual(status(d,p),expected)
                stored=check_project(d,p,project_id="engineering")
                self.assertFalse(any(r.obligation=="can-publish" for r in stored.outcomes))
                self.assertFalse(any(r.status=="violated" for r in stored.outcomes))
                self.assertEqual(next(r.status for r in stored.outcomes if r.obligation=="retention"),"unknown")
        d,p=fixture(5,5)
        self.assertEqual(status(d,p),"satisfied")

    def test_closed_seconds_and_definite_exclusion(self):
        d,p=fixture(2)
        for t,expected in (("2026-10-03T11:49:59Z","violated"),("2026-10-03T11:50:00Z","satisfied"),
                           ("2026-10-03T12:00:00Z","satisfied"),("2026-10-03T12:00:01Z","violated")):
            self.assertEqual(status(d,slot(p,"event-0","occurred","known",t)),expected)
        self.assertEqual(status(d,slot(p,"event-0","quality","known","rejected")),"violated")

    def test_unknown_filter_precision_and_kleene_exclusions(self):
        for n in (3,6):
            d,p=fixture(n)
            self.assertEqual(status(d,slot(p,f"event-{n-1}","quality","unknown")),"unknown")
        d,p=fixture(3)
        unknown=slot(p,"event-2","quality","unknown")
        self.assertEqual(status(d,slot(unknown,"event-2","occurred","known","2026-10-03T10:00:00Z")),"satisfied")
        unknown=slot(p,"event-2","occurred","unknown")
        self.assertEqual(status(d,slot(unknown,"event-2","quality","known","rejected")),"satisfied")
        self.assertEqual(status(d,replace(p,population_complete=False)),"unknown")

    def test_other_bundle_not_counted_and_direction_inverse(self):
        d,p=fixture(3)
        other=Instance("bundle-2","bundle",p.objects[0].slots)
        p=replace(p,objects=p.objects+(other,),links=tuple(replace(l,source="bundle-2") if l.target=="event-2" else l for l in p.links))
        self.assertEqual(status(d,p),"satisfied")
        d=f.validate_definition(d)
        e=ex("count",ex("navigate",ex("self"),symbol="contains:in"))
        self.assertEqual(f.expression_type(e,"event",{x.id:x for x in d.entities},{r.id:r for r in d.relations}), ("integer",False))

    def test_null_error_wins_unknown_or_false(self):
        d,p=fixture(3)
        event=replace(d.entities[1],fields=tuple(replace(x,nullable=True) if x.id=="occurred" else x for x in d.entities[1].fields))
        d=replace(d,entities=(d.entities[0],event))
        p=replace(p,definition=replace(p.definition,content_hash=digest(d)))
        for quality in ("unknown","known"):
            q=slot(slot(p,"event-2","occurred","null"),"event-2","quality",quality,"rejected" if quality=="known" else None)
            self.assertEqual(status(d,q),"error")

    def test_missing_optional_unknown_required_structural_violation(self):
        d,p=fixture(2)
        p=replace(p,objects=tuple(replace(o,slots=tuple(s for s in o.slots if s.field!="occurred")) if o.id=="event-0" else o for o in p.objects))
        self.assertEqual(status(d,p),"error")
        event=replace(d.entities[1],fields=tuple(replace(x,required=False) if x.id=="occurred" else x for x in d.entities[1].fields))
        d=replace(d,entities=(d.entities[0],event)); p=replace(p,definition=replace(p.definition,content_hash=digest(d)))
        self.assertEqual(status(d,p),"unknown")
        report=check_project(d,p,project_id="engineering")
        self.assertEqual(next(r.status for r in report.outcomes if r.obligation=="occurred" and r.target=="event-0"),"not_applicable")

    def test_timestamp_rejections_overflow_and_bool(self):
        d,p=fixture(2)
        for t in (True,0,"2026-10-03T12:00:00+00:00","2026-10-03T12:00:00.0Z","2026-02-30T12:00:00Z","2026-10-03T12:00:60Z","0000-01-01T00:00:00Z"):
            self.assertEqual(status(d,slot(p,"event-0","occurred","known",t)),"error")
        self.assertEqual(status(d,slot(p,"bundle-1","deadline","known","0001-01-01T00:00:00Z")),"error")
        for val in (True,2**63):
            with self.assertRaises(ContractError): f.expression_type(ex("duration",value=val),"bundle",{}, {})

    def test_structural_errors_and_resource_limits_are_not_business_bounds(self):
        d,p=fixture(2)
        for bad in (replace(p,links=p.links+(p.links[0],)), replace(p,links=p.links+(Link("contains","missing","event-0"),))):
            with self.assertRaises(ContractError): status(d,bad)
        with self.assertRaises(ContractError) as c: status(d,replace(p,objects=p.objects*100))
        self.assertEqual(c.exception.code,"unsupported")
        with self.assertRaises(ContractError): check_eligibility(d,p,project_id="engineering",operation="invented",target="bundle-1")

    def test_static_types_scope_and_old_profile_rejection(self):
        d,p=fixture()
        bad=replace(d.constraints[0],scope="invariant")
        with self.assertRaises(ContractError): f.validate_definition(replace(d,constraints=(bad,)))
        for ast in (ex("var",symbol="free"), ex("add",ex("instant",value="2026-01-01T00:00:00Z"),ex("instant",value="2026-01-01T00:00:00Z")),
                    ex("get",ex("self"),symbol="quality"),ex("eq",ex("literal",value=True),ex("literal",value=1))):
            with self.assertRaises(ContractError): f.expression_type(ast,"bundle",{e.id:e for e in d.entities},{r.id:r for r in d.relations})
        data=to_data(d); data["schema_version"]="finite-domain/0.1"
        with self.assertRaises(ContractError): f.decode_definition(data)


if __name__ == "__main__": unittest.main(verbosity=2)
