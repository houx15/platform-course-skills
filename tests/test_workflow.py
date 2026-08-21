import tempfile
import unittest
from pathlib import Path

from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.issues import IssueStore, make_registered_issue
from course_toolkit.workflow import (
    ArtifactReconciliationResult,
    G3_EVIDENCE_KEYS,
    G4_EVIDENCE_KEYS,
    G4_PREREQUISITE_COVERAGE_KEY,
    MEDIA_DESIGN_RELATIVE_PATH,
    G5_EVIDENCE_KEYS,
    G6_EVIDENCE_KEYS,
    G7_EVIDENCE_KEYS,
    G8_EVIDENCE_KEYS,
    G9_EVIDENCE_KEYS,
    G10_EVIDENCE_KEYS,
    WorkflowError,
    complete_gate,
    hash_path,
    load_session,
    new_session,
    reconcile_artifacts,
    reconcile_current_session,
    save_session,
    set_phase_status,
    workflow_summary,
    verify_g3_plan,
    verify_g4_media_design,
    verify_g5_compilation,
    verify_g6_validation,
)
from course_toolkit.instructional_plan import approve_plan
from course_toolkit.course_package_validation import (
    build_course_validation_report,
    sync_validation_issues,
    write_current_validation_report,
)
from tests.test_course_package_validation import build_full_package
from tests.test_instructional_plan import write_root, write_valid_media_design


NOW = "2026-08-16T00:00:00Z"


def fully_gated_through(gate_id):
    session = new_session("course-a", [], NOW)
    for index in range(int(gate_id[1:]) + 1):
        if index == 3:
            evidence = {key: "3" * 64 for key in G3_EVIDENCE_KEYS}
        elif index == 4:
            evidence = {
                key: (
                    "3" * 64
                    if key in {".course-work/course-storyboard.json", G4_PREREQUISITE_COVERAGE_KEY}
                    else "4" * 64
                )
                for key in (*G4_EVIDENCE_KEYS, G4_PREREQUISITE_COVERAGE_KEY)
            }
        elif index == 5:
            evidence = {key: "a" * 64 for key in G5_EVIDENCE_KEYS}
        elif index == 6:
            evidence = {key: "b" * 64 for key in G6_EVIDENCE_KEYS}
        elif index == 7:
            evidence = {key: "e" * 64 for key in G7_EVIDENCE_KEYS}
        elif index == 8:
            evidence = {key: "f" * 64 for key in G8_EVIDENCE_KEYS}
        elif index == 9:
            evidence = {key: "c" * 64 for key in G9_EVIDENCE_KEYS}
        elif index == 10:
            evidence = {key: "d" * 64 for key in G10_EVIDENCE_KEYS}
        else:
            evidence = None
        complete_gate(session, f"G{index}", NOW, gate_evidence=evidence)
    return session


def legacy_without_page_plan_evidence(session):
    """Model pre-Task-3 sessions, which remain readable without new evidence."""
    for key in (*G3_EVIDENCE_KEYS, *G4_EVIDENCE_KEYS):
        session.artifact_hashes.pop(key, None)
    return session


def bind_current_page_plan_evidence(root, session):
    # Package-validation fixtures already contain a compiled CourseDefinition.
    # Bind their G3/G4 records to that definition so the Task-4 correspondence
    # layer is testing a current plan rather than an intentionally unrelated
    # standalone page-plan fixture.
    if (root / "course/course.json").is_file():
        part_id = "part-evidence-check"
        slice_id = "slice-read-and-answer"
        coverage = {
            "schemaVersion": "2.0",
            "items": [
                {
                    "sourceId": "source-1",
                    "sourceFile": "materials/claim.md",
                    "location": "paragraph:1",
                    "summary": "回答题目的主张证据",
                    "disposition": "required-core",
                    "bindings": [{
                        "partId": part_id,
                        "sliceId": slice_id,
                        "blockId": "claim-text",
                        "role": "question-reference",
                        "supportsIds": ["evidence-question"],
                    }],
                }
            ],
        }
        plan = {
            "schemaVersion": "2.0",
            "title": "当前课程计划",
            "parts": [{"partId": part_id, "title": "证据", "slices": [{
                "partId": part_id,
                "sliceId": slice_id,
                "title": "看主张作答",
                "teachingPurpose": "在主张证据支持下完成回答。",
                "sourceUses": [{"sourceId": "source-1", "locator": "paragraph:1", "materialRole": "回答证据"}],
                "learnerSees": "主张和题目。",
                "learnerAction": {"kind": "answer", "description": "查看主张后作答。", "referencePolicy": "co-visible", "referenceSourceIds": ["source-1"], "targetId": "question:evidence-question"},
                "completionEvidence": {"event": "block.completed"},
                "layoutIntent": {"preset": "full"},
                "coVisibleRequirements": [{"sourceId": "source-1", "targetId": "question:evidence-question", "reason": "作答时需要主张证据。"}],
                "imageRelationships": [],
                "unresolvedBlockers": [],
                "proposedExclusions": [],
            }]}],
        }
        extracted = {
            "schemaVersion": "1.0",
            "items": [{"sourceId": "source-1", "sourceFile": "materials/claim.md", "location": "paragraph:1", "kind": "file", "text": "回答题目的主张证据"}],
            "ignored": [], "unsupported": [], "errors": [],
        }
        write_root(root, plan=plan, coverage=coverage, extracted=extracted)
    else:
        write_root(root)
    approve_plan(root, decision_id="decision-plan-fixture", approved_at=NOW)
    write_valid_media_design(root)
    session.artifact_hashes.update(verify_g3_plan(root))
    session.artifact_hashes.update(verify_g4_media_design(root))
    return session


