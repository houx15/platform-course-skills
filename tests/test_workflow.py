import tempfile
import unittest
from pathlib import Path

from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.issues import make_registered_issue
from course_toolkit.workflow import (
    WorkflowError,
    complete_gate,
    load_session,
    new_session,
    save_session,
    set_phase_status,
    workflow_summary,
)


NOW = "2026-08-16T00:00:00Z"


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

    def test_load_rejects_noncontiguous_completed_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = new_session("course-a", [], NOW)
            data = session.as_dict()
            data["completedGateIds"] = ["G0", "G2"]
            write_json_atomic(root / ".course-work" / "session.json", data)

            with self.assertRaisesRegex(ValueError, "contiguous"):
                load_session(root)


if __name__ == "__main__":
    unittest.main()
