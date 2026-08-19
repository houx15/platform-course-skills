import tempfile
import unittest
from pathlib import Path

from course_toolkit.html_validation import (
    validate_interactive_html,
    validate_interactive_html_v2,
)
from tests.helpers import ROOT


VALID_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
html, body { margin: 0; width: 100%; height: 100%; overflow-x: hidden; font-size: 16px; }
button, input, select, textarea { font-size: inherit; }
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

VALID_HTML_V2 = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
html, body { margin: 0; width: 100%; height: 100%; overflow-x: hidden; font-size: 16px; }
button, input, select, textarea { font-size: inherit; }
.canvas { width: 100%; height: 100%; aspect-ratio: 4 / 3; }
</style>
</head>
<body>
<main class="canvas">
  <button id="complete" type="button">完成任务</button>
</main>
<script>
const PROTOCOL = "mind-course-interaction";
const VERSION = "1.0";
const resultId = "evidence-check-attempt-1";
let sessionToken = null;
let selectedAnswer = "source-and-method";
const pendingFrameMessages = [];

function postFrameMessage(type, payload) {
  window.parent.postMessage({
    protocol: PROTOCOL,
    version: VERSION,
    sessionToken,
    type,
    payload
  }, "*");
}

function send(type, payload) {
  if (!sessionToken) {
    pendingFrameMessages.push({ type, payload });
    return;
  }
  postFrameMessage(type, payload);
}

window.addEventListener("message", (event) => {
  const message = event.data;
  if (message.protocol !== PROTOCOL || message.version !== VERSION || !message.sessionToken) return;
  const isNewSession = sessionToken !== message.sessionToken;
  sessionToken = message.sessionToken;
  if (!isNewSession) return;
  postFrameMessage("ready", {});
  while (pendingFrameMessages.length) {
    const pending = pendingFrameMessages.shift();
    postFrameMessage(pending.type, pending.payload);
  }
});

