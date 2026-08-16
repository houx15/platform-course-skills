import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from course_toolkit.blueprint import project_course_definition
from course_toolkit.legacy_course_import import LegacyImportError, import_legacy_course
from course_toolkit.jsonio import dump_json
from tests.helpers import ROOT


FIXTURES = ROOT / "tests" / "fixtures" / "course-blueprint"
LEGACY = FIXTURES / "legacy-course.json"
STORYBOARD = FIXTURES / "legacy-storyboard.json"
SCRIPT = ROOT / "scripts" / "import-legacy-course.py"


def legacy_course():
    return json.loads(LEGACY.read_text(encoding="utf-8"))


def legacy_storyboard():
    return json.loads(STORYBOARD.read_text(encoding="utf-8"))


class LegacyCourseImportTests(unittest.TestCase):
    def imported(self):
        return import_legacy_course(legacy_course(), legacy_storyboard())

    def blocks(self, blueprint):
        return blueprint["course"]["parts"][0]["slices"][0]["blocks"]

    def block(self, blueprint, block_id):
        return next(block for block in self.blocks(blueprint) if block["id"] == block_id)

    def test_piece_becomes_slice_with_stable_id(self):
        blueprint = self.imported()
        part = blueprint["course"]["parts"][0]

        self.assertEqual(part["id"], "part-source-check")
        self.assertEqual(part["slices"][0]["id"], "piece-source-check")
        self.assertEqual(part["objectiveIds"], ["check-source"])
        self.assertEqual(part["slices"][0]["objectiveIds"], ["check-source"])

    def test_all_legacy_blocks_convert_to_closed_two_shapes(self):
        blueprint = self.imported()

        self.assertEqual(
            {block["type"] for block in self.blocks(blueprint)},
            {"text", "images", "pdf", "video", "interactiveHtml", "fillBlank", "singleChoice"},
        )
        for block in self.blocks(blueprint):
            self.assertNotIn("blocking", block)

    def test_image_items_gain_deterministic_ids_and_presentation(self):
        images = self.block(self.imported(), "legacy-images")

        self.assertEqual(images["presentation"], "side-by-side")
        self.assertEqual(
            [item["id"] for item in images["items"]],
            ["legacy-images-item-1", "legacy-images-item-2"],
        )

    def test_html_and_video_runtime_references_are_explicit(self):
        blueprint = self.imported()
        html = self.block(blueprint, "legacy-html")
        video = self.block(blueprint, "legacy-video")

        self.assertEqual(html["protocolVersion"], "1.0")
        self.assertEqual(html["aspectRatio"], "4:3")
        self.assertEqual(video["interaction"], {"source": "interactions/video/case.json"})
        self.assertNotIn("case.md", dump_json(blueprint["course"]))

    def test_completion_rules_are_strict_two_rules(self):
        blueprint = self.imported()
        reflection = self.block(blueprint, "legacy-reflection")
        question = self.block(blueprint, "legacy-question")

        self.assertEqual(reflection["completion"], {"rule": "submit-any"})
        self.assertEqual(
            question["completion"],
            {"rule": "submit-correct-or-exhausted", "maxAttempts": 3},
        )

    def test_storyboard_alignment_supplies_objective_evidence(self):
        blueprint = self.imported()
        objective = blueprint["course"]["objectives"][0]

        self.assertEqual(
            objective["evidenceBlockIds"],
            ["legacy-question", "legacy-reflection"],
        )

    def test_missing_objective_alignment_blocks_import(self):
        storyboard = legacy_storyboard()
        storyboard["courseFrame"]["objectiveAlignment"] = []

        with self.assertRaisesRegex(LegacyImportError, "objectiveAlignment"):
            import_legacy_course(legacy_course(), storyboard)

    def test_migration_assumptions_require_new_teacher_confirmation(self):
        blueprint = self.imported()

        self.assertFalse(blueprint["approval"]["teacherConfirmed"])
        self.assertEqual(blueprint["approval"]["decisionIds"], [])
        assumption_ids = {
            assumption["id"] for assumption in blueprint["migration"]["assumptions"]
        }
        self.assertTrue(
            {
                "layout-default",
                "workflow-from-blocking",
                "estimated-time",
                "personalization-disabled",
                "objective-slice-mapping",
                "video-authoring-document-omitted",
            }.issubset(assumption_ids)
        )

    def test_workflow_gates_blocking_elements_in_source_order(self):
        workflow = self.imported()["course"]["parts"][0]["slices"][0]["workflow"]

        self.assertEqual(workflow["initialStepId"], "wait-legacy-video")
        self.assertEqual(
            [step["id"] for step in workflow["steps"]],
            [
                "wait-legacy-video",
                "wait-legacy-html",
                "wait-legacy-reflection",
                "wait-legacy-question",
                "finish",
            ],
        )
        self.assertEqual(
            workflow["steps"][1]["transitions"][0]["on"]["type"],
            "interaction.completed",
        )

    def test_identical_inputs_produce_byte_identical_blueprints(self):
        first = import_legacy_course(legacy_course(), legacy_storyboard())
        second = import_legacy_course(legacy_course(), legacy_storyboard())

        self.assertEqual(dump_json(first), dump_json(second))

    def test_confirmed_import_projects_to_shared_contract_valid_course(self):
        blueprint = self.imported()
        blueprint["approval"] = {
            "teacherConfirmed": True,
            "decisionIds": ["decision-confirm-migration"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "course.json"
            input_path.write_text(
                json.dumps(project_course_definition(blueprint)),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "node",
                    "--import",
                    "tsx",
                    "scripts/validate-course-definition.ts",
                    str(input_path),
                    "--json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


class LegacyImportCliTests(unittest.TestCase):
    def run_cli(self, output, *extra):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(LEGACY),
                str(STORYBOARD),
                str(output),
                *extra,
                "--json",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_cli_writes_unconfirmed_blueprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / ".course-work" / "course-blueprint.json"

            result = self.run_cli(output)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(output.read_text())["approval"]["teacherConfirmed"])

    def test_cli_never_overwrites_confirmed_blueprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "course-blueprint.json"
            existing = import_legacy_course(legacy_course(), legacy_storyboard())
            existing["approval"] = {
                "teacherConfirmed": True,
                "decisionIds": ["decision-approved"],
            }
            output.write_text(json.dumps(existing), encoding="utf-8")

            result = self.run_cli(output, "--replace-unconfirmed")

            self.assertEqual(result.returncode, 2)
            self.assertTrue(json.loads(output.read_text())["approval"]["teacherConfirmed"])


if __name__ == "__main__":
    unittest.main()
