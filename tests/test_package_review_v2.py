import copy
import tempfile
import unittest
from pathlib import Path

from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.package_review import (
    V2ReviewBlocked,
    prepare_v2_review,
    verify_g8_review,
    write_v2_review_report,
)
from course_toolkit.preview_evidence import record_preview_evidence
from tests.test_publication_manifest import NOW, prepare_g6


def approve(report: dict) -> dict:
    approved = copy.deepcopy(report)
    approved["status"] = "publishable"
    approved["reviewedAt"] = NOW
    for part in approved["parts"]:
        part["status"] = "pass"
        for dimension in part["dimensions"].values():
            dimension.update(status="pass", evidence="Independently checked against the source and current preview.")
        for slice_review in part["slices"]:
            slice_review["status"] = "pass"
            for check in slice_review["checks"].values():
                check.update(status="pass", evidence="Current definition and renderer behavior are coherent.")
    for objective in approved["objectives"]:
        objective.update(status="pass", evidence="Evidence blocks are inside objective-aligned Parts and collect a result.")
    for check in approved["overallChecks"].values():
        check.update(status="pass", evidence="Checked independently against current hash-bound evidence.")
    return approved


class CourseDefinitionTwoReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        write_json_atomic(self.root / ".course-work/decisions.json", {"schemaVersion": "1.0", "decisions": []})
        write_json_atomic(self.root / ".course-work/unresolved.json", {"schemaVersion": "1.0", "items": []})
        prepare_g6(self.root, instructional_evidence=True)
        document = load_json(self.root / "course/course.json")
        slices = [slice_data["id"] for part in document["course"]["parts"] for slice_data in part["slices"]]
        record_preview_evidence(
            self.root,
            {
                "viewport": {"width": 1440, "height": 900},
                "visitedSliceIds": slices,
                "exercisedEvents": [],
                "runtimeErrors": [],
                "teacherConfirmed": True,
                "completedAt": NOW,
            },
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_current_independent_report_can_satisfy_g8(self):
        report = prepare_v2_review(self.root)
        write_v2_review_report(self.root, approve(report))

        evidence = verify_g8_review(self.root)

        self.assertIn(".course-work/review-report.json", evidence)
        self.assertEqual(report["schemaVersion"], "2.0")
        self.assertEqual(report["courseDefinitionSchemaVersion"], "2.0")

    def test_legacy_report_cannot_certify_course_definition_two(self):
        report = approve(prepare_v2_review(self.root))
        report["schemaVersion"] = "1.0"
        write_json_atomic(self.root / ".course-work/review-report.json", report)

        with self.assertRaisesRegex(V2ReviewBlocked, "schemaVersion 2.0"):
            verify_g8_review(self.root)

    def test_stale_preview_or_definition_blocks_review(self):
        report = approve(prepare_v2_review(self.root))
        report["definitionHash"] = "0" * 64
        write_v2_review_report(self.root, report)

        with self.assertRaisesRegex(V2ReviewBlocked, "definition hash"):
            verify_g8_review(self.root)

    def test_missing_part_dimension_blocks_review(self):
        report = approve(prepare_v2_review(self.root))
        first_dimension = next(iter(report["parts"][0]["dimensions"].values()))
        first_dimension.update(status="revise", evidence="Workflow branch was not exercised.")
        write_v2_review_report(self.root, report)

        with self.assertRaisesRegex(V2ReviewBlocked, "Part dimension"):
            verify_g8_review(self.root)

    def test_objective_evidence_must_match_current_definition(self):
        report = approve(prepare_v2_review(self.root))
        report["objectives"][0]["evidenceBlockIds"] = ["invented-block"]
        write_v2_review_report(self.root, report)

        with self.assertRaisesRegex(V2ReviewBlocked, "objective evidence"):
            verify_g8_review(self.root)


if __name__ == "__main__":
    unittest.main()
