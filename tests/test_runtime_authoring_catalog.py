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

        self.assertEqual(catalog["upstreamTag"], "course-authoring-v1.2.0")
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
        self.assertEqual(
            layout["mediaComposition"],
            {
                "pdf": "portrait-column; never stretch into a wide shallow band",
                "video": "wide-region; when paired, the video slot must have the larger split weight",
                "interactiveHtml": "preserve declared 1:1 or 4:3 aspect ratio; scale and center without stretching",
            },
        )

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
