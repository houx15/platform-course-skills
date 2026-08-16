import tempfile
import unittest
from pathlib import Path

from course_toolkit.issue_codes import get_issue_policy
from course_toolkit.issues import IssueStore, make_registered_issue


class IssuePolicyTests(unittest.TestCase):
    def test_registered_warning_carries_publish_ack_policy(self):
        policy = get_issue_policy("workflow-artifact-changed")

        self.assertEqual(policy.severity, "warning")
        self.assertEqual(
            policy.warning_policy,
            "no-acknowledgement-required",
        )

    def test_unknown_issue_code_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown issue code"):
            get_issue_policy("invented-by-a-skill")

    def test_unconfirmed_blueprint_is_a_g3_teacher_decision(self):
        policy = get_issue_policy("blueprint-unconfirmed")

        self.assertEqual(policy.severity, "decision-required")
        self.assertEqual(policy.default_gate_id, "G3")


class IssueStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / ".course-work" / "issues.json"
        self.store = IssueStore(self.path)

    def tearDown(self):
        self.temporary.cleanup()

    def make_issue(self, **overrides):
        values = {
            "code": "workflow-artifact-changed",
            "source": "workflow",
            "message": "changed",
            "gate_id": "G3",
            "seen_at": "2026-08-16T00:00:00Z",
            "target": {"path": ".course-work/course-blueprint.json"},
        }
        values.update(overrides)
        return make_registered_issue(**values)

    def test_upsert_deduplicates_by_fingerprint_and_updates_last_seen(self):
        first = self.store.upsert(
            self.make_issue(message="old", seen_at="2026-08-16T00:00:00Z")
        )
        second = self.store.upsert(
            self.make_issue(message="new", seen_at="2026-08-16T01:00:00Z")
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(len(self.store.all()), 1)
        self.assertEqual(self.store.all()[0].message, "new")
        self.assertEqual(
            self.store.all()[0].last_seen_at,
            "2026-08-16T01:00:00Z",
        )

    def test_blocker_cannot_be_accepted(self):
        blocker = self.store.upsert(
            self.make_issue(code="workflow-gate-prerequisite", gate_id="G0")
        )

        with self.assertRaisesRegex(ValueError, "cannot be accepted"):
            self.store.accept(blocker.id, rationale="ignore")

    def test_warning_without_acknowledgement_requirement_cannot_be_accepted(self):
        warning = self.store.upsert(self.make_issue())

        with self.assertRaisesRegex(ValueError, "cannot be accepted"):
            self.store.accept(warning.id, rationale="unnecessary acknowledgement")

    def test_issue_lifecycle_persists(self):
        issue = self.store.upsert(self.make_issue())
        self.store.resolve(issue.id, "2026-08-16T02:00:00Z")
        self.store.save()

        restored = IssueStore.load(self.path)

        self.assertEqual(restored.get(issue.id).status, "resolved")
        self.assertEqual(restored.get(issue.id).resolved_at, "2026-08-16T02:00:00Z")

    def test_upsert_reactivates_a_recurring_issue(self):
        issue = self.store.upsert(self.make_issue())
        self.store.resolve(issue.id, "2026-08-16T01:00:00Z")

        recurring = self.store.upsert(
            self.make_issue(seen_at="2026-08-16T02:00:00Z")
        )

        self.assertEqual(recurring.status, "active")
        self.assertIsNone(recurring.resolved_at)


if __name__ == "__main__":
    unittest.main()
