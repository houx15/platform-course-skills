import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from course_toolkit.annotation_revisions import (
    AnnotationRevisionPlan,
    RevisionPlanBlocked,
    apply_revision_plan,
    prepare_revision_plan,
)
from course_toolkit.annotations import AnnotationStore, AnnotationTarget, CourseAnnotation
from course_toolkit.course_compiler import canonical_json_hash
from course_toolkit.decisions import DecisionStore
from course_toolkit.issues import IssueStore
from course_toolkit.jsonio import load_json, write_json_atomic
from tests.helpers import ROOT
from tests.test_course_package_validation import build_minimal_package


NOW = "2026-08-16T00:00:00Z"


class AnnotationRevisionPlanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        build_minimal_package(self.root)
        self.blueprint = load_json(self.root / ".course-work/course-blueprint.json")
        self.document = load_json(self.root / "course/course.json")
        self.source_map = load_json(
            self.root / ".course-work/course-runtime-source-map.json"
        )
        self.before = self.blueprint["course"]["parts"][0]["slices"][0][
            "blocks"
        ][0]["content"]
        annotation = CourseAnnotation(
            id="annotation-copy-1",
            type="content",
            status="open",
            required=True,
            target=AnnotationTarget(
                course_id="blueprint-sample",
                part_id="part-evidence-check",
                slice_id="slice-read-and-answer",
                block_id="claim-text",
            ),
            definition_hash=canonical_json_hash(self.document),
            text="Shorten this sentence.",
            created_at=NOW,
            updated_at=NOW,
        )
        store = AnnotationStore(self.root / ".course-work/annotations.json")
        store.add(annotation)
        store.save()

    def tearDown(self):
        self.temporary.cleanup()

    def plan_data(self, **entry_overrides):
        entry = {
            "annotationId": "annotation-copy-1",
            "classification": "mechanical",
            "targetId": "block:claim-text",
            "summary": "Shorten copy without changing meaning.",
            "decisionId": None,
            "operations": [
                {
                    "op": "replace",
                    "relativePointer": "/content",
                    "beforeHash": canonical_json_hash(self.before),
                    "value": "A conclusion needs traceable evidence.",
                }
            ],
        }
        entry.update(entry_overrides)
        return {
            "schemaVersion": "1.0",
            "planId": "annotation-revision-1",
            "baseBlueprintHash": canonical_json_hash(self.blueprint),
            "baseDefinitionHash": canonical_json_hash(self.document),
            "baseSourceMapHash": canonical_json_hash(self.source_map),
            "entries": [entry],
        }

    def write_plan(self, data=None):
        path = self.root / "proposed-plan.json"
        write_json_atomic(path, data or self.plan_data())
        return path

    def test_plan_round_trip_is_closed_and_deterministic(self):
        plan = AnnotationRevisionPlan.from_dict(self.plan_data())

        self.assertEqual(plan.as_dict(), self.plan_data())
        self.assertEqual(plan.entries[0].operations[0].relative_pointer, "/content")

    def test_mechanical_plan_cannot_change_protected_semantics(self):
        for pointer in ("/id", "/source", "/completion/rule", "/layout/preset"):
            with self.subTest(pointer=pointer):
                data = self.plan_data()
                data["entries"][0]["operations"][0]["relativePointer"] = pointer
                with self.assertRaisesRegex(ValueError, "mechanical"):
                    AnnotationRevisionPlan.from_dict(data)

    def test_runtime_bug_cannot_mutate_blueprint(self):
        data = self.plan_data(
            classification="runtime-bug",
            operations=self.plan_data()["entries"][0]["operations"],
        )

        with self.assertRaisesRegex(ValueError, "runtime-bug"):
            AnnotationRevisionPlan.from_dict(data)

    def test_stale_base_hash_blocks_preparation_without_mutation(self):
        data = self.plan_data()
        data["baseDefinitionHash"] = "0" * 64
        path = self.write_plan(data)
        before = (self.root / ".course-work/annotations.json").read_bytes()

        with self.assertRaisesRegex(RevisionPlanBlocked, "baseDefinitionHash"):
            prepare_revision_plan(self.root, path, NOW)

        self.assertEqual(
            (self.root / ".course-work/annotations.json").read_bytes(),
            before,
        )

    def test_prepare_mechanical_plan_marks_annotation_proposed(self):
        result = prepare_revision_plan(self.root, self.write_plan(), NOW)

        restored = AnnotationStore.load(
            self.root / ".course-work/annotations.json"
        ).get("annotation-copy-1")
        self.assertEqual(restored.status, "proposed")
        self.assertEqual(restored.classification, "mechanical")
        self.assertEqual(result.pending_decision_ids, ())
        self.assertTrue(
            (self.root / ".course-work/annotation-revision-plan.json").is_file()
        )

    def test_semantic_plan_creates_context_hashed_teacher_decision(self):
        data = self.plan_data(
            classification="semantic",
            decisionId="decision-annotation-copy-1",
            operations=[
                {
                    "op": "replace",
                    "relativePointer": "/content",
                    "beforeHash": canonical_json_hash(self.before),
                    "value": "Evidence must be traceable before accepting the claim.",
                }
            ],
        )

        first = prepare_revision_plan(self.root, self.write_plan(data), NOW)
        second = prepare_revision_plan(self.root, self.write_plan(data), NOW)

        decision = DecisionStore.load(
            self.root / ".course-work/decisions.json"
        ).get("decision-annotation-copy-1")
        self.assertEqual(decision.status, "pending")
        self.assertEqual(first.pending_decision_ids, (decision.id,))
        self.assertEqual(second.pending_decision_ids, (decision.id,))
        self.assertEqual(decision.context["annotationId"], "annotation-copy-1")

    def test_prepare_runtime_bug_creates_g7_blocker_without_operations(self):
        store = AnnotationStore.load(self.root / ".course-work/annotations.json")
        bug = CourseAnnotation(
            id="annotation-runtime-bug",
            type="bug",
            status="open",
            required=False,
            target=store.get("annotation-copy-1").target,
            definition_hash=canonical_json_hash(self.document),
            text="Focus does not return after closing the modal.",
            created_at=NOW,
            updated_at=NOW,
        )
        store.add(bug)
        store.save()
        data = self.plan_data(
            annotationId=bug.id,
            classification="runtime-bug",
            summary="Fix focus restoration in the renderer.",
            operations=[],
        )

        result = prepare_revision_plan(self.root, self.write_plan(data), NOW)

        issues = IssueStore.load(self.root / ".course-work/issues.json").all()
        runtime_issue = next(issue for issue in issues if issue.code == "preview-runtime-bug")
        self.assertEqual(runtime_issue.target["annotationId"], bug.id)
        self.assertEqual(result.runtime_bug_annotation_ids, (bug.id,))

    def test_apply_mechanical_revision_updates_blueprint_not_definition(self):
        path = self.write_plan()
        prepare_revision_plan(self.root, path, NOW)
        definition_before = (self.root / "course/course.json").read_bytes()

        result = apply_revision_plan(
            self.root,
            path,
            "2026-08-16T01:00:00Z",
        )

        blueprint = load_json(self.root / ".course-work/course-blueprint.json")
        changed = blueprint["course"]["parts"][0]["slices"][0]["blocks"][0]
        self.assertEqual(changed["content"], "A conclusion needs traceable evidence.")
        self.assertEqual((self.root / "course/course.json").read_bytes(), definition_before)
        applied = AnnotationStore.load(
            self.root / ".course-work/annotations.json"
        ).get("annotation-copy-1")
        self.assertEqual(applied.status, "applied")
        self.assertEqual(applied.applied_blueprint_hash, result.blueprint_hash)
        self.assertIsNone(applied.verified_against_definition_hash)

    def test_semantic_revision_blocks_until_exact_decision_is_approved(self):
        data = self.plan_data(
            classification="semantic",
            decisionId="decision-annotation-copy-1",
        )
        path = self.write_plan(data)
        prepare_revision_plan(self.root, path, NOW)

        with self.assertRaisesRegex(RevisionPlanBlocked, "not approved"):
            apply_revision_plan(self.root, path, "2026-08-16T01:00:00Z")

        decisions = DecisionStore.load(self.root / ".course-work/decisions.json")
        decisions.confirm(
            "decision-annotation-copy-1",
            {"choice": "approve", "rationale": "The revised wording is clearer."},
            "2026-08-16T01:00:00Z",
        )
        decisions.save()
        result = apply_revision_plan(
            self.root,
            path,
            "2026-08-16T02:00:00Z",
        )

        self.assertFalse(result.idempotent)
        annotation = AnnotationStore.load(
            self.root / ".course-work/annotations.json"
        ).get("annotation-copy-1")
        self.assertEqual(
            annotation.resolution_decision_id,
            "decision-annotation-copy-1",
        )
        blueprint = load_json(self.root / ".course-work/course-blueprint.json")
        self.assertIn(
            "decision-annotation-copy-1",
            blueprint["approval"]["decisionIds"],
        )

    def test_reapplying_exact_plan_is_idempotent(self):
        path = self.write_plan()
        prepare_revision_plan(self.root, path, NOW)
        first = apply_revision_plan(self.root, path, "2026-08-16T01:00:00Z")
        before = (self.root / ".course-work/course-blueprint.json").read_bytes()

        second = apply_revision_plan(self.root, path, "2026-08-16T02:00:00Z")

        self.assertTrue(second.idempotent)
        self.assertEqual(second.blueprint_hash, first.blueprint_hash)
        self.assertEqual(
            (self.root / ".course-work/course-blueprint.json").read_bytes(),
            before,
        )

    def test_atomic_write_failure_rolls_back_blueprint_and_annotations(self):
        path = self.write_plan()
        prepare_revision_plan(self.root, path, NOW)
        blueprint_before = (self.root / ".course-work/course-blueprint.json").read_bytes()
        annotations_before = (self.root / ".course-work/annotations.json").read_bytes()
        calls = 0

        def fail_second(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected replace failure")
            os.replace(source, destination)

        with self.assertRaisesRegex(OSError, "injected"):
            apply_revision_plan(
                self.root,
                path,
                "2026-08-16T01:00:00Z",
                replace_output=fail_second,
            )

        self.assertEqual(
            (self.root / ".course-work/course-blueprint.json").read_bytes(),
            blueprint_before,
        )
        self.assertEqual(
            (self.root / ".course-work/annotations.json").read_bytes(),
            annotations_before,
        )

    def test_apply_cli_returns_explicit_rebuild_sequence(self):
        path = self.write_plan()
        prepare_revision_plan(self.root, path, NOW)

        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/manage-annotations.py"),
                "apply",
                str(self.root),
                str(path),
                "--json",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(
            payload["application"]["appliedAnnotationIds"],
            ["annotation-copy-1"],
        )
        self.assertIn(
            "python scripts/compile-course.py ROOT --json",
            payload["application"]["nextRequiredCommands"],
        )


if __name__ == "__main__":
    unittest.main()
