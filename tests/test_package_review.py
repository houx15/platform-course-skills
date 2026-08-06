import json
import shutil
import tempfile
import unittest
from pathlib import Path

from course_toolkit.jsonio import dump_json, load_json
from course_toolkit.package_review import review_package
from tests.helpers import ROOT


class PackageReviewTests(unittest.TestCase):
    def copy_valid(self, root: Path) -> Path:
        target = root / "course"
        shutil.copytree(ROOT / "tests" / "fixtures" / "valid-course", target)
        return target

    def test_valid_fixture_is_uploadable(self):
        result = review_package(ROOT / "tests" / "fixtures" / "valid-course")
        self.assertEqual(result.status, "uploadable")
        self.assertEqual(result.issues, ())

    def test_missing_course_json_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = review_package(Path(tmp))
        self.assertEqual(result.status, "blocked")
        self.assertIn("missing-file", {issue.code for issue in result.issues})

    def test_missing_resource_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.copy_valid(Path(tmp))
            (course / "assets" / "images" / "example.svg").unlink()
            result = review_package(course)
        self.assertEqual(result.status, "blocked")
        self.assertIn("missing-file", {issue.code for issue in result.issues})

    def test_generated_markdown_drift_needs_fix(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.copy_valid(Path(tmp))
            (course / "index.md").write_text("# drift\n", encoding="utf-8")
            result = review_package(course)
        self.assertEqual(result.status, "uploadable-after-fixes")
        self.assertIn("generated-view-drift", {issue.code for issue in result.issues})

    def test_unresolved_coverage_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course = self.copy_valid(root)
            work = root / ".course-work"
            work.mkdir()
            (work / "source-coverage.json").write_text(
                dump_json(
                    {
                        "items": [
                            {"sourceId": "source-1", "status": "unresolved"}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (work / "decisions.json").write_text(
                dump_json({"decisions": []}),
                encoding="utf-8",
            )
            result = review_package(course, work)
        self.assertEqual(result.status, "blocked")
        self.assertIn("unresolved", {issue.code for issue in result.issues})

    def test_unconfirmed_substantive_decision_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course = self.copy_valid(root)
            work = root / ".course-work"
            work.mkdir()
            (work / "source-coverage.json").write_text(
                dump_json({"items": []}),
                encoding="utf-8",
            )
            (work / "decisions.json").write_text(
                dump_json(
                    {
                        "decisions": [
                            {
                                "id": "decision-1",
                                "substantive": True,
                                "teacherConfirmed": False,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            result = review_package(course, work)
        self.assertIn(
            "unconfirmed-decision",
            {issue.code for issue in result.issues},
        )

    def test_zip_files_do_not_affect_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.copy_valid(Path(tmp))
            (course / "unused.zip").write_bytes(b"not a real zip")
            result = review_package(course)
        self.assertEqual(result.status, "uploadable")

    def test_issue_order_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.copy_valid(Path(tmp))
            data = load_json(course / "course.json")
            data["course"]["parts"][0]["pieces"][0]["blocks"][1]["items"][0][
                "source"
            ] = "../bad.svg"
            data["course"]["id"] = "Bad ID"
            (course / "course.json").write_text(dump_json(data), encoding="utf-8")
            result = review_package(course)
        keys = [(issue.path, issue.code, issue.message) for issue in result.issues]
        self.assertEqual(keys, sorted(keys))

    def test_work_review_reconciles_extracted_sources_and_real_destinations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course = self.copy_valid(root)
            work = root / ".course-work"
            work.mkdir()
            extracted = {
                "items": [
                    {
                        "sourceId": "source-1",
                        "sourceFile": "lesson.docx",
                        "location": "paragraph:1",
                        "kind": "paragraph",
                        "text": "开场",
                    },
                    {
                        "sourceId": "source-2",
                        "sourceFile": "lesson.docx",
                        "location": "paragraph:2",
                        "kind": "paragraph",
                        "text": "结尾",
                    },
                ],
                "ignored": [],
                "unsupported": [],
                "errors": [],
            }
            coverage = {
                "schemaVersion": "1.0",
                "items": [
                    {
                        "sourceId": "source-1",
                        "sourceFile": "lesson.docx",
                        "location": "paragraph:1",
                        "summary": "开场",
                        "status": "mapped",
                        "destinations": ["part-1/piece-1/intro-text"],
                    },
                    {
                        "sourceId": "source-extra",
                        "sourceFile": "lesson.docx",
                        "location": "paragraph:99",
                        "summary": "不存在",
                        "status": "mapped",
                        "destinations": ["part-1/piece-1/not-a-block"],
                    },
                ],
            }
            (work / "materials-extracted.json").write_text(
                dump_json(extracted),
                encoding="utf-8",
            )
            (work / "source-coverage.json").write_text(
                dump_json(coverage),
                encoding="utf-8",
            )
            (work / "decisions.json").write_text(
                dump_json({"decisions": []}),
                encoding="utf-8",
            )

            result = review_package(course, work)

        codes = {issue.code for issue in result.issues}
        self.assertIn("missing-source-coverage", codes)
        self.assertIn("unknown-source", codes)
        self.assertIn("unknown-destination", codes)

    def test_open_blocking_unresolved_item_blocks_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course = self.copy_valid(root)
            work = root / ".course-work"
            work.mkdir()
            (work / "materials-extracted.json").write_text(
                dump_json({"items": [], "ignored": [], "unsupported": [], "errors": []}),
                encoding="utf-8",
            )
            (work / "source-coverage.json").write_text(
                dump_json({"schemaVersion": "1.0", "items": []}),
                encoding="utf-8",
            )
            (work / "decisions.json").write_text(
                dump_json({"schemaVersion": "1.0", "decisions": []}),
                encoding="utf-8",
            )
            (work / "unresolved.json").write_text(
                dump_json(
                    {
                        "schemaVersion": "1.0",
                        "items": [
                            {
                                "id": "missing-video",
                                "status": "open",
                                "blocking": True,
                                "summary": "最终 MP4 尚未提供",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (work / "session.json").write_text(
                dump_json({"schemaVersion": "1.0", "state": "review"}),
                encoding="utf-8",
            )

            result = review_package(course, work)

        self.assertIn("unresolved-item", {issue.code for issue in result.issues})


if __name__ == "__main__":
    unittest.main()
