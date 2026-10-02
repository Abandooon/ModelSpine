"""Source-to-inspection-to-instance engineering checks, not extraction evidence."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from modelspine_protocols import ArtifactRef, ContractError, decode, digest, dumps, to_data
from modelspine_protocols.domain_language import (
    Constraint, DomainDefinition, EntityType, Expression, Field, Instance,
    ProjectModel, Slot, definition_ids,
)
from modelspine_requirements.domain_modeling import prepare_request
from modelspine_requirements.typed_domain import inspect_typed_candidate, typed_modeling_prompt
from modelspine_kernel.domain_projection import to_scalar_metamodel
from domain_checks import check_project

ROOT = Path(__file__).parents[1]


class FiniteValueBoundaryTests(unittest.TestCase):
    """Public-contract counterexamples, independent of the sample fixture."""

    @staticmethod
    def literal(value):
        return Expression("literal", (), None, value)

    @staticmethod
    def field(key):
        return Expression("field", (), key, None)

    def statuses(self, fields, slots, predicate, position="assertion", **overrides):
        predicates = dict(applies=self.literal(True), assertion=self.literal(True), unless=self.literal(False))
        predicates[position] = predicate
        predicates.update(overrides)
        definition = DomainDefinition("finite-domain/0.1", "boundary", "1",
            (EntityType("item", "Item", fields),), (), (Constraint("rule", "item", **predicates),), ())
        project = ProjectModel("finite-project/0.1", "p", "1",
            ArtifactRef("engineering", "boundary", "1", digest(definition)),
            (Instance("i", "item", slots),), (), True)
        return {r.obligation: r.status for r in check_project(definition, project, project_id="engineering").outcomes}

    def test_optional_missing_and_explicit_unknown_at_all_predicate_positions(self):
        fields = (Field("flag", "Flag", "boolean", False, False),)
        for slots, structure in (((), "not_applicable"), ((Slot("flag", "unknown", None),), "unknown")):
            for predicate in (self.field("flag"), Expression("is_null", (self.field("flag"),), None, None)):
                for position in ("assertion", "applies", "unless"):
                    with self.subTest(slots=slots, op=predicate.op, position=position):
                        self.assertEqual(self.statuses(fields, slots, predicate, position),
                                         {"flag": structure, "rule": "unknown"})

    def test_known_and_business_null_remain_distinct(self):
        nullable = (Field("flag", "Flag", "boolean", False, True),)
        nonnullable = (replace(nullable[0], nullable=False),)
        is_null = Expression("is_null", (self.field("flag"),), None, None)
        # Columns: assertion, applicability, exception; expected from the contract.
        for value, expected in ((True, ("satisfied", "satisfied", "not_applicable")),
                                (False, ("violated", "not_applicable", "satisfied"))):
            for position, status in zip(("assertion", "applies", "unless"), expected):
                self.assertEqual(self.statuses(nonnullable, (Slot("flag", "known", value),), self.field("flag"), position),
                                 {"flag": "satisfied", "rule": status})
        for state, value, expected in (("null", None, ("satisfied", "satisfied", "not_applicable")),
                                       ("known", True, ("violated", "not_applicable", "satisfied")),
                                       ("known", False, ("violated", "not_applicable", "satisfied"))):
            for position, status in zip(("assertion", "applies", "unless"), expected):
                self.assertEqual(self.statuses(nullable, (Slot("flag", state, value),), is_null, position),
                                 {"flag": "satisfied", "rule": status})

    def test_required_absence_and_invalid_null_are_structural_violations(self):
        for field, slots in ((Field("flag", "Flag", "boolean", True, False), ()),
                             (Field("flag", "Flag", "boolean", False, False), (Slot("flag", "null", None),))):
            for predicate in (self.field("flag"), Expression("is_null", (self.field("flag"),), None, None)):
                for position in ("assertion", "applies", "unless"):
                    self.assertEqual(self.statuses((field,), slots, predicate, position),
                                     {"flag": "violated", "rule": "error"})

    def test_nullable_comparison_errors_dominate_unknown_or_missing_in_both_orders(self):
        fields = (Field("a", "A", "integer", False, True), Field("b", "B", "integer", False, True))
        for op in ("eq", "lt", "le"):
            for others, structure in (((), "not_applicable"), ((Slot("b", "unknown", None),), "unknown"),
                                      ((Slot("b", "known", 1),), "satisfied")):
                for operands in ((self.field("a"), self.field("b")), (self.field("b"), self.field("a"))):
                    predicate = Expression(op, operands, None, None)
                    for position in ("assertion", "applies", "unless"):
                        with self.subTest(op=op, others=others, operands=operands, position=position):
                            self.assertEqual(self.statuses(fields, (Slot("a", "null", None), *others), predicate, position),
                                             {"a": "satisfied", "b": structure, "rule": "error"})
                    # Without a null operand, missing/unknown must remain unknown.
                    if structure != "satisfied":
                        self.assertEqual(self.statuses(fields, (Slot("a", "known", 1), *others), predicate)["rule"], "unknown")

    def test_applicability_gates_preserve_unknown_and_error_precedence(self):
        fields = (Field("flag", "Flag", "boolean", False, False),)
        self.assertEqual(self.statuses(fields, (), self.field("flag"), "applies", unless=self.literal(True))["rule"], "not_applicable")
        self.assertEqual(self.statuses(fields, (), self.field("flag"), "unless", applies=self.literal(False))["rule"], "not_applicable")
        fields = (Field("a", "A", "integer", False, True), Field("b", "B", "integer", False, True))
        predicate = Expression("eq", (self.field("a"), self.field("b")), None, None)
        slots = (Slot("a", "null", None),)
        self.assertEqual(self.statuses(fields, slots, predicate, "applies", unless=self.literal(True))["rule"], "error")
        self.assertEqual(self.statuses(fields, slots, predicate, "unless", applies=self.literal(False))["rule"], "error")


class FiniteDomainTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "packages/protocols/contracts/finite-domain-examples.json").read_text(encoding="utf-8"))
        self.definition = decode(DomainDefinition, self.data["definition"])
        raw = b"A unit uses parts. Active units use at most one part.\n"
        self.request = prepare_request(raw, ArtifactRef("engineering", "source", "1", sha256(raw).hexdigest()),
                                       request_id="r", scope="Engineering consumer only")
        self.candidate = dict(schema_version="typed-domain-candidate/0.1", request_hash=digest(self.request),
            status="unconfirmed", definition=to_data(self.definition), issues=[],
            traces=[dict(element=key, evidence=[dict(start_line=1, end_line=1, quote=raw.decode().strip())])
                    for key in definition_ids(self.definition)])

    def project(self, index=0):
        return decode(ProjectModel, self.data["cases"][index]["project"])

    def report(self, project, definition=None):
        return check_project(definition or self.definition, project, project_id="engineering")

    def test_public_positive_negative_unknown_and_not_applicable(self):
        for i, expected in enumerate(("satisfied", "violated", "unknown", "not_applicable", "unknown")):
            report = self.report(self.project(i))
            self.assertEqual(next(r.status for r in report.outcomes if r.obligation == "active-cap"), expected)
            self.assertEqual(report.requirement_fidelity, "not_checked")
        self.assertEqual(next(r.status for r in self.report(self.project(5)).outcomes if r.obligation == "uses:out"), "violated")

    def test_residuals_and_empty_population_cannot_be_positive_witness(self):
        definition = decode(DomainDefinition, self.data["residual_definition"])
        report = self.report(decode(ProjectModel, self.data["residual_project"]), definition)
        self.assertEqual(report.outcomes[-1].status, "unknown")
        report = self.report(replace(self.project(), objects=(), links=()))
        self.assertEqual(report.outcomes[0].status, "not_applicable")

    def test_binding_duplicates_dangling_and_wrong_endpoint_rejected(self):
        p = self.project()
        bad = [replace(p, definition=replace(p.definition, revision="2")),
               replace(p, objects=p.objects + p.objects[:1]),
               replace(p, links=p.links + p.links),
               replace(p, links=(replace(p.links[0], target="gone"),)),
               replace(p, links=(replace(p.links[0], target="u"),))]
        for project in bad:
            with self.assertRaises(ContractError):
                self.report(project)

    def test_missing_null_unknown_and_wrong_scalar_are_distinct(self):
        p = self.project()
        slot = p.objects[0].slots[0]
        for slots, field_status, rule_status in (((), "violated", "error"),
            ((replace(slot, state="null", value=None),), "violated", "error"),
            ((replace(slot, state="unknown", value=None),), "unknown", "unknown"),
            ((replace(slot, value=1),), "violated", "error")):
            changed = replace(p, objects=(replace(p.objects[0], slots=slots), *p.objects[1:]))
            outcomes = self.report(changed).outcomes
            self.assertEqual(outcomes[0].status, field_status)
            self.assertEqual(next(r.status for r in outcomes if r.obligation == "active-cap"), rule_status)

    def test_open_population_still_exposes_observed_upper_bound_violation(self):
        p = self.project(1)
        extra = replace(p.objects[1], id="third")
        p = replace(p, population_complete=False, objects=(*p.objects, extra),
                    links=(*p.links, replace(p.links[0], target="third")))
        self.assertEqual(next(r.status for r in self.report(p).outcomes if r.obligation == "uses:out"), "violated")

    def test_typed_trace_binding_and_structure_are_not_fidelity(self):
        result = inspect_typed_candidate(self.request, dumps(self.candidate).encode())
        self.assertEqual(result.requirement_fidelity, "not_checked")
        self.assertEqual(result.instance_conformance, "not_run")
        for mutation in (lambda c: c.update(request_hash="0" * 64),
                         lambda c: c.pop("schema_version"),
                         lambda c: c.update(schema_version="finite-domain/0.1"),
                         lambda c: c.update(status="accepted"),
                         lambda c: c.update(extra=True),
                         lambda c: c["traces"].pop(),
                         lambda c: c["traces"][0]["evidence"][0].update(quote="invented")):
            candidate = deepcopy(self.candidate)
            mutation(candidate)
            with self.assertRaises(ContractError):
                inspect_typed_candidate(self.request, dumps(candidate).encode())

    def test_prompt_has_no_io_or_domain_answer_catalogue(self):
        with patch("builtins.open", side_effect=AssertionError("prompt must not read files")):
            prompt = typed_modeling_prompt(self.request)
        self.assertEqual(json.loads(prompt.rsplit("INPUT_JSON=", 1)[1]), to_data(self.request))
        self.assertIn('exactly these six required root fields:\n'
                      'schema_version="typed-domain-candidate/0.1", request_hash, status="unconfirmed",\n'
                      'definition, traces, issues. Do not omit or add root fields.', prompt)
        self.assertNotIn("engineering-sample", prompt)
        self.assertNotIn("expected_rule", prompt)

    def test_three_valued_logic_and_null_error_precedence(self):
        lit = lambda v: Expression("literal", (), None, v)
        get = lambda key: Expression("field", (), key, None)
        # Explicit truth tables, row/column order true, false, unknown.
        expected = {"and": ("satisfied", "violated", "unknown", "violated", "violated", "violated", "unknown", "violated", "unknown"),
                    "or": ("satisfied", "satisfied", "satisfied", "satisfied", "violated", "unknown", "satisfied", "unknown", "unknown"),
                    "implies": ("satisfied", "violated", "unknown", "satisfied", "satisfied", "satisfied", "satisfied", "unknown", "unknown")}
        def run(expr, a, b, nullable=False):
            definition = DomainDefinition("finite-domain/0.1", "logic", "1",
                (EntityType("t", "T", (Field("a", "A", "boolean", False, nullable), Field("b", "B", "boolean", False, False))),),
                (), (Constraint("r", "t", lit(True), expr, lit(False)),), ())
            project = ProjectModel("finite-project/0.1", "p", "1",
                ArtifactRef("engineering", "logic", "1", digest(definition)),
                (Instance("o", "t", (a, b)),), (), True)
            return self.report(project, definition).outcomes[-1].status
        values = (("known", True), ("known", False), ("unknown", None))
        for op, table in expected.items():
            for i, (state_a, a) in enumerate(values):
                for j, (state_b, b) in enumerate(values):
                    self.assertEqual(run(Expression(op, (get("a"), get("b")), None, None),
                                         Slot("a", state_a, a), Slot("b", state_b, b)), table[i * 3 + j])
        null = Slot("a", "null", None)
        known = Slot("b", "known", False)
        bad_comparison = Expression("eq", (get("a"), lit(True)), None, None)
        self.assertEqual(run(Expression("and", (lit(False), bad_comparison), None, None), null, known, True), "error")
        self.assertEqual(run(Expression("is_null", (get("a"),), None, None), null, known, True), "satisfied")
        self.assertEqual(run(Expression("not", (get("b"),), None, None), null, known, True), "satisfied")

    def test_too_deep_response_and_unencodable_project_are_explicit_errors(self):
        candidate = deepcopy(self.candidate)
        expression = candidate["definition"]["constraints"][0]["applies"]
        for _ in range(26):
            expression = dict(op="not", args=[expression], symbol=None, value=None)
        candidate["definition"]["constraints"][0]["applies"] = expression
        with self.assertRaises(ContractError) as caught:
            inspect_typed_candidate(self.request, dumps(candidate).encode())
        self.assertEqual(caught.exception.code, "unsupported")
        with self.assertRaises(ContractError):
            self.report(replace(self.project(), id="\ud800"))

    def test_relationship_projection_rejects_instead_of_dropping_rules(self):
        with self.assertRaises(ContractError) as caught:
            to_scalar_metamodel(self.definition)
        self.assertEqual(caught.exception.code, "unsupported")

    def test_cli_isolated_real_report_and_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name, value in (("request", self.request), ("candidate", self.candidate), ("project", self.project(1))):
                (folder / (name + ".json")).write_text(dumps(value), encoding="utf-8")
            args = [sys.executable, "-B", "-I", str(ROOT / "apps/domain_modeling.py"), "check-project",
                    "--request", str(folder / "request.json"), "--response", str(folder / "candidate.json"),
                    "--project-model", str(folder / "project.json")]
            result = subprocess.run(args, cwd=folder, capture_output=True, text=True, encoding="utf-8", timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertFalse(data["model_committed"])
            self.assertIn("violated", [r["status"] for r in data["report"]["outcomes"]])
            bad = to_data(self.project())
            bad["definition"]["revision"] = "2"
            (folder / "project.json").write_text(dumps(bad), encoding="utf-8")
            result = subprocess.run(args, cwd=folder, capture_output=True, text=True, encoding="utf-8", timeout=20)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stderr)["code"], "conflict")
