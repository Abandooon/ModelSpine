"""Presentation boundary checks; browser behavior is verified separately."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from modelspine_interaction.review_ui import format_expression, project_instance, project_report, review_page, review_asset, spec_template


class PresentationTests(unittest.TestCase):
    def test_application_template_does_not_invent_configuration(self):
        import json
        ref={"project_id":"engineering","artifact_id":"ref","revision":"1","content_hash":"0"*64}
        view={k:ref for k in ("request_ref","source_ref","definition_ref","candidate_ref","review_ref")}
        view["project_id"]="engineering"
        draft=json.loads(spec_template(view))
        self.assertEqual(draft["review_ref"],ref)
        self.assertIsNone(draft["storage"])
        self.assertIsNone(draft["access"])
        self.assertEqual(draft["tasks"],[])
        self.assertIsNone(spec_template({**view,"definition_ref":None}))

    def test_instance_exact_integer_unknown_and_report_statuses(self):
        model = {"schema_version":"finite-project/0.1", "id":"hand_authored_engineering_only", "version":"1",
                 "definition":{"project_id":"fixture", "artifact_id":"d", "revision":"1", "content_hash":"0" * 64},
                 "objects":[{"id":"<script>object</script>", "entity":"sensor", "slots":[
                     {"field":"max", "state":"known", "value":9223372036854775807},
                     {"field":"min", "state":"known", "value":-9223372036854775808},
                     {"field":"missing", "state":"unknown", "value":None}]}], "links":[], "population_complete":False}
        projected = project_instance(model)[0]
        self.assertEqual(projected["rows"][0][-1], "9223372036854775807")
        self.assertEqual(projected["rows"][1][-1], "-9223372036854775808")
        self.assertEqual(projected["rows"][2][-2:], ["unknown", "null"])
        states = ["satisfied", "violated", "unknown", "error", "not_applicable"]
        report = {"checker":"engineering-only", "requirement_fidelity":"not_checked", "definition_hash":"d", "project_hash":"p",
                  "outcomes":[{"obligation":"r", "target":"o", "status":s, "reason":"<img src=x>"} for s in states]}
        self.assertEqual([r[2] for r in project_report(report)["rows"]], states)

    def test_expression_keeps_parentheses_and_exact_int64(self):
        lit = lambda n: {"op":"literal", "value":n, "symbol":None, "args":[]}
        expr = {"op":"and", "args":[lit(True), {"op":"or", "args":[lit(False),lit(True)]}]}
        self.assertEqual(format_expression(expr), "(true AND (false OR true))")
        self.assertEqual(format_expression(lit(9223372036854775807)), "9223372036854775807")
        self.assertEqual(format_expression({"op":"count", "symbol":"linked:in", "args":[]}), 'count("linked:in")')

    def test_shell_escapes_attribute_and_exposes_limits(self):
        page = review_page('\"><script>alert(1)</script>')
        self.assertNotIn('<script>alert(1)', page)
        self.assertIn('&quot;&gt;&lt;script&gt;', page)
        self.assertIn("可离线保存和检查实例", page)
        self.assertIn("记录意见不会改变候选", page)

    def test_assets_are_closed_and_no_html_injection_sink(self):
        with self.assertRaises(ValueError):
            review_asset("../../secret")
        script = review_asset("review.js").decode()
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("document.write", script)


if __name__ == "__main__":
    unittest.main()