function finish() {
  send("completed", {
    resultId,
    value: { answer: selectedAnswer, attempts: 1 }
  });
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

    def test_missing_font_contract_fails(self):
        text = VALID_HTML.replace("font-size: 16px;", "")
        self.assertIn("missing-font-contract", self.codes(text))

    def test_root_inherit_is_not_a_verifiable_base(self):
        text = VALID_HTML.replace("font-size: 16px;", "font-size: inherit;", 1)
        self.assertIn("unverifiable-font-size", self.codes(text))

    def test_later_body_rule_cannot_reduce_the_base_below_16px(self):
        text = VALID_HTML.replace(
            "</style>",
            "body { font-size: 15px; }\n</style>",
        )
        self.assertIn("base-font-too-small", self.codes(text))

    def test_final_duplicate_root_declaration_controls_the_result(self):
        text = VALID_HTML.replace(
            "font-size: 16px;",
            "font-size: 16px; font-size: 12px;",
            1,
        )
        self.assertIn("base-font-too-small", self.codes(text))

    def test_body_rem_resolves_against_explicit_html_root(self):
        text = VALID_HTML.replace(
            "html, body { margin: 0; width: 100%; height: 100%; overflow-x: hidden; font-size: 16px; }",
            "html { font-size: 20px; } body { margin: 0; width: 100%; height: 100%; overflow-x: hidden; font-size: 0.8rem; }",
        )
        self.assertNotIn("base-font-too-small", self.codes(text))

    def test_content_rem_uses_html_root_not_body_size(self):
        text = VALID_HTML.replace(
            "html, body { margin: 0; width: 100%; height: 100%; overflow-x: hidden; font-size: 16px; }",
            "html { font-size: 20px; } body { margin: 0; width: 100%; height: 100%; overflow-x: hidden; font-size: 16px; }",
        ).replace(
            "</style>",
            ".title { font-size: 0.8rem; }\n</style>",
        )
        self.assertNotIn("content-font-too-small", self.codes(text))

    def test_auxiliary_text_may_be_14px_but_not_13px(self):
        at_14 = VALID_HTML.replace(
            "</style>",
            ".auxiliary { font-size: 14px; }\n</style>",
        )
        at_13 = at_14.replace("14px", "13px")
        self.assertNotIn("auxiliary-font-too-small", self.codes(at_14))
        self.assertIn("auxiliary-font-too-small", self.codes(at_13))

    def test_unmarked_text_and_controls_must_be_16px(self):
        unmarked = VALID_HTML.replace(
            "</style>",
            ".caption { font-size: 15px; }\n</style>",
        )
        control = VALID_HTML.replace(
            "font-size: inherit;",
            "font-size: 15px;",
        )
        self.assertIn("unmarked-small-text", self.codes(unmarked))
        self.assertIn("control-font-too-small", self.codes(control))

    def test_later_identical_content_rule_replaces_earlier_rule(self):
        text = VALID_HTML.replace(
            "</style>",
            ".caption { font-size: 12px; } .caption { font-size: 16px; }\n</style>",
        )
        codes = self.codes(text)
        self.assertNotIn("content-font-too-small", codes)
        self.assertNotIn("unmarked-small-text", codes)

    def test_rem_and_safe_clamp_are_resolved(self):
        text = VALID_HTML.replace(
            "</style>",
            ".title { font-size: 1rem; }\n"
            ".auxiliary { font-size: clamp(14px, 2vw, 18px); }\n</style>",
        )
        codes = self.codes(text)
        self.assertNotIn("unverifiable-font-size", codes)
        self.assertNotIn("unmarked-small-text", codes)

    def test_unverifiable_units_and_unsafe_clamp_fail(self):
        viewport = VALID_HTML.replace(
            "</style>",
            ".caption { font-size: 2vw; }\n</style>",
        )
        unsafe_clamp = VALID_HTML.replace(
            "</style>",
            ".caption { font-size: clamp(12px, 2vw, 20px); }\n</style>",
        )
        self.assertIn("unverifiable-font-size", self.codes(viewport))
        self.assertIn("content-font-too-small", self.codes(unsafe_clamp))

    def test_inline_font_sizes_follow_the_same_contract(self):
        unmarked = VALID_HTML.replace(
            '<main class="canvas">',
            '<main class="canvas"><p style="font-size: 15px">说明</p>',
        )
        auxiliary = VALID_HTML.replace(
            '<main class="canvas">',
            '<main class="canvas"><p class="auxiliary" style="font-size: 13px">说明</p>',
        )
        self.assertIn("unmarked-small-text", self.codes(unmarked))
        self.assertIn("auxiliary-font-too-small", self.codes(auxiliary))

    def test_auxiliary_marker_does_not_exempt_a_control(self):
        text = VALID_HTML.replace(
            "button, input, select, textarea { font-size: inherit; }",
            ".auxiliary { font-size: 14px; }",
        ).replace(
            'id="complete"',
            'id="complete" class="auxiliary"',
        )
        self.assertIn("control-font-too-small", self.codes(text))

    def test_control_without_verifiable_font_rule_fails(self):
        text = VALID_HTML.replace(
            "button, input, select, textarea { font-size: inherit; }",
            "",
        )
        self.assertIn("unverifiable-font-size", self.codes(text))

    def test_descendant_rule_does_not_size_the_control(self):
        text = VALID_HTML.replace(
            "button, input, select, textarea { font-size: inherit; }",
            "button span { font-size: inherit; }",
        )
        self.assertIn("unverifiable-font-size", self.codes(text))

    def test_final_duplicate_control_declaration_controls_the_result(self):
        text = VALID_HTML.replace(
            "font-size: inherit;",
            "font-size: 16px; font-size: 12px;",
        )
        self.assertIn("control-font-too-small", self.codes(text))

    def test_important_control_declaration_beats_later_normal_value(self):
        text = VALID_HTML.replace(
            "font-size: inherit;",
            "font-size: 12px !important; font-size: 16px;",
        )
        self.assertIn("control-font-too-small", self.codes(text))

    def test_later_identical_control_rule_replaces_earlier_rule(self):
        text = VALID_HTML.replace(
            "button, input, select, textarea { font-size: inherit; }",
            "button { font-size: 12px; } button { font-size: 16px; }",
        )
        codes = self.codes(text)
        self.assertNotIn("control-font-too-small", codes)
        self.assertNotIn("unverifiable-font-size", codes)

    def test_svg_text_presentation_attribute_is_checked(self):
        text = VALID_HTML.replace(
            '<main class="canvas">',
            '<main class="canvas"><svg><text font-size="10px">小字</text></svg>',
        )
        self.assertIn("content-font-too-small", self.codes(text))

    def test_unquoted_auxiliary_attribute_selector_is_supported(self):
        text = VALID_HTML.replace(
            "</style>",
            "[data-text-role=auxiliary] { font-size: 14px; }\n</style>",
        )
        self.assertNotIn("unmarked-small-text", self.codes(text))

    def test_auxiliary_class_prefix_does_not_receive_the_exception(self):
        for class_name in ("auxiliary-note", "auxiliary2"):
            with self.subTest(class_name=class_name):
                text = VALID_HTML.replace(
                    "</style>",
                    f".{class_name} {{ font-size: 15px; }}\n</style>",
                )
                self.assertIn("unmarked-small-text", self.codes(text))


class HtmlV2ValidationTests(unittest.TestCase):
    def validate_text(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "interaction.html"
            path.write_text(text, encoding="utf-8")
            return validate_interactive_html_v2(path)

    def codes(self, text):
        return {issue.code for issue in self.validate_text(text)}

    def test_valid_renderer_handshake_and_completion_evidence_pass(self):
        self.assertEqual(self.validate_text(VALID_HTML_V2), [])

    def test_legacy_completion_message_is_not_v2_compatible(self):
        codes = self.codes(VALID_HTML)
        self.assertIn("missing-host-handshake", codes)
        self.assertIn("invalid-frame-message-contract", codes)

    def test_session_token_must_be_received_and_echoed(self):
        text = VALID_HTML_V2.replace(
            "sessionToken = message.sessionToken;",
            "// token was not accepted",
        )
        self.assertIn("missing-session-token-echo", self.codes(text))

    def test_silently_dropping_messages_before_handshake_is_rejected(self):
        text = VALID_HTML_V2.replace(
            "if (!sessionToken) {\n    pendingFrameMessages.push({ type, payload });\n    return;\n  }",
            "if (!sessionToken) return;",
        )

        self.assertIn("missing-pre-handshake-queue", self.codes(text))

    def test_completed_payload_accepts_optional_result_id_but_requires_learning_evidence(self):
        no_result_id = VALID_HTML_V2.replace("    resultId,\n", "")
        no_evidence = VALID_HTML_V2.replace("value: { answer: selectedAnswer, attempts: 1 }", "status: 'done'")

        self.assertNotIn("missing-completion-evidence", self.codes(no_result_id))
        self.assertIn("missing-completion-evidence", self.codes(no_evidence))

    def test_completed_payload_accepts_correct_as_the_only_evidence(self):
        correct_only = VALID_HTML_V2.replace(
            "value: { answer: selectedAnswer, attempts: 1 }",
            "correct: true",
        )

        self.assertNotIn("missing-completion-evidence", self.codes(correct_only))

    def test_network_and_host_storage_apis_are_prohibited(self):
        snippets = (
            "fetch('/track')",
            "new XMLHttpRequest()",
            "new WebSocket('wss://example.test')",
            "localStorage.setItem('x', 'y')",
            "document.cookie = 'x=y'",
            "window.parent.document.body",
        )
        for snippet in snippets:
            with self.subTest(snippet=snippet):
                text = VALID_HTML_V2.replace("function finish() {", f"{snippet};\nfunction finish() {{")
                self.assertIn("prohibited-html-api", self.codes(text))

    def test_v2_preserves_common_self_containment_and_typography_checks(self):
        external = VALID_HTML_V2.replace(
            "</head>",
            '<script src="https://example.com/app.js"></script></head>',
        )
        small = VALID_HTML_V2.replace("font-size: 16px;", "font-size: 12px;", 1)

        self.assertIn("external-resource", self.codes(external))
        self.assertIn("base-font-too-small", self.codes(small))


if __name__ == "__main__":
    unittest.main()
