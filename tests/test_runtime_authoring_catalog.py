import json
import subprocess
import unittest

from tests.helpers import ROOT


CATALOG = ROOT / "course_toolkit" / "runtime_authoring_catalog.json"
CHECKER = ROOT / "scripts" / "check-runtime-authoring-catalog.ts"


class RuntimeAuthoringCatalogTests(unittest.TestCase):
    def load_catalog(self):
        return json.loads(CATALOG.read_text(encoding="utf-8"))

    def test_catalog_covers_every_closed_runtime_choice(self):
        catalog = self.load_catalog()

        self.assertEqual(catalog["upstreamTag"], "course-authoring-v1.8.0")
        self.assertEqual(
            catalog["layout"]["presets"],
            ["full", "split-horizontal", "split-vertical", "grid"],
        )
        self.assertEqual(
            catalog["layout"]["splitRatios"],
            ["1:1", "3:2", "2:3", "2:1", "1:2", "3:1", "1:3"],
        )
        self.assertEqual(
            catalog["blocks"]["types"],
            [
                "text",
                "richText",
                "images",
                "pdf",
                "video",
                "interactiveHtml",
                "fillBlank",
                "singleChoice",
            ],
        )
        self.assertEqual(len(catalog["workflow"]["actions"]), 16)
        self.assertEqual(len(catalog["workflow"]["events"]), 16)
        self.assertEqual(
            catalog["workflow"]["matcherFields"],
            ["type", "sourceId", "interactionId", "timerId"],
        )
        self.assertEqual(
            catalog["navigation"]["manualNext"],
            ["after-completion", "allowed"],
        )

    def test_catalog_covers_html_audio_and_message_protocol(self):
        html = self.load_catalog()["blocks"]["interactiveHtml"]

        self.assertEqual(html["capabilities"], {"audio": "boolean-optional"})
        self.assertEqual(
            html["frameMessageTypes"],
            ["ready", "progress", "completed", "error"],
        )
        self.assertEqual(
            html["hostMessageTypes"],
            [
                "activate",
                "deactivate",
                "enable",
                "disable",
                "pauseMedia",
                "resumeMedia",
                "stopMedia",
            ],
        )
        self.assertEqual(
            html["completedPayload"]["atLeastOneOf"],
            ["correct", "value"],
        )

    def test_catalog_exposes_media_aware_authoring_policy(self):
        layout = self.load_catalog()["layout"]

        self.assertIn("do-not-author-split-vertical-by-default", layout["authoringRules"])
        self.assertIn("full-layout-has-one-block", layout["authoringRules"])
        self.assertIn("split-horizontal-defaults-to-1:1", layout["authoringRules"])
        self.assertIn("asymmetric-only-for-dominant-video-with-short-supporting-text", layout["authoringRules"])
        self.assertIn("answerable-block-prefers-right-slot", layout["authoringRules"])
        self.assertIn("reference-and-answer-prefer-same-slice", layout["authoringRules"])
        self.assertIn("grid-supports-two-to-four-cells", layout["authoringRules"])
        self.assertIn("split-slots-must-be-non-empty", layout["authoringRules"])
        self.assertEqual(
            layout["mediaComposition"],
            {
                "pdf": "portrait page centred within an equal 1:1 slot; never stretch into a wide shallow band",
                "video": "full or equal 1:1 by default; only a dominant large video with short supporting text may own the larger split weight",
                "interactiveHtml": "the host gives the iframe the complete slot; aspectRatio is only a design hint, use fill when no preferred shape exists, and the document must remain usable at 1280x720 and 1200x520 without imposing a clipped inner frame",
                "richText": "static structured reading card for course maps, method position, worked examples, comparisons, and synthesis; use full or a tall horizontal-split side and split long reading across slices",
            },
        )

    def test_catalog_exposes_modal_blocks_and_full_slot_html(self):
        catalog = self.load_catalog()

        self.assertEqual(catalog["blocks"]["openAs"]["values"], ["inline", "modal"])
        self.assertIn("openAs", catalog["blocks"]["pdf"]["optionalFields"])
        self.assertIn("modalLabel", catalog["blocks"]["interactiveHtml"]["optionalFields"])
        self.assertEqual(
            catalog["blocks"]["interactiveHtml"]["aspectRatios"],
            ["1:1", "4:3", "fill"],
        )
        self.assertEqual(
            catalog["blocks"]["interactiveHtml"]["visualChecks"],
            ["1280x720", "1200x520", "modal-open"],
        )

    def test_catalog_exposes_safe_display_only_rich_text(self):
        rich_text = self.load_catalog()["blocks"]["richText"]

        self.assertEqual(rich_text["requiredFields"], ["id", "type", "html"])
        self.assertEqual(rich_text["optionalFields"], ["title", "openAs", "modalLabel"])
        self.assertTrue(rich_text["displayOnly"])
        self.assertEqual(rich_text["maxHtmlChars"], 65536)
        self.assertIn("at least two meaningful styled teaching regions", rich_text["authoringRule"])
        self.assertEqual(
            rich_text["recommendedRegions"],
            ["numbered-method-sequence", "current-step", "worked-example", "comparison", "hint-or-callout", "knowledge-diagram"],
        )

    def test_catalog_explains_when_images_should_use_gallery(self):
        images = self.load_catalog()["blocks"]["images"]

        self.assertIn("exactly two images", images["authoringRule"])
        self.assertIn("portrait/tall images", images["authoringRule"])
        self.assertIn("use gallery", images["authoringRule"])

    def test_catalog_marks_events_without_a_real_renderer_producer(self):
        catalog = self.load_catalog()

        self.assertEqual(
            catalog["rendererCaveats"]["workflowEventsWithoutProducer"],
            ["pdf.pageChanged"],
        )
        self.assertEqual(
            catalog["rendererCaveats"]["authoringPolicy"],
            "do-not-generate-transition",
        )

    def test_typescript_checker_proves_catalog_parity(self):
        result = subprocess.run(
            ["node", "--import", "tsx", str(CHECKER)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
