import tempfile
import unittest
from pathlib import Path

from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.issues import make_registered_issue
from course_toolkit.workflow import (
    ArtifactReconciliationResult,
    WorkflowError,
    complete_gate,
    hash_path,
    load_session,
    new_session,
    reconcile_artifacts,
    save_session,
    set_phase_status,
    workflow_summary,
)


NOW = "2026-08-16T00:00:00Z"


def fully_gated_through(gate_id):
    session = new_session("course-a", [], NOW)
    for index in range(int(gate_id[1:]) + 1):
        complete_gate(session, f"G{index}", NOW)
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

    def test_renderer_version_change_invalidates_preview_not_compilation(self):
        manifest = self.root / ".course-work" / "preview-manifest.json"
        write_json_atomic(manifest, {"rendererVersion": "1"})
        session = fully_gated_through("G8")
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


if __name__ == "__main__":
    unittest.main()
