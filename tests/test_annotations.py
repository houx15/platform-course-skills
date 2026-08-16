import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from course_toolkit.annotations import (
    AnnotationStore,
    AnnotationTarget,
    CourseAnnotation,
    reconcile_annotations,
    resolve_annotation_target,
)
from course_toolkit.course_compiler import canonical_json_hash
from course_toolkit.course_compiler import compile_blueprint, write_compilation_outputs_atomic
from course_toolkit.issues import IssueStore
from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.workflow import load_session, new_session, save_session
from tests.helpers import ROOT
from tests.test_course_package_validation import build_full_package, build_minimal_package


NOW = "2026-08-16T00:00:00Z"
HASH = "a" * 64


def annotation(**overrides):
    values = {
        "id": "annotation-copy-1",
        "type": "content",
        "status": "open",
        "required": True,
        "target": AnnotationTarget(
            course_id="blueprint-sample",
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


class AnnotationTargetReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        build_minimal_package(self.root)
        self.document = load_json(self.root / "course/course.json")
        self.source_map = load_json(
            self.root / ".course-work/course-runtime-source-map.json"
        )
        self.definition_hash = canonical_json_hash(self.document)

    def tearDown(self):
        self.temporary.cleanup()

    def record(self, **overrides):
        values = {"definition_hash": self.definition_hash}
        values.update(overrides)
        return annotation(**values)

    def save_annotations(self, *records):
        store = AnnotationStore(self.root / ".course-work/annotations.json")
        for record in records:
            store.add(record)
        store.save()

    def test_block_and_workflow_step_resolve_to_source_map_pointers(self):
        block = resolve_annotation_target(
            self.record(), self.document, self.source_map
        )
        workflow = resolve_annotation_target(
            self.record(
                id="annotation-workflow-1",
                type="workflow",
                target=AnnotationTarget(
                    course_id="blueprint-sample",
                    part_id="part-evidence-check",
                    slice_id="slice-read-and-answer",
                    workflow_step_id="answer",
                ),
            ),
            self.document,
            self.source_map,
        )

        self.assertEqual(block.target_id, "block:claim-text")
        self.assertEqual(block.blueprint_pointer, "/course/parts/0/slices/0/blocks/0")
        self.assertEqual(
            workflow.target_id,
            "slice:slice-read-and-answer/workflow-step:answer",
        )

    def test_item_target_stays_scoped_under_owning_block(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build_full_package(root)
            document = load_json(root / "course/course.json")
            source_map = load_json(
                root / ".course-work/course-runtime-source-map.json"
            )
            record = self.record(
                id="annotation-image-item",
                type="media",
                definition_hash=canonical_json_hash(document),
                target=AnnotationTarget(
                    course_id="blueprint-sample",
                    part_id="part-evidence-check",
                    slice_id="slice-read-and-answer",
                    block_id="diagram",
                    item_id="diagram-item",
                ),
            )

            resolved = resolve_annotation_target(record, document, source_map)

        self.assertEqual(resolved.target_id, "block:diagram")
        self.assertTrue(resolved.blueprint_pointer.endswith("/items/0"))

    def test_structurally_inconsistent_target_becomes_orphaned_and_blocks_g7(self):
        bad = self.record(
            target=AnnotationTarget(
                course_id="blueprint-sample",
                part_id="missing-part",
            )
        )
        self.save_annotations(bad)
        session = new_session("course-a", [], NOW)
        save_session(self.root, session)

        result = reconcile_annotations(self.root, NOW)

        restored = AnnotationStore.load(
            self.root / ".course-work/annotations.json"
        ).get(bad.id)
        self.assertEqual(restored.status, "orphaned")
        self.assertIn(bad.id, result.orphaned_ids)
        issue = IssueStore.load(self.root / ".course-work/issues.json").all()[0]
        self.assertEqual(issue.code, "preview-orphaned-annotation")
        self.assertEqual(load_session(self.root).pending_annotation_ids, [bad.id])

    def test_stale_definition_hash_rebinds_when_stable_target_still_exists(self):
        stale = self.record(definition_hash="0" * 64)
        self.save_annotations(stale)

        result = reconcile_annotations(self.root, NOW)

        rebound = AnnotationStore.load(
            self.root / ".course-work/annotations.json"
        ).get(stale.id)
        self.assertEqual(rebound.definition_hash, self.definition_hash)
        self.assertEqual(rebound.rebound_from_definition_hash, "0" * 64)
        self.assertEqual(result.rebound_ids, (stale.id,))

    def test_orphan_returns_to_open_when_exact_stable_target_reappears(self):
        future = self.record(
            target=AnnotationTarget(
                course_id="blueprint-sample",
                part_id="part-evidence-check",
                slice_id="slice-read-and-answer",
                block_id="future-block",
            )
        )
        self.save_annotations(future)
        reconcile_annotations(self.root, NOW)
        blueprint_path = self.root / ".course-work/course-blueprint.json"
        blueprint = load_json(blueprint_path)
        slice_data = blueprint["course"]["parts"][0]["slices"][0]
        added = copy.deepcopy(slice_data["blocks"][0])
        added["id"] = "future-block"
        slice_data["blocks"].append(added)
        slice_data["layout"]["slots"][0]["blockIds"].append("future-block")
        write_json_atomic(blueprint_path, blueprint)
        write_compilation_outputs_atomic(self.root, compile_blueprint(blueprint))

        result = reconcile_annotations(self.root, "2026-08-16T01:00:00Z")

        restored = AnnotationStore.load(
            self.root / ".course-work/annotations.json"
        ).get(future.id)
        self.assertEqual(restored.status, "open")
        self.assertEqual(result.restored_ids, (future.id,))

    def test_runtime_bug_is_a_blocker_even_when_annotation_is_optional(self):
        bug = self.record(
            id="annotation-runtime-bug",
            type="bug",
            required=False,
            status="proposed",
            classification="runtime-bug",
            proposed_change="Fix the renderer focus trap.",
        )
        self.save_annotations(bug)

        reconcile_annotations(self.root, NOW)

        issues = IssueStore.load(self.root / ".course-work/issues.json").all()
        self.assertEqual(issues[0].code, "preview-runtime-bug")

    def test_optional_open_annotation_does_not_create_g7_issue(self):
        optional = self.record(required=False)
        self.save_annotations(optional)

        result = reconcile_annotations(self.root, NOW)

        self.assertEqual(result.active_issue_ids, ())


class AnnotationCliTests(unittest.TestCase):
    def test_add_reconciles_mock_annotation_and_returns_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "course"
            root.mkdir()
            build_minimal_package(root)
            document = load_json(root / "course/course.json")
            record = annotation(definition_hash=canonical_json_hash(document))
            input_path = Path(temporary) / "annotation.json"
            write_json_atomic(input_path, record.as_dict())

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/manage-annotations.py"),
                    "add",
                    str(root),
                    str(input_path),
                    "--json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["reconciliation"]["resolvedIds"], [record.id])
        self.assertEqual(payload["annotations"][0]["status"], "open")


if __name__ == "__main__":
    unittest.main()
