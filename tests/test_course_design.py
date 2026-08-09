import subprocess
import copy
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
    course = minimal_course()["course"]
    return {
        "schemaVersion": "1.0",
        "teacherConfirmed": True,
        "courseFrame": {
            "teacherConfirmed": True,
            "introduction": copy.deepcopy(course["introduction"]),
            "conclusion": copy.deepcopy(course["conclusion"]),
            "sourceIds": ["source-1"],
            "objectiveAlignment": [
                {
                    "objectiveId": "explain-course-content",
                    "partIds": ["part-1"],
                    "evidenceBlockIds": ["course-content-response"],
                }
            ],
            "pendingConfirmations": [],
        },
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
                        "modalities": ["fillBlank", "text"],
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
    "courseIntroduction",
    "courseConclusion",
    "images",
    "pdf",
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
        self.assertIn("## 课程首尾设计", rendered)
        self.assertIn("| 课程目标 |", rendered)
        self.assertLess(rendered.index("## 课程首尾设计"), rendered.index("## Part/Piece 设计"))
        self.assertIn("共 1 个 Part、1 个 Piece", rendered)
        self.assertIn("| Part / Piece | Part 阶段目标 | 学生看到什么 |", rendered)
        self.assertEqual(rendered.count("| part-1 / piece-1 |"), 1)

    def test_storyboard_compacts_long_course_frame_source_list(self):
        data = valid_storyboard()
        data["courseFrame"]["sourceIds"] = [f"source-{index}" for index in range(12)]

        rendered = render_storyboard(data)

        self.assertIn("共 12 项来源", rendered)
        self.assertIn("source-0", rendered)
        self.assertNotIn("source-11", rendered)

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

    def test_storyboard_requires_confirmed_course_frame(self):
        data = valid_storyboard()
        data["courseFrame"]["teacherConfirmed"] = False
        data["courseFrame"]["pendingConfirmations"] = ["确认课程总结"]

        codes = {issue.code for issue in validate_storyboard(data, minimal_course())}

        self.assertIn("teacher-confirmation-required", codes)
        self.assertIn("pending-confirmation", codes)

    def test_storyboard_course_frame_must_match_course(self):
        data = valid_storyboard()
        data["courseFrame"]["introduction"]["overview"] = "旧版本介绍"

        codes = {issue.code for issue in validate_storyboard(data, minimal_course())}

        self.assertIn("course-frame-drift", codes)

    def test_course_frame_sources_must_exist_in_extracted_materials(self):
        data = valid_storyboard()
        data["courseFrame"]["sourceIds"] = ["source-missing"]

        codes = {
            issue.code
            for issue in validate_storyboard(data, minimal_course(), {"source-1"})
        }

        self.assertIn("unknown-course-frame-source", codes)

    def test_objective_alignment_requires_real_part_and_evidence_block(self):
        cases = (
            ("partIds", ["missing-part"], "unknown-objective-part"),
            ("evidenceBlockIds", ["missing-block"], "unknown-objective-evidence"),
            ("evidenceBlockIds", ["intro"], "invalid-objective-evidence"),
        )
        for field, value, expected in cases:
            data = valid_storyboard()
            data["courseFrame"]["objectiveAlignment"][0][field] = value
            with self.subTest(field=field, expected=expected):
                codes = {
                    issue.code for issue in validate_storyboard(data, minimal_course())
                }
                self.assertIn(expected, codes)

    def test_objective_evidence_must_belong_to_an_aligned_part(self):
        course = minimal_course()
        course["course"]["parts"].append(
            {
                "id": "part-2",
                "title": "第二部分",
                "pieces": [
                    {
                        "id": "piece-2",
                        "title": "第二内容块",
                        "blocks": [
                            {
                                "id": "part-2-response",
                                "type": "fillBlank",
                                "blocking": True,
                                "prompt": "说明第二部分的内容。",
                                "assessment": {
                                    "mode": "reflection",
                                    "rubric": "回答应说明第二部分的关键内容。",
                                },
                            }
                        ],
                    }
                ],
            }
        )
        data = valid_storyboard()
        data["summary"] = {"partCount": 2, "pieceCount": 2}
        data["parts"].append(
            {
                "id": "part-2",
                "title": "第二部分",
                "stageGoal": "理解第二部分",
                "pieces": [
                    {
                        "id": "piece-2",
                        "title": "第二内容块",
                        "studentSees": "第二部分完整内容",
                        "teachingFocus": "第二部分重点",
                        "modalities": ["fillBlank"],
                        "studentAction": "完成第二部分练习",
                        "completion": "提交说明",
                        "sourceIds": ["source-2"],
                        "assetNeeds": [],
                        "pendingConfirmations": [],
                    }
                ],
            }
        )
        data["courseFrame"]["objectiveAlignment"][0]["evidenceBlockIds"] = [
            "part-2-response"
        ]

        codes = {issue.code for issue in validate_storyboard(data, course)}

        self.assertIn("objective-evidence-part-mismatch", codes)

    def test_every_course_objective_has_exactly_one_alignment(self):
        for alignments, expected in (
            ([], "missing-objective-alignment"),
            (
                valid_storyboard()["courseFrame"]["objectiveAlignment"] * 2,
                "duplicate-objective-alignment",
            ),
        ):
            data = valid_storyboard()
            data["courseFrame"]["objectiveAlignment"] = alignments
            with self.subTest(expected=expected):
                codes = {
                    issue.code for issue in validate_storyboard(data, minimal_course())
                }
                self.assertIn(expected, codes)

    def test_storyboard_accepts_pdf_modality_that_matches_course(self):
        course = minimal_course()
        course["course"]["parts"][0]["pieces"][0]["blocks"] = [
            {
                "id": "source-paper",
                "type": "pdf",
                "title": "研究论文原文（结构测试材料）",
                "source": "assets/pdfs/source-paper.pdf",
            },
            {
                "id": "course-content-response",
                "type": "fillBlank",
                "blocking": True,
                "prompt": "请说明这份论文材料如何支持课程内容。",
                "assessment": {
                    "mode": "reflection",
                    "rubric": "回答应引用论文材料中的具体内容。",
                },
            },
        ]
        storyboard = valid_storyboard()
        storyboard["parts"][0]["pieces"][0]["modalities"] = ["fillBlank", "pdf"]
        storyboard["parts"][0]["pieces"][0][
            "studentSees"
        ] = "一份可以翻阅和下载的完整结构测试 PDF"
        storyboard["parts"][0]["pieces"][0][
            "studentAction"
        ] = "打开完整文档并定位其标题和章节结构"

        self.assertEqual(validate_storyboard(storyboard, course), [])


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
        self.assertIn("| courseIntroduction |", rendered)
        self.assertIn("| courseConclusion |", rendered)
        self.assertIn("| pdf |", rendered)

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

    def test_missing_pdf_overall_check_blocks_uploadable_claim(self):
        report = valid_review_report()
        del report["overallChecks"]["pdf"]
        issues = validate_review_report(report, minimal_course())
        codes = {issue.code for issue in issues}
        self.assertIn("missing-overall-check", codes)
        self.assertIn("invalid-uploadable-claim", codes)

    def test_missing_course_frame_overall_checks_block_uploadable_claim(self):
        for check in ("courseIntroduction", "courseConclusion"):
            report = valid_review_report()
            del report["overallChecks"][check]
            with self.subTest(check=check):
                codes = {
                    issue.code
                    for issue in validate_review_report(report, minimal_course())
                }
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
