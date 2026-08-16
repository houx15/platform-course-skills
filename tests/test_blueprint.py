import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from course_toolkit.blueprint import (
    index_blueprint_targets,
    project_course_definition,
    validate_blueprint_authoring,
)
from tests.helpers import ROOT


FIXTURE = (
    ROOT
    / "tests"
    / "fixtures"
    / "course-blueprint"
    / "approved-blueprint.json"
)


def approved_blueprint():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class BlueprintTests(unittest.TestCase):
    def codes(self, data, *, require_approval=True):
        return {
            issue.code
            for issue in validate_blueprint_authoring(
                data,
                require_approval=require_approval,
            )
        }

    def test_approved_blueprint_is_authoring_valid(self):
        self.assertEqual(validate_blueprint_authoring(approved_blueprint()), [])

    def test_target_index_covers_all_stable_runtime_entities(self):
        targets = index_blueprint_targets(approved_blueprint())

        self.assertEqual(targets["course"], "/course")
        self.assertEqual(
            targets["block:evidence-question"],
            "/course/parts/0/slices/0/blocks/1",
        )
        self.assertEqual(
            targets["slice:slice-read-and-answer/narration:introduce-check"],
            "/course/parts/0/slices/0/narrations/0",
        )
        self.assertEqual(
            targets["slice:slice-read-and-answer/workflow-step:finish"],
            "/course/parts/0/slices/0/workflow/steps/2",
        )

    def test_unknown_top_level_field_is_rejected(self):
        data = approved_blueprint()
        data["teacherNotes"] = "leak"

        self.assertIn("unknown-field", self.codes(data))

    def test_unknown_approval_field_is_rejected(self):
        data = approved_blueprint()
        data["approval"]["approvedByAI"] = True

        self.assertIn("unknown-field", self.codes(data))

    def test_unconfirmed_blueprint_requires_teacher_decision(self):
        data = approved_blueprint()
        data["approval"] = {"teacherConfirmed": False, "decisionIds": []}

        self.assertIn("blueprint-unconfirmed", self.codes(data))
        self.assertNotIn(
            "blueprint-unconfirmed",
            self.codes(data, require_approval=False),
        )

    def test_confirmed_blueprint_requires_decision_identity(self):
        data = approved_blueprint()
        data["approval"]["decisionIds"] = []

        self.assertIn("missing-decision", self.codes(data))

    def test_target_contract_must_be_two(self):
        data = approved_blueprint()
        data["targetContractVersion"] = "1.1"

        self.assertIn("invalid-version", self.codes(data))

    def test_duplicate_provenance_target_is_rejected(self):
        data = approved_blueprint()
        data["provenance"].append(copy.deepcopy(data["provenance"][0]))

        self.assertIn("duplicate-provenance", self.codes(data))

    def test_malformed_provenance_target_is_rejected(self):
        data = approved_blueprint()
        data["provenance"][0]["targetId"] = "block/not-valid"

        self.assertIn("invalid-target", self.codes(data))

    def test_provenance_target_must_exist(self):
        data = approved_blueprint()
        data["provenance"][0]["targetId"] = "block:missing"

        self.assertIn("unknown-target", self.codes(data))

    def test_duplicate_runtime_target_is_rejected(self):
        data = approved_blueprint()
        duplicate = copy.deepcopy(
            data["course"]["parts"][0]["slices"][0]["blocks"][0]
        )
        data["course"]["parts"][0]["slices"][0]["blocks"].append(duplicate)

        self.assertIn("duplicate-target", self.codes(data))

    def test_projection_contains_only_runtime_document(self):
        data = approved_blueprint()

        projected = project_course_definition(data)

        self.assertEqual(projected["schemaVersion"], "2.0")
        self.assertEqual(projected["course"], data["course"])
        self.assertNotIn("approval", projected)
        self.assertNotIn("provenance", projected)

    def test_projected_fixture_passes_shared_student_contract(self):
        projected = project_course_definition(approved_blueprint())
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "course.json"
            input_path.write_text(json.dumps(projected), encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
