import tempfile
import unittest
from pathlib import Path

from course_toolkit.annotations import (
    AnnotationStore,
    AnnotationTarget,
    CourseAnnotation,
)


NOW = "2026-08-16T00:00:00Z"
HASH = "a" * 64


def annotation(**overrides):
    values = {
        "id": "annotation-copy-1",
        "type": "content",
        "status": "open",
        "required": True,
        "target": AnnotationTarget(
            course_id="evidence-comparability",
            part_id="part-evidence-check",
            slice_id="slice-read-and-answer",
            block_id="claim-text",
        ),
        "definition_hash": HASH,
        "text": "Shorten this sentence.",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return CourseAnnotation(**values)


class AnnotationContractTests(unittest.TestCase):
    def test_round_trip_preserves_authoring_only_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".course-work/annotations.json"
            store = AnnotationStore(path)
            store.add(
                annotation(
                    screenshot_path=".course-work/screenshots/copy.png",
                )
            )
            store.save()

            restored = AnnotationStore.load(path).get("annotation-copy-1")

        self.assertEqual(restored.target.block_id, "claim-text")
        self.assertEqual(
            restored.screenshot_path,
            ".course-work/screenshots/copy.png",
        )
        self.assertIsNone(restored.classification)

    def test_duplicate_annotation_id_is_rejected(self):
        store = AnnotationStore(Path("annotations.json"))
        store.add(annotation())

        with self.assertRaisesRegex(ValueError, "Duplicate annotation"):
            store.add(annotation())

    def test_target_requires_stable_hierarchy(self):
        with self.assertRaisesRegex(ValueError, "courseId"):
            AnnotationTarget(course_id=None)
        with self.assertRaisesRegex(ValueError, "blockId requires sliceId"):
            AnnotationTarget(
                course_id="course-a",
                block_id="block-a",
            )
        with self.assertRaisesRegex(ValueError, "itemId requires blockId"):
            AnnotationTarget(
                course_id="course-a",
                part_id="part-a",
                slice_id="slice-a",
                item_id="item-a",
            )

    def test_unsafe_screenshot_path_is_rejected(self):
        for screenshot in (
            "../shot.png",
            "/tmp/shot.png",
            "screenshots/shot.png",
            ".course-work/screenshots/shot.html",
        ):
            with self.subTest(screenshot=screenshot):
                with self.assertRaisesRegex(ValueError, "screenshotPath"):
                    annotation(screenshot_path=screenshot)

    def test_unknown_annotation_fields_are_rejected(self):
        data = annotation().as_dict()
        data["cssSelector"] = "#claim-text"

        with self.assertRaisesRegex(ValueError, "Unknown annotation field"):
            CourseAnnotation.from_dict(data)

    def test_required_annotation_cannot_be_dismissed_without_decision(self):
        store = AnnotationStore(Path("annotations.json"), [annotation()])

        with self.assertRaisesRegex(ValueError, "teacher decision"):
            store.transition(
                "annotation-copy-1",
                "dismissed",
                NOW,
            )

    def test_applied_and_verified_states_require_distinct_hashes(self):
        proposed = annotation(
            status="proposed",
            classification="mechanical",
            proposed_change="Shorten the copy without changing meaning.",
        )
        store = AnnotationStore(Path("annotations.json"), [proposed])

        applied = store.transition(
            proposed.id,
            "applied",
            NOW,
            applied_blueprint_hash="b" * 64,
        )

        self.assertEqual(applied.status, "applied")
        self.assertIsNone(applied.verified_against_definition_hash)
        verified = store.transition(
            proposed.id,
            "verified",
            NOW,
            verified_against_definition_hash="c" * 64,
        )
        self.assertEqual(verified.verified_against_definition_hash, "c" * 64)

    def test_illegal_status_jump_is_rejected(self):
        store = AnnotationStore(Path("annotations.json"), [annotation()])

        with self.assertRaisesRegex(ValueError, "Illegal annotation transition"):
            store.transition(
                "annotation-copy-1",
                "verified",
                NOW,
                verified_against_definition_hash="c" * 64,
            )


if __name__ == "__main__":
    unittest.main()
