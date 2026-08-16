import tempfile
import unittest
from pathlib import Path

from course_toolkit.decisions import DecisionStore


class DecisionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / ".course-work" / "decisions.json"
        self.store = DecisionStore(self.path)

    def tearDown(self):
        self.temporary.cleanup()

    def test_request_creates_pending_decision_with_context(self):
        decision = self.store.request(
            "d-objective",
            "Which objective?",
            "hash-a",
            context={"source": "materials/index.md"},
            options=("Compare evidence", "Summarize evidence"),
            affected_artifact_ids=("course-brief",),
            requested_at="2026-08-16T00:00:00Z",
        )

        self.assertEqual(decision.status, "pending")
        self.assertEqual(decision.context_hash, "hash-a")
        self.assertEqual(decision.affected_artifact_ids, ("course-brief",))

    def test_confirmed_decision_cannot_be_silently_reanswered(self):
        self.store.request("d-objective", "Which objective?", "hash-a")
        self.store.confirm(
            "d-objective", "Compare evidence", "2026-08-16T00:00:00Z"
        )

        with self.assertRaisesRegex(ValueError, "already confirmed"):
            self.store.confirm(
                "d-objective", "Summarize evidence", "2026-08-16T01:00:00Z"
            )

    def test_confirmed_decision_is_invalidated_by_new_context_hash(self):
        self.store.request("d-objective", "Which objective?", "hash-a")
        self.store.confirm(
            "d-objective", "Compare evidence", "2026-08-16T00:00:00Z"
        )

        invalidated = self.store.reconcile_context(
            "d-objective", "hash-b", "2026-08-16T01:00:00Z"
        )

        self.assertTrue(invalidated)
        self.assertEqual(self.store.get("d-objective").status, "invalidated")

    def test_same_context_does_not_invalidate_confirmed_decision(self):
        self.store.request("d-objective", "Which objective?", "hash-a")
        self.store.confirm(
            "d-objective", "Compare evidence", "2026-08-16T00:00:00Z"
        )

        invalidated = self.store.reconcile_context(
            "d-objective", "hash-a", "2026-08-16T01:00:00Z"
        )

        self.assertFalse(invalidated)
        self.assertEqual(self.store.get("d-objective").status, "confirmed")

    def test_unknown_decision_cannot_be_confirmed(self):
        with self.assertRaisesRegex(ValueError, "Unknown decision"):
            self.store.confirm("missing", "answer", "2026-08-16T00:00:00Z")

    def test_empty_answer_cannot_confirm_a_decision(self):
        self.store.request("d-objective", "Which objective?", "hash-a")

        with self.assertRaisesRegex(ValueError, "answer is required"):
            self.store.confirm("d-objective", "", "2026-08-16T00:00:00Z")

    def test_store_round_trips_all_fields(self):
        self.store.request(
            "d-objective",
            "Which objective?",
            "hash-a",
            context={"source": "materials/index.md"},
            options=("Compare evidence",),
            affected_artifact_ids=("course-brief",),
            requested_at="2026-08-16T00:00:00Z",
        )
        self.store.confirm(
            "d-objective", "Compare evidence", "2026-08-16T01:00:00Z"
        )
        self.store.save()

        restored = DecisionStore.load(self.path).get("d-objective")

        self.assertEqual(restored.answer, "Compare evidence")
        self.assertEqual(restored.context, {"source": "materials/index.md"})
        self.assertEqual(restored.decided_at, "2026-08-16T01:00:00Z")


if __name__ == "__main__":
    unittest.main()
