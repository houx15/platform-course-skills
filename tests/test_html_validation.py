import tempfile
import unittest
from pathlib import Path

from course_toolkit.html_validation import validate_interactive_html
from tests.helpers import ROOT


VALID_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
html, body { margin: 0; width: 100%; height: 100%; overflow-x: hidden; }
.canvas { width: 100%; height: 100%; aspect-ratio: 4 / 3; }
</style>
</head>
<body>
<main class="canvas">
  <button id="complete" type="button">完成任务</button>
</main>
<script>
const interactions = [{ interactionId: "choice", type: "choice", answer: "a" }];
function finish() {
  window.parent.postMessage({
    type: "INTERACTION_COMPLETE",
    version: "1.0",
    payload: { lessonId: "lesson-1", duration: 12, interactions }
  }, "*");
}
document.getElementById("complete").addEventListener("click", finish);
</script>
</body>
</html>
"""


class HtmlValidationTests(unittest.TestCase):
    def validate_text(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "interaction.html"
            path.write_text(text, encoding="utf-8")
            return validate_interactive_html(path)

    def codes(self, text):
        return {issue.code for issue in self.validate_text(text)}

    def test_valid_html_passes(self):
        self.assertEqual(self.validate_text(VALID_HTML), [])

    def test_missing_completion_button_fails(self):
        text = VALID_HTML.replace("完成任务", "提交")
        self.assertIn("missing-complete-button", self.codes(text))

    def test_missing_message_contract_fails(self):
        text = VALID_HTML.replace("INTERACTION_COMPLETE", "DONE")
        self.assertIn("invalid-message-contract", self.codes(text))

    def test_external_resources_fail(self):
        text = VALID_HTML.replace(
            "</head>",
            '<script src="https://example.com/app.js"></script></head>',
        )
        self.assertIn("external-resource", self.codes(text))

    def test_missing_canvas_fails(self):
        text = VALID_HTML.replace("aspect-ratio: 4 / 3;", "")
        self.assertIn("missing-canvas", self.codes(text))

    def test_sample_fails_standardized_button_label(self):
        codes = {
            issue.code
            for issue in validate_interactive_html(
                ROOT / "tests" / "fixtures" / "legacy-html-wrong-button.html"
            )
        }
        self.assertIn("missing-complete-button", codes)


if __name__ == "__main__":
    unittest.main()