class AtomicJsonTests(unittest.TestCase):
    def test_write_json_atomic_creates_parent_and_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".course-work" / "session.json"

            write_json_atomic(path, {"phase": "intake", "title": "课程"})

            self.assertEqual(load_json(path)["title"], "课程")
            self.assertEqual(list(path.parent.glob("*.tmp")), [])


class WorkflowGateTests(unittest.TestCase):
    def test_cannot_complete_gate_before_prerequisite(self):
        session = new_session("course-a", ["materials/source.md"], NOW)

        with self.assertRaisesRegex(WorkflowError, "G1 requires G0"):
            complete_gate(session, "G1", NOW)

    def test_completing_gate_advances_to_next_phase(self):
        session = new_session("course-a", [], NOW)

        complete_gate(session, "G0", NOW)

        self.assertEqual(session.phase, "material-review")
        self.assertEqual(session.completed_gate_ids, ["G0"])

    def test_complete_gate_refuses_active_blocker(self):
        session = new_session("course-a", [], NOW)
        blocker = make_registered_issue(
            code="workflow-active-blocker",
            source="workflow",
            message="unsafe path",
            gate_id="G0",
            seen_at=NOW,
        )

        with self.assertRaisesRegex(WorkflowError, "active blocker"):
            complete_gate(session, "G0", NOW, active_issues=[blocker])

    def test_complete_gate_refuses_pending_teacher_decision(self):
        session = new_session("course-a", [], NOW)

        with self.assertRaisesRegex(WorkflowError, "pending teacher decision"):
            complete_gate(
                session,
                "G0",
                NOW,
                pending_decision_ids=["decision-1"],
            )

    def test_downstream_blocker_does_not_block_earlier_gate(self):
        session = new_session("course-a", [], NOW)
        blocker = make_registered_issue(
            code="workflow-missing-source",
            source="workflow",
            message="source not available yet",
            gate_id="G1",
            seen_at=NOW,
        )

        complete_gate(session, "G0", NOW, active_issues=[blocker])

        self.assertEqual(session.completed_gate_ids, ["G0"])

    def test_session_round_trips_and_summary_exposes_next_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = new_session("course-a", ["materials/source.md"], NOW)
            complete_gate(session, "G0", NOW)
            save_session(root, session)

            restored = load_session(root)
            summary = workflow_summary(restored)

            self.assertEqual(restored.course_local_id, "course-a")
            self.assertEqual(restored.source_paths, ["materials/source.md"])
            self.assertEqual(summary["nextAction"], "complete G1")

    def test_pending_annotations_are_the_next_visible_action(self):
        session = new_session("course-a", [], NOW)
        session.pending_annotation_ids = ["annotation-required-1"]

        self.assertEqual(
            workflow_summary(session)["nextAction"],
            "resolve preview annotations",
        )

    def test_status_transition_records_failure_without_changing_phase(self):
        session = new_session("course-a", [], NOW)

        set_phase_status(
            session,
            "failed",
            NOW,
            failure={"code": "storage-error", "message": "disk full"},
        )

        self.assertEqual(session.phase, "intake")
        self.assertEqual(session.status, "failed")
        self.assertEqual(session.failure["code"], "storage-error")

    def test_status_api_cannot_bypass_remote_verification_gate(self):
        session = new_session("course-a", [], NOW)

        with self.assertRaisesRegex(WorkflowError, "only be set by G10"):
            set_phase_status(session, "complete", NOW)

    def test_publish_statuses_require_their_gates(self):
        session = new_session("course-a", [], NOW)

        with self.assertRaisesRegex(WorkflowError, "requires G8"):
            set_phase_status(session, "ready-to-publish", NOW)
        with self.assertRaisesRegex(WorkflowError, "requires G9"):
            set_phase_status(session, "publishing", NOW)

    def test_load_rejects_noncontiguous_completed_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = new_session("course-a", [], NOW)
            data = session.as_dict()
            data["completedGateIds"] = ["G0", "G2"]
            write_json_atomic(root / ".course-work" / "session.json", data)

            with self.assertRaisesRegex(ValueError, "contiguous"):
                load_session(root)

    def test_g5_requires_verified_compilation_evidence(self):
        session = fully_gated_through("G4")

        with self.assertRaisesRegex(WorkflowError, "compilation evidence"):
            complete_gate(session, "G5", NOW)

    def test_g3_and_g4_require_page_plan_evidence(self):
        session = fully_gated_through("G2")
        with self.assertRaisesRegex(WorkflowError, "G3 requires current page-plan evidence"):
            complete_gate(session, "G3", NOW)

        complete_gate(
            session,
            "G3",
            NOW,
            gate_evidence={key: "3" * 64 for key in G3_EVIDENCE_KEYS},
        )
        with self.assertRaisesRegex(WorkflowError, "G4 requires current approved page-plan"):
            complete_gate(session, "G4", NOW)

    def test_gate_evidence_rejects_unknown_or_non_hash_values(self):
        session = fully_gated_through("G2")
        valid = {key: "a" * 64 for key in G3_EVIDENCE_KEYS}
        with self.assertRaisesRegex(WorkflowError, "unexpected evidence: extra"):
            complete_gate(
                session,
                "G3",
                NOW,
                gate_evidence={**valid, "extra": "a" * 64},
            )
        with self.assertRaisesRegex(WorkflowError, "must be a SHA-256 hash"):
            complete_gate(
                session,
                "G3",
                NOW,
                gate_evidence={**valid, ".course-work/course-storyboard.json": "not-a-hash"},
            )

    def test_g6_requires_verified_validation_evidence(self):
        session = fully_gated_through("G5")

        with self.assertRaisesRegex(WorkflowError, "validation evidence"):
            complete_gate(session, "G6", NOW)

    def test_g9_requires_verified_publication_preflight_evidence(self):
        session = fully_gated_through("G8")

        with self.assertRaisesRegex(WorkflowError, "publication preflight evidence"):
            complete_gate(session, "G9", NOW)

    def test_g8_requires_independent_review_evidence(self):
        session = fully_gated_through("G7")

        with self.assertRaisesRegex(WorkflowError, "independent review evidence"):
            complete_gate(session, "G8", NOW)

    def test_g7_requires_renderer_preview_evidence(self):
        session = fully_gated_through("G6")

        with self.assertRaisesRegex(WorkflowError, "renderer preview evidence"):
            complete_gate(session, "G7", NOW)

    def test_g10_requires_verified_remote_publication_evidence(self):
        session = fully_gated_through("G9")

        with self.assertRaisesRegex(WorkflowError, "remote verification evidence"):
            complete_gate(session, "G10", NOW)


class ArtifactReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_directory_hash_is_deterministic_and_ignores_zip_files(self):
        materials = self.root / "materials"
        materials.mkdir()
        (materials / "b.md").write_text("B", encoding="utf-8")
        (materials / "a.md").write_text("A", encoding="utf-8")
        before = hash_path(materials)

        (materials / "ignored.zip").write_bytes(b"archive")
        after = hash_path(materials)

        self.assertEqual(before, after)

    def test_blueprint_change_invalidates_g5_and_downstream_only(self):
        blueprint = self.root / ".course-work" / "course-blueprint.json"
        write_json_atomic(blueprint, {"title": "new"})
        session = bind_current_page_plan_evidence(self.root, fully_gated_through("G8"))
        session.artifact_hashes[".course-work/course-blueprint.json"] = "old"

        result = reconcile_artifacts(self.root, session, NOW)

        self.assertIsInstance(result, ArtifactReconciliationResult)
        self.assertEqual(session.completed_gate_ids, ["G0", "G1", "G2", "G3", "G4"])
        self.assertIn("G5", session.invalidated_gate_ids)
        self.assertEqual(session.phase, "compile")
        self.assertEqual(result.earliest_invalidated_gate_id, "G5")

    def test_revalidated_artifact_resolves_prior_change_warning(self):
        blueprint = self.root / ".course-work" / "course-blueprint.json"
        write_json_atomic(blueprint, {"title": "new"})
        session = bind_current_page_plan_evidence(self.root, fully_gated_through("G8"))
        session.artifact_hashes[".course-work/course-blueprint.json"] = "old"

        first = reconcile_artifacts(self.root, session, NOW)
        second = reconcile_artifacts(self.root, session, NOW)

        self.assertTrue(
            any(issue.code == "workflow-artifact-changed" for issue in first.active_issues)
        )
        self.assertFalse(
            any(
                issue.code == "workflow-artifact-changed"
                and issue.target == {"path": ".course-work/course-blueprint.json"}
                for issue in second.active_issues
            )
        )

    def test_renderer_version_change_invalidates_preview_not_compilation(self):
        manifest = self.root / ".course-work" / "preview-manifest.json"
        write_json_atomic(manifest, {"rendererVersion": "1"})
        session = bind_current_page_plan_evidence(self.root, fully_gated_through("G8"))
        for key in G5_EVIDENCE_KEYS:
            session.artifact_hashes.pop(key, None)
        for key in G6_EVIDENCE_KEYS:
            session.artifact_hashes.pop(key, None)
        session.artifact_hashes[
            ".course-work/preview-manifest.json"
        ] = hash_path(manifest)
        write_json_atomic(manifest, {"rendererVersion": "2"})

        reconcile_artifacts(self.root, session, NOW)

        self.assertEqual(
            session.completed_gate_ids,
            ["G0", "G1", "G2", "G3", "G4", "G5", "G6"],
        )
        self.assertEqual(session.phase, "preview")

    def test_first_observation_records_baseline_without_invalidation(self):
        material = self.root / "materials" / "source.md"
        material.parent.mkdir()
        material.write_text("source", encoding="utf-8")
        session = fully_gated_through("G2")

        result = reconcile_artifacts(self.root, session, NOW)

        self.assertIsNone(result.earliest_invalidated_gate_id)
        self.assertIn("materials/", session.artifact_hashes)
        self.assertEqual(session.completed_gate_ids, ["G0", "G1", "G2"])

    def test_publisher_code_change_invalidates_g9_only(self):
        session = bind_current_page_plan_evidence(self.root, fully_gated_through("G9"))
        for key in (
            *G5_EVIDENCE_KEYS,
            *G6_EVIDENCE_KEYS,
            *G7_EVIDENCE_KEYS,
            *G8_EVIDENCE_KEYS,
        ):
            session.artifact_hashes.pop(key, None)
        session.artifact_hashes["@toolkit/course-publisher"] = "0" * 64

        result = reconcile_artifacts(self.root, session, NOW)

        self.assertEqual(session.completed_gate_ids[-1], "G8")
        self.assertEqual(result.earliest_invalidated_gate_id, "G9")

    def test_missing_explicit_source_creates_blocker(self):
        session = new_session("course-a", ["sources/missing.md"], NOW)

        result = reconcile_artifacts(self.root, session, NOW)

        self.assertEqual(len(result.active_issues), 1)
        self.assertEqual(result.active_issues[0].code, "workflow-missing-source")
        self.assertEqual(session.active_issue_ids, [result.active_issues[0].id])

    def test_external_source_change_uses_g1(self):
        source = self.root / "sources" / "source.md"
        source.parent.mkdir()
        source.write_text("new", encoding="utf-8")
        session = fully_gated_through("G3")
        session.source_paths = ["sources/source.md"]
        session.artifact_hashes["sources/source.md"] = "old"

        reconcile_artifacts(self.root, session, NOW)

        self.assertEqual(session.completed_gate_ids, ["G0"])
        self.assertEqual(session.phase, "material-review")

    def test_unsafe_source_path_is_rejected(self):
        session = new_session("course-a", ["../outside.md"], NOW)

        with self.assertRaisesRegex(WorkflowError, "safe relative path"):
            reconcile_artifacts(self.root, session, NOW)

    def test_symlink_in_hashed_tree_is_rejected(self):
        materials = self.root / "materials"
        materials.mkdir()
        outside = self.root / "outside.md"
        outside.write_text("outside", encoding="utf-8")
        (materials / "linked.md").symlink_to(outside)

        with self.assertRaisesRegex(ValueError, "symlink"):
            hash_path(materials)


class PagePlanGateEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        write_root(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def approve_and_design_media(self, *, decision_id="decision-plan-1"):
        approve_plan(self.root, decision_id=decision_id, approved_at=NOW)
        write_valid_media_design(self.root)

    def complete_through_g4(self):
        session = fully_gated_through("G2")
        complete_gate(session, "G3", NOW, gate_evidence=verify_g3_plan(self.root))
        self.approve_and_design_media()
        complete_gate(session, "G4", NOW, gate_evidence=verify_g4_media_design(self.root))
        return session

    def test_current_plan_completes_g3_and_current_approval_completes_g4(self):
        session = fully_gated_through("G2")

        complete_gate(session, "G3", NOW, gate_evidence=verify_g3_plan(self.root))
        self.approve_and_design_media()
        complete_gate(session, "G4", NOW, gate_evidence=verify_g4_media_design(self.root))

        self.assertEqual(session.completed_gate_ids, ["G0", "G1", "G2", "G3", "G4"])
        self.assertIn("@decision/course-plan-approval", session.artifact_hashes)

    def test_approval_metadata_does_not_invalidate_completed_g3(self):
        session = fully_gated_through("G2")
        complete_gate(session, "G3", NOW, gate_evidence=verify_g3_plan(self.root))

        approve_plan(self.root, decision_id="decision-plan-1", approved_at=NOW)
        result = reconcile_artifacts(self.root, session, NOW)

        self.assertIsNone(result.earliest_invalidated_gate_id)
        self.assertIn("G3", session.completed_gate_ids)

    def test_g4_cannot_replace_completed_g3_plan_baseline(self):
        session = fully_gated_through("G2")
        complete_gate(session, "G3", NOW, gate_evidence=verify_g3_plan(self.root))
        plan_path = self.root / ".course-work" / "course-storyboard.json"
        plan = load_json(plan_path)
        plan["parts"][0]["slices"][0]["teachingPurpose"] = "重新审批后的页面目标"
        write_json_atomic(plan_path, plan)
        self.approve_and_design_media(decision_id="decision-plan-2")

        with self.assertRaisesRegex(WorkflowError, "differs from completed G3"):
            complete_gate(
                session,
                "G4",
                NOW,
                gate_evidence=verify_g4_media_design(self.root),
            )
        self.assertNotIn("G4", session.completed_gate_ids)

    def test_g4_direct_api_rejects_current_coverage_drift_from_g3(self):
        session = fully_gated_through("G2")
        complete_gate(session, "G3", NOW, gate_evidence=verify_g3_plan(self.root))
        coverage_path = self.root / ".course-work" / "source-coverage.json"
        coverage = load_json(coverage_path)
        coverage["items"][0]["summary"] = "更新后的覆盖证据"
        write_json_atomic(coverage_path, coverage)
        self.approve_and_design_media(decision_id="decision-plan-coverage-2")

        with self.assertRaisesRegex(WorkflowError, "source coverage differs from completed G3"):
            complete_gate(
                session,
                "G4",
                NOW,
                gate_evidence=verify_g4_media_design(self.root),
            )

    def test_media_design_requires_complete_current_media_and_narration_plan(self):
        self.approve_and_design_media()
        media_path = self.root / ".course-work" / "media-design.json"
        self.assertIn(MEDIA_DESIGN_RELATIVE_PATH, verify_g4_media_design(self.root))

        write_json_atomic(media_path, {})
        with self.assertRaisesRegex(WorkflowError, "schema-version"):
            verify_g4_media_design(self.root)

        write_valid_media_design(self.root)
        media = load_json(media_path)
        media["planContentHash"] = "0" * 64
        write_json_atomic(media_path, media)
        with self.assertRaisesRegex(WorkflowError, "stale-plan"):
            verify_g4_media_design(self.root)

        write_valid_media_design(self.root)
        media = load_json(media_path)
        media["items"] = []
        write_json_atomic(media_path, media)
        with self.assertRaisesRegex(WorkflowError, "media-items-incomplete"):
            verify_g4_media_design(self.root)

        write_valid_media_design(self.root)
        media = load_json(media_path)
        media["items"].append(dict(media["items"][0]))
        write_json_atomic(media_path, media)
        with self.assertRaisesRegex(WorkflowError, "duplicate-media-item"):
            verify_g4_media_design(self.root)

        write_valid_media_design(self.root)
        media = load_json(media_path)
        media["items"][0]["status"] = "draft"
        write_json_atomic(media_path, media)
        with self.assertRaisesRegex(WorkflowError, "media-status"):
            verify_g4_media_design(self.root)

        write_valid_media_design(self.root)
        media = load_json(media_path)
        media["items"][0]["status"] = "ready"
        write_json_atomic(media_path, media)
        with self.assertRaisesRegex(WorkflowError, "media-status"):
            verify_g4_media_design(self.root)

        write_valid_media_design(self.root)
        media = load_json(media_path)
        media["narrations"][0]["status"] = "ready"
        write_json_atomic(media_path, media)
        with self.assertRaisesRegex(WorkflowError, "narration-status"):
            verify_g4_media_design(self.root)

        write_valid_media_design(self.root)
        media = load_json(media_path)
        media["items"][0]["kind"] = "video"
        write_json_atomic(media_path, media)
        with self.assertRaisesRegex(WorkflowError, "media-item-mismatch"):
            verify_g4_media_design(self.root)

        write_valid_media_design(self.root)
        media = load_json(media_path)
        media["items"][0]["sourcePath"] = "materials/not-the-approved-source.pdf"
        write_json_atomic(media_path, media)
        with self.assertRaisesRegex(WorkflowError, "media-item-mismatch"):
            verify_g4_media_design(self.root)

        write_valid_media_design(self.root)
        media = load_json(media_path)
        (self.root / media["items"][0]["sourcePath"]).unlink()
        with self.assertRaisesRegex(WorkflowError, "media-source-missing"):
            verify_g4_media_design(self.root)

    def test_media_design_allows_empty_items_only_for_a_text_only_plan(self):
        coverage_path = self.root / ".course-work" / "source-coverage.json"
        coverage = load_json(coverage_path)
        for item in coverage["items"][:2]:
            item["sourceFile"] = item["sourceFile"].rsplit(".", 1)[0] + ".txt"
        write_json_atomic(coverage_path, coverage)
        extracted_path = self.root / ".course-work" / "materials-extracted.json"
        extracted = load_json(extracted_path)
        for item in extracted["items"][:2]:
            item["sourceFile"] = item["sourceFile"].rsplit(".", 1)[0] + ".txt"
        write_json_atomic(extracted_path, extracted)
        self.approve_and_design_media()

        design = load_json(self.root / ".course-work" / "media-design.json")
        self.assertEqual(design["items"], [])
        self.assertIn(MEDIA_DESIGN_RELATIVE_PATH, verify_g4_media_design(self.root))

    def test_media_source_symlink_is_rejected(self):
        self.approve_and_design_media()
        media = load_json(self.root / ".course-work" / "media-design.json")
        source = self.root / media["items"][0]["sourcePath"]
        target = self.root / "replacement-source.pdf"
        target.write_bytes(b"replacement")
        source.unlink()
        source.symlink_to(target)

        with self.assertRaisesRegex(WorkflowError, "media-path"):
            verify_g4_media_design(self.root)

    def test_media_deletion_and_reappearance_require_g4_recompletion(self):
        session = self.complete_through_g4()
        media_path = self.root / ".course-work" / "media-design.json"
        media_path.unlink()

        deleted = reconcile_artifacts(self.root, session, NOW)
        self.assertEqual(deleted.earliest_invalidated_gate_id, "G4")
        write_valid_media_design(self.root)
        reconcile_artifacts(self.root, session, NOW)
        complete_gate(session, "G4", NOW, gate_evidence=verify_g4_media_design(self.root))
        self.assertIn("G4", session.completed_gate_ids)

    def test_legacy_completed_course_is_not_retroactively_invalidated_by_new_plan_evidence(self):
        session = self.complete_through_g4()
        for key in G3_EVIDENCE_KEYS:
            session.artifact_hashes.pop(key, None)
        save_session(self.root, session)

        before_load = load_json(self.root / ".course-work" / "session.json")
        restored = load_session(self.root)
        self.assertEqual(restored.as_dict(), before_load)
        # A plain deserialize-and-save path is not a hidden migration.
        save_session(self.root, restored)
        self.assertEqual(load_session(self.root).completed_gate_ids[-1], "G4")

        result = reconcile_current_session(self.root, restored, NOW)
        self.assertEqual(restored.completed_gate_ids[-1], "G4")
        self.assertEqual(restored.invalidated_gate_ids, [])
        self.assertIsNone(result.earliest_invalidated_gate_id)
        self.assertIsNone(result.page_plan_proof_gate_id)
        self.assertEqual(load_session(self.root).completed_gate_ids[-1], "G4")
        active = [
            issue
            for issue in IssueStore.load(self.root / ".course-work" / "issues.json").all()
            if issue.status == "active"
        ]
        self.assertFalse(any(issue.code == "workflow-page-plan-evidence-unproved" for issue in active))

        repeated = reconcile_current_session(self.root, restored, NOW)
        self.assertIsNone(repeated.earliest_invalidated_gate_id)
        self.assertEqual(list(repeated.active_issues), active)

    def test_symlink_course_root_is_rejected_by_g3_and_g4(self):
        parent = Path(self.temporary.name).parent
        alias = parent / f"course-root-link-{self.root.name}"
        alias.symlink_to(self.root, target_is_directory=True)
        self.addCleanup(lambda: alias.unlink(missing_ok=True))

        with self.assertRaisesRegex(WorkflowError, "symlink-root"):
            verify_g3_plan(alias)
        with self.assertRaisesRegex(WorkflowError, "symlink-root"):
            verify_g4_media_design(alias)

    def test_plan_body_or_source_coverage_change_invalidates_g3_onward(self):
        session = self.complete_through_g4()
        plan_path = self.root / ".course-work" / "course-storyboard.json"
        plan = load_json(plan_path)
        plan["parts"][0]["slices"][0]["teachingPurpose"] = "更新后的学习目标"
        write_json_atomic(plan_path, plan)

        body_result = reconcile_artifacts(self.root, session, NOW)
        self.assertEqual(body_result.earliest_invalidated_gate_id, "G3")
        self.assertEqual(session.completed_gate_ids, ["G0", "G1", "G2"])

        session = self.complete_through_g4()
        coverage_path = self.root / ".course-work" / "source-coverage.json"
        coverage = load_json(coverage_path)
        coverage["items"][0]["summary"] = "更新后的材料摘要"
        write_json_atomic(coverage_path, coverage)

        coverage_result = reconcile_artifacts(self.root, session, NOW)
        self.assertEqual(coverage_result.earliest_invalidated_gate_id, "G3")
        self.assertEqual(session.completed_gate_ids, ["G0", "G1", "G2"])

    def test_approval_or_media_design_change_invalidates_g4_onward(self):
        session = self.complete_through_g4()
        self.approve_and_design_media(decision_id="decision-plan-2")

        approval_result = reconcile_artifacts(self.root, session, NOW)
        self.assertEqual(approval_result.earliest_invalidated_gate_id, "G4")
        self.assertEqual(session.completed_gate_ids, ["G0", "G1", "G2", "G3"])

        session = self.complete_through_g4()
        media_path = self.root / ".course-work" / "media-design.json"
        media = load_json(media_path)
        media["designId"] = "media-design-2"
        write_json_atomic(media_path, media)

        media_result = reconcile_artifacts(self.root, session, NOW)
        self.assertEqual(media_result.earliest_invalidated_gate_id, "G4")
        self.assertEqual(session.completed_gate_ids, ["G0", "G1", "G2", "G3"])

        repeated = reconcile_artifacts(self.root, session, NOW)
        self.assertIsNone(repeated.earliest_invalidated_gate_id)
        self.assertFalse(
            any(
                issue.target == {"path": ".course-work/media-design.json"}
                for issue in repeated.active_issues
            )
        )

    def test_g4_rejects_malformed_or_non_object_media_design(self):
        self.approve_and_design_media()
        media_path = self.root / ".course-work" / "media-design.json"
        media_path.write_text("{broken", encoding="utf-8")
        with self.assertRaisesRegex(WorkflowError, "invalid JSON"):
            verify_g4_media_design(self.root)

        write_json_atomic(media_path, ["not", "an", "object"])
        with self.assertRaisesRegex(WorkflowError, "must be a JSON object"):
            verify_g4_media_design(self.root)

        target = self.root / "media-design-target.json"
        write_json_atomic(target, {"schemaVersion": "1.0"})
        media_path.unlink()
        media_path.symlink_to(target)
        with self.assertRaisesRegex(WorkflowError, "must not traverse a symlink"):
            verify_g4_media_design(self.root)

    def test_storyboard_markdown_is_not_gate_evidence_and_reconcile_is_idempotent(self):
        session = self.complete_through_g4()
        markdown = self.root / ".course-work" / "course-storyboard.md"
        markdown.write_text("# regenerated teacher view\n", encoding="utf-8")

        first = reconcile_artifacts(self.root, session, NOW)
        second = reconcile_artifacts(self.root, session, NOW)

        self.assertIsNone(first.earliest_invalidated_gate_id)
        self.assertIsNone(second.earliest_invalidated_gate_id)
        self.assertEqual(session.completed_gate_ids, ["G0", "G1", "G2", "G3", "G4"])


class CompilationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        blueprint_source = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "course-blueprint"
            / "approved-blueprint.json"
        )
        blueprint = load_json(blueprint_source)
        write_json_atomic(
            self.root / ".course-work" / "course-blueprint.json",
            blueprint,
        )
        from course_toolkit.course_compiler import (
            compile_blueprint,
            write_compilation_outputs_atomic,
        )

        write_compilation_outputs_atomic(
            self.root,
            compile_blueprint(blueprint),
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_current_compilation_evidence_allows_g5_and_stores_hashes(self):
        evidence = verify_g5_compilation(self.root)
        session = fully_gated_through("G4")

        complete_gate(session, "G5", NOW, gate_evidence=evidence)

        self.assertIn("course/course.json", session.artifact_hashes)
        self.assertIn("@toolkit/course-compiler", session.artifact_hashes)
        self.assertIn("@toolkit/course-contract-snapshot", session.artifact_hashes)

    def test_mismatched_definition_hash_blocks_g5(self):
        course_path = self.root / "course" / "course.json"
        course = load_json(course_path)
        course["course"]["title"] = "Changed after compilation"
        write_json_atomic(course_path, course)

        with self.assertRaisesRegex(WorkflowError, "does not match compilation"):
            verify_g5_compilation(self.root)

    def test_blueprint_change_invalidates_completed_g5_and_downstream(self):
        session = bind_current_page_plan_evidence(self.root, fully_gated_through("G5"))
        session.artifact_hashes.update(verify_g5_compilation(self.root))
        blueprint_path = self.root / ".course-work" / "course-blueprint.json"
        blueprint = load_json(blueprint_path)
        blueprint["course"]["title"] = "Changed blueprint"
        write_json_atomic(blueprint_path, blueprint)

        reconcile_artifacts(self.root, session, NOW)

        self.assertEqual(session.completed_gate_ids, ["G0", "G1", "G2", "G3", "G4"])
        self.assertEqual(session.phase, "compile")

    def test_compiler_evidence_change_invalidates_g5_and_downstream(self):
        session = bind_current_page_plan_evidence(self.root, fully_gated_through("G7"))
        session.artifact_hashes.update(verify_g5_compilation(self.root))
        session.artifact_hashes["@toolkit/course-compiler"] = "0" * 64

        result = reconcile_artifacts(self.root, session, NOW)

        self.assertEqual(session.completed_gate_ids, ["G0", "G1", "G2", "G3", "G4"])
        self.assertEqual(result.earliest_invalidated_gate_id, "G5")

    def test_contract_snapshot_evidence_change_invalidates_g5_and_downstream(self):
        session = bind_current_page_plan_evidence(self.root, fully_gated_through("G7"))
        session.artifact_hashes.update(verify_g5_compilation(self.root))
        session.artifact_hashes["@toolkit/course-contract-snapshot"] = "0" * 64

        result = reconcile_artifacts(self.root, session, NOW)

        self.assertEqual(session.completed_gate_ids, ["G0", "G1", "G2", "G3", "G4"])
        self.assertEqual(result.earliest_invalidated_gate_id, "G5")


class PackageValidationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        build_full_package(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def validate(self):
        report = build_course_validation_report(self.root)
        write_current_validation_report(self.root, report)
        sync_validation_issues(self.root, report, NOW)
        return report

    def test_current_clear_report_allows_g6_and_stores_asset_hashes(self):
        self.validate()
        evidence = verify_g6_validation(self.root)
        session = fully_gated_through("G5")

        complete_gate(session, "G6", NOW, gate_evidence=evidence)

        self.assertIn(".course-work/course-validation-report.json", session.artifact_hashes)
        self.assertIn("@toolkit/course-package-validator", session.artifact_hashes)
        self.assertIn("@course/asset-set", session.artifact_hashes)
        self.assertIn(
            "@course/asset:assets/images/diagram.png",
            session.artifact_hashes,
        )

    def test_asset_change_invalidates_g6_and_downstream(self):
        session = bind_current_page_plan_evidence(self.root, fully_gated_through("G8"))
        self.validate()
        session.artifact_hashes.update(verify_g5_compilation(self.root))
        session.artifact_hashes.update(verify_g6_validation(self.root))
        (self.root / "course/assets/images/diagram.png").write_bytes(b"changed")

        result = reconcile_artifacts(self.root, session, NOW)

        self.assertEqual(
            session.completed_gate_ids,
            ["G0", "G1", "G2", "G3", "G4", "G5"],
        )
        self.assertEqual(result.earliest_invalidated_gate_id, "G6")

    def test_revalidated_asset_resolves_prior_change_warning(self):
        session = bind_current_page_plan_evidence(self.root, fully_gated_through("G8"))
        self.validate()
        session.artifact_hashes.update(verify_g5_compilation(self.root))
        session.artifact_hashes.update(verify_g6_validation(self.root))
        asset = self.root / "course/assets/images/diagram.png"
        asset.write_bytes(b"changed")

        first = reconcile_artifacts(self.root, session, NOW)
        second = reconcile_artifacts(self.root, session, NOW)

        target = {"path": "assets/images/diagram.png"}
        self.assertTrue(any(issue.target == target for issue in first.active_issues))
        self.assertFalse(any(issue.target == target for issue in second.active_issues))

    def test_unchanged_course_asset_does_not_invalidate_g6(self):
        session = bind_current_page_plan_evidence(self.root, fully_gated_through("G8"))
        self.validate()
        session.artifact_hashes.update(verify_g5_compilation(self.root))
        session.artifact_hashes.update(verify_g6_validation(self.root))

        result = reconcile_artifacts(self.root, session, NOW)

        self.assertNotIn(
            "@course/asset:assets/images/diagram.png",
            result.changed_paths,
        )
        self.assertNotEqual(result.earliest_invalidated_gate_id, "G6")
        self.assertIn("G6", session.completed_gate_ids)

    def test_validator_hash_change_invalidates_g6(self):
        session = bind_current_page_plan_evidence(self.root, fully_gated_through("G7"))
        self.validate()
        session.artifact_hashes.update(verify_g5_compilation(self.root))
        session.artifact_hashes.update(verify_g6_validation(self.root))
        session.artifact_hashes["@toolkit/course-package-validator"] = "0" * 64

        result = reconcile_artifacts(self.root, session, NOW)

        self.assertEqual(result.earliest_invalidated_gate_id, "G6")
        self.assertEqual(session.completed_gate_ids[-1], "G5")

    def test_nonblocking_warning_does_not_block_g6_evidence(self):
        blueprint_path = self.root / ".course-work/course-blueprint.json"
        blueprint = load_json(blueprint_path)
        blueprint["course"]["estimatedMinutes"] = 10
        write_json_atomic(blueprint_path, blueprint)
        from course_toolkit.course_compiler import (
            compile_blueprint,
            write_compilation_outputs_atomic,
        )

        write_compilation_outputs_atomic(self.root, compile_blueprint(blueprint))
        self.validate()

        store = IssueStore.load(self.root / ".course-work/issues.json")
        warning = next(
            issue
            for issue in store.all()
            if issue.code == "course-package-estimate-warning"
        )
        self.assertEqual(warning.status, "active")
        self.assertEqual(warning.warning_policy, "no-acknowledgement-required")
        self.assertIn("@course/asset-set", verify_g6_validation(self.root))

if __name__ == "__main__":
    unittest.main()
