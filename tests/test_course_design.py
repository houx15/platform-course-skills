import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from course_toolkit.course_design import (
    render_review_report,
    render_storyboard,
    validate_audience_classification,
    validate_learner_facing_course,
    validate_review_report,
    validate_storyboard,
)
from tests.helpers import minimal_course
from course_toolkit.jsonio import dump_json


def valid_audience_classification():
    return {
        "schemaVersion": "1.0",
        "teacherConfirmed": True,
        "groups": [
            {
                "audience": "student-core",
                "sourceIds": ["source-1"],
                "summary": "学生需要理解的核心概念",
                "disposition": "storyboard",
            },
            {
                "audience": "teacher-design",
                "sourceIds": ["source-2"],
                "summary": "教师对课堂组织方式的说明",
                "disposition": "work-record",
            },
        ],
    }


def valid_storyboard():
    return {
        "schemaVersion": "1.0",
        "teacherConfirmed": True,
        "summary": {
            "partCount": 1,
            "pieceCount": 1,
        },
        "parts": [
            {
                "id": "part-1",
                "title": "第一部分",
                "stageGoal": "建立课程所需的核心认识",
                "pieces": [
                    {
                        "id": "piece-1",
                        "title": "第一内容块",
                        "studentSees": "一个简洁的概念说明",
                        "teachingFocus": "辨认概念的关键特征",
                        "modalities": ["text"],
                        "studentAction": "阅读后用自己的话复述",
                        "completion": "能够准确说出关键特征",
                        "sourceIds": ["source-1"],
                        "assetNeeds": [],
                        "pendingConfirmations": [],
                    }
                ],
            }
        ],
    }


REVIEW_DIMENSIONS = (
    "instructionalGoalStructure",
    "contentCompleteness",
    "studentFacingPresentation",
    "modalityChoice",
    "practiceFeedback",
    "resourcesFormat",
)
OVERALL_CHECKS = (
    "allPartsPass",
    "sourceClassificationCoverage",
    "resourcesPresent",
    "courseJsonSchema",
    "indexConsistency",
    "images",
    "video",
    "html",
    "assessments",
    "unresolved",
)


def valid_review_report():
    return {
        "schemaVersion": "1.0",
        "partReviews": [
            {
                "partId": "part-1",
                "partTitle": "第一部分",
                "dimensions": {
                    key: {
                        "status": "pass",
                        "evidence": f"{key} 已核查",
                    }
                    for key in REVIEW_DIMENSIONS
                },
                "conclusion": "pass",
                "recommendations": [],
            }
        ],
        "overallChecks": {
            key: {
                "status": "pass",
                "evidence": f"{key} 已核查",
            }
            for key in OVERALL_CHECKS
        },
        "finalStatus": "uploadable",
    }


class AudienceClassificationTests(unittest.TestCase):
    def test_complete_grouped_classification_passes(self):
        issues = validate_audience_classification(
            valid_audience_classification(),
            {"source-1", "source-2"},
        )
        self.assertEqual(issues, [])

    def test_teacher_must_confirm_grouped_classification(self):
        data = valid_audience_classification()
        data["teacherConfirmed"] = False
        issues = validate_audience_classification(data, {"source-1", "source-2"})
        self.assertIn("teacher-confirmation-required", {issue.code for issue in issues})

    def test_every_source_is_classified_once(self):
        data = valid_audience_classification()
        data["groups"][1]["sourceIds"] = ["source-1"]
        issues = validate_audience_classification(data, {"source-1", "source-2"})
        codes = {issue.code for issue in issues}
        self.assertIn("duplicate-source", codes)
        self.assertIn("missing-source-classification", codes)


