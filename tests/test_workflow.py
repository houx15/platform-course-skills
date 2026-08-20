import tempfile
import unittest
from pathlib import Path

from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.issues import IssueStore, make_registered_issue
from course_toolkit.workflow import (
    ArtifactReconciliationResult,
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
    save_session,
    set_phase_status,
    workflow_summary,
    verify_g5_compilation,
    verify_g6_validation,
)
from course_toolkit.course_package_validation import (
    build_course_validation_report,
    sync_validation_issues,
    write_current_validation_report,
)
from tests.test_course_package_validation import build_full_package


NOW = "2026-08-16T00:00:00Z"


def fully_gated_through(gate_id):
    session = new_session("course-a", [], NOW)
    for index in range(int(gate_id[1:]) + 1):
        if index == 5:
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

    def test_blueprint_change_invalidates_g3_and_downstream_only(self):
        blueprint = self.root / ".course-work" / "course-blueprint.json"
        write_json_atomic(blueprint, {"title": "new"})
        session = fully_gated_through("G8")
        session.artifact_hashes[".course-work/course-blueprint.json"] = "old"

        result = reconcile_artifacts(self.root, session, NOW)

        self.assertIsInstance(result, ArtifactReconciliationResult)
        self.assertEqual(session.completed_gate_ids, ["G0", "G1", "G2"])
        self.assertIn("G3", session.invalidated_gate_ids)
        self.assertEqual(session.phase, "course-design")
        self.assertEqual(result.earliest_invalidated_gate_id, "G3")

    def test_revalidated_artifact_resolves_prior_change_warning(self):
        blueprint = self.root / ".course-work" / "course-blueprint.json"
        write_json_atomic(blueprint, {"title": "new"})
        session = fully_gated_through("G8")
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
        session = fully_gated_through("G8")
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
        session = fully_gated_through("G9")
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

    def test_blueprint_change_invalidates_completed_g3_and_downstream(self):
        session = fully_gated_through("G5")
        session.artifact_hashes.update(verify_g5_compilation(self.root))
        blueprint_path = self.root / ".course-work" / "course-blueprint.json"
        blueprint = load_json(blueprint_path)
        blueprint["course"]["title"] = "Changed blueprint"
        write_json_atomic(blueprint_path, blueprint)

        reconcile_artifacts(self.root, session, NOW)

        self.assertEqual(session.completed_gate_ids, ["G0", "G1", "G2"])
        self.assertEqual(session.phase, "course-design")

    def test_compiler_evidence_change_invalidates_g5_and_downstream(self):
        session = fully_gated_through("G7")
        session.artifact_hashes.update(verify_g5_compilation(self.root))
        session.artifact_hashes["@toolkit/course-compiler"] = "0" * 64

        result = reconcile_artifacts(self.root, session, NOW)

        self.assertEqual(session.completed_gate_ids, ["G0", "G1", "G2", "G3", "G4"])
        self.assertEqual(result.earliest_invalidated_gate_id, "G5")

    def test_contract_snapshot_evidence_change_invalidates_g5_and_downstream(self):
        session = fully_gated_through("G7")
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
        self.validate()
        session = fully_gated_through("G8")
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
        self.validate()
        session = fully_gated_through("G8")
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
        self.validate()
        session = fully_gated_through("G8")
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
        self.validate()
        session = fully_gated_through("G7")
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
