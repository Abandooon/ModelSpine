import unittest
from modelspine_generation.local_web import LocalWebPlan, render


class LocalPageTests(unittest.TestCase):
    def test_untrusted_view_label_is_text_and_integer_project_never_json_parsed(self):
        spec={"views":[{"id":"\" onfocus=alert(1)","title":"<script>alert(1)</script>"}]}
        files=render(LocalWebPlan(spec,{}, {},None,{},"input"))
        self.assertNotIn(b"<script>alert(1)</script>",files["index.html"])
        self.assertIn(b"&lt;script&gt;",files["index.html"])
        self.assertNotIn(b"JSON.parse",files["client.js"])