class StoryboardTests(unittest.TestCase):
    def test_storyboard_matches_course_and_renders_one_row_per_piece(self):
        data = valid_storyboard()
        issues = validate_storyboard(data, minimal_course())
        self.assertEqual(issues, [])
        rendered = render_storyboard(data)
        self.assertIn("共 1 个 Part、1 个 Piece", rendered)
        self.assertIn("| Part / Piece | Part 阶段目标 | 学生看到什么 |", rendered)
        self.assertEqual(rendered.count("| part-1 / piece-1 |"), 1)

    def test_storyboard_rejects_modality_that_does_not_match_course(self):
        data = valid_storyboard()
        data["parts"][0]["pieces"][0]["modalities"] = ["images"]
        issues = validate_storyboard(data, minimal_course())
        self.assertIn("modality-mismatch", {issue.code for issue in issues})

    def test_storyboard_requires_teacher_confirmation(self):
        data = valid_storyboard()
        data["teacherConfirmed"] = False
        issues = validate_storyboard(data, minimal_course())
        self.assertIn("teacher-confirmation-required", {issue.code for issue in issues})


class LearnerFacingBoundaryTests(unittest.TestCase):
    def test_course_rejects_design_metadata_in_learner_content(self):
        data = minimal_course()
        data["course"]["parts"][0]["pieces"][0]["title"] = "设计思路"
        data["course"]["parts"][0]["pieces"][0]["blocks"][0][
            "content"
        ] = "AI 角色负责判断老师和系统如何分工。"
        issues = validate_learner_facing_course(data)
        self.assertIn("non-learner-content", {issue.code for issue in issues})


class ReviewReportTests(unittest.TestCase):
    def test_complete_review_matches_every_part_and_renders_two_tables(self):
        report = valid_review_report()
        issues = validate_review_report(report, minimal_course())
        self.assertEqual(issues, [])
        rendered = render_review_report(report)
        self.assertIn("## Part 逐项 Review", rendered)
        self.assertIn("## 整体 Review", rendered)
        self.assertIn("| part-1 | 第一部分 |", rendered)
        self.assertIn("| courseJsonSchema |", rendered)

    def test_missing_part_dimension_blocks_uploadable_claim(self):
        report = valid_review_report()
        del report["partReviews"][0]["dimensions"]["modalityChoice"]
        issues = validate_review_report(report, minimal_course())
        codes = {issue.code for issue in issues}
        self.assertIn("missing-review-dimension", codes)
        self.assertIn("invalid-uploadable-claim", codes)

    def test_failed_part_cannot_conclude_pass_or_uploadable(self):
        report = valid_review_report()
        report["partReviews"][0]["dimensions"]["contentCompleteness"][
            "status"
        ] = "revise"
        issues = validate_review_report(report, minimal_course())
        codes = {issue.code for issue in issues}
        self.assertIn("invalid-part-conclusion", codes)
        self.assertIn("invalid-uploadable-claim", codes)

    def test_missing_overall_check_blocks_uploadable_claim(self):
        report = valid_review_report()
        del report["overallChecks"]["resourcesPresent"]
        issues = validate_review_report(report, minimal_course())
        codes = {issue.code for issue in issues}
        self.assertIn("missing-overall-check", codes)
        self.assertIn("invalid-uploadable-claim", codes)


class RenderingCliTests(unittest.TestCase):
    def run_script(self, name, data, output_name):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            output = root / output_name
            source.write_text(dump_json(data), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / "scripts" / name),
                    str(source),
                    "--output",
                    str(output),
                ],
                text=True,
                capture_output=True,
            )
            return result, output.read_text(encoding="utf-8") if output.exists() else ""

    def test_storyboard_renderer_cli(self):
        result, rendered = self.run_script(
            "render-course-storyboard.py",
            valid_storyboard(),
            "course-storyboard.md",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("课程设计确认表", rendered)

    def test_review_renderer_cli(self):
        result, rendered = self.run_script(
            "render-review-report.py",
            valid_review_report(),
            "review-report.md",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Part 逐项 Review", rendered)


if __name__ == "__main__":
    unittest.main()
