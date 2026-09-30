"""Presentation boundary checks; browser behavior is verified separately."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from modelspine_interaction.review_ui import format_expression, review_page, review_asset


class PresentationTests(unittest.TestCase):
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
        self.assertIn("尚未提供实例查看", page)
        self.assertIn("已记录 ≠ 已修订或已接受", page)

    def test_assets_are_closed_and_no_html_injection_sink(self):
        with self.assertRaises(ValueError):
            review_asset("../../secret")
        script = review_asset("review.js").decode()
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("document.write", script)


if __name__ == "__main__":
    unittest.main()
