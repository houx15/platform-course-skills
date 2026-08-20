import copy
import tempfile
import unittest
from pathlib import Path

from course_toolkit.course_compiler import canonical_json_hash
from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.preview_evidence import (
    PreviewEvidenceError,
    record_preview_evidence,
    verify_g7_preview,
)
from tests.helpers import ROOT


NOW = "2026-08-17T13:00:00Z"


class PreviewEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        document = load_json(ROOT / "packages/course-contract/test/fixtures/coverage-course.json")
        write_json_atomic(self.root / "course/course.json", document)
        self.slice_ids = [
            slice_data["id"]
            for part in document["course"]["parts"]
            for slice_data in part["slices"]
        ]
        self.client = {
            "viewport": {"width": 1440, "height": 900},
            "visitedSliceIds": self.slice_ids,
            "exercisedEvents": [
                {
                    "id": "event-preview-1",
                    "type": "student.continue",
                    "sourceId": "course-nav",
                    "sliceId": self.slice_ids[0],
                }
            ],
            "runtimeErrors": [],
            "teacherConfirmed": True,
            "completedAt": NOW,
        }

    def tearDown(self):
        self.temporary.cleanup()

    def test_records_hash_bound_renderer_evidence_for_every_slice(self):
        manifest = record_preview_evidence(self.root, self.client)

        self.assertEqual(manifest["schemaVersion"], "1.0")
        self.assertEqual(manifest["renderer"]["upstreamTag"], "course-authoring-v1.5.2")
        self.assertEqual(manifest["visitedSliceIds"], self.slice_ids)
        evidence = verify_g7_preview(self.root)
        self.assertIn(".course-work/preview-manifest.json", evidence)
        self.assertIn("@toolkit/course-preview-bundle", evidence)

    def test_rejects_missing_visited_slice(self):
        client = {**self.client, "visitedSliceIds": []}
        with self.assertRaisesRegex(PreviewEvidenceError, "not reviewed"):
            record_preview_evidence(self.root, client)

    def test_rejects_open_required_annotation(self):
        annotation = {
            "id": "annotation-open-one",
            "type": "content",
            "status": "open",
            "required": True,
            "target": {
                "courseId": "evidence-comparability",
                "partId": "part-check-comparability",
                "sliceId": self.slice_ids[0],
                "blockId": None,
                "itemId": None,
                "workflowStepId": None,
            },
            "definitionHash": "a" * 64,
            "text": "Revise this before approval.",
            "screenshotPath": None,
            "createdAt": NOW,
            "updatedAt": NOW,
            "classification": None,
            "proposedChange": None,
            "resolutionDecisionId": None,
            "appliedBlueprintHash": None,
            "verifiedAgainstDefinitionHash": None,
            "orphanReason": None,
            "reboundFromDefinitionHash": None,
        }
        write_json_atomic(
            self.root / ".course-work/annotations.json",
            {"schemaVersion": "1.0", "annotations": [annotation]},
        )
        with self.assertRaisesRegex(PreviewEvidenceError, "required annotation"):
            record_preview_evidence(self.root, self.client)

    def test_verifies_an_applied_annotation_against_the_rebuilt_definition(self):
        blueprint = {"course": {"id": "evidence-comparability", "parts": []}}
        write_json_atomic(self.root / ".course-work/course-blueprint.json", blueprint)
        annotation = {
            "id": "annotation-applied-one",
            "type": "layout",
            "status": "applied",
            "required": True,
            "target": {
                "courseId": "evidence-comparability",
                "partId": "part-check-comparability",
                "sliceId": self.slice_ids[0],
                "blockId": None,
                "itemId": None,
                "workflowStepId": None,
            },
            "definitionHash": "a" * 64,
            "text": "Make the video dominant.",
            "screenshotPath": None,
            "createdAt": NOW,
            "updatedAt": NOW,
            "classification": "semantic",
            "proposedChange": "Use a 1:2 split layout.",
            "resolutionDecisionId": "decision-layout-one",
            "appliedBlueprintHash": canonical_json_hash(blueprint),
            "verifiedAgainstDefinitionHash": None,
            "orphanReason": None,
            "reboundFromDefinitionHash": None,
        }
        write_json_atomic(
            self.root / ".course-work/annotations.json",
            {"schemaVersion": "1.0", "annotations": [annotation]},
        )

        manifest = record_preview_evidence(self.root, self.client)

        stored = load_json(self.root / ".course-work/annotations.json")["annotations"][0]
        self.assertEqual(stored["status"], "verified")
        self.assertEqual(stored["verifiedAgainstDefinitionHash"], manifest["definitionHash"])

    def test_rejects_runtime_error(self):
        client = {**self.client, "runtimeErrors": ["iframe completion protocol failed"]}
        with self.assertRaisesRegex(PreviewEvidenceError, "runtime error"):
            record_preview_evidence(self.root, client)

    def test_verifier_rejects_wrong_definition_hash_and_renderer_tag(self):
        manifest = record_preview_evidence(self.root, self.client)
        for field, value, message in (
            ("definitionHash", "0" * 64, "definition hash"),
            ("renderer.upstreamTag", "wrong-tag", "renderer tag"),
        ):
            changed = copy.deepcopy(manifest)
            if field == "definitionHash":
                changed[field] = value
            else:
                changed["renderer"]["upstreamTag"] = value
            write_json_atomic(self.root / ".course-work/preview-manifest.json", changed)
            with self.subTest(field=field), self.assertRaisesRegex(PreviewEvidenceError, message):
                verify_g7_preview(self.root)
            write_json_atomic(self.root / ".course-work/preview-manifest.json", manifest)


if __name__ == "__main__":
    unittest.main()
