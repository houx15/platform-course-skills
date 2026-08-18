import json
import re
import unittest
from pathlib import Path

from tests.helpers import ROOT


class SkillPackageTests(unittest.TestCase):
    def assert_skill(self, name):
        scenario_path = ROOT / "tests" / "skill_scenarios" / f"{name}.json"
        if not scenario_path.is_file():
            self.skipTest(f"scenario not started: {name}")
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
        skill_path = ROOT / "skills" / name / "SKILL.md"
        self.assertTrue(skill_path.is_file(), f"missing skill: {skill_path}")
        text = skill_path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        self.assertIsNotNone(match, f"missing frontmatter: {skill_path}")
        frontmatter = match.group(1)
        self.assertIn(f"name: {name}", frontmatter)
        self.assertRegex(frontmatter, r"(?m)^description: Use when ")
        for phrase in scenario["requiredPhrases"]:
            self.assertIn(phrase, text, f"{name} missing phrase: {phrase}")
        self.assertNotRegex(text, r"\b(?:TODO|TBD|PLACEHOLDER)\b")

    def test_analyze_course_materials(self):
        self.assert_skill("analyze-course-materials")

    def test_design_course_html(self):
        self.assert_skill("design-course-html")

    def test_design_video_interactions(self):
        self.assert_skill("design-video-interactions")

    def test_review_platform_course(self):
        self.assert_skill("review-platform-course")

    def test_build_platform_course(self):
        self.assert_skill("build-platform-course")

    def test_design_course_blueprint(self):
        self.assert_skill("design-course-blueprint")

    def test_preview_platform_course(self):
        self.assert_skill("preview-platform-course")

    def test_publish_platform_course(self):
        self.assert_skill("publish-platform-course")

    def test_apply_preview_feedback(self):
        self.assert_skill("apply-preview-feedback")

    def test_build_platform_course_routes_all_work_through_persistent_gates(self):
        skill_path = ROOT / "skills" / "build-platform-course" / "SKILL.md"
        workflow_path = (
            ROOT
            / "skills"
            / "build-platform-course"
            / "references"
            / "workflow.md"
        )
        skill = skill_path.read_text(encoding="utf-8")
        workflow = workflow_path.read_text(encoding="utf-8")
        combined = f"{skill}\n{workflow}"

        required = (
            "only teacher-facing entry",
            "status ROOT --json",
            "reconcile ROOT --json",
            "before any analysis or generation",
            "G0–G10",
            "cannot be skipped",
            "earliest incomplete or invalidated gate",
            "semantic changes require teacher confirmation",
            "CourseDefinition 2.0",
            "current implementation boundary",
            "annotations invalidate G8 and G9",
            "dry run",
            "explicit publication approval",
            "local completion never implies upload, POST, or publication",
            "G10 requires the real publication adapter",
        )
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, combined)

        for gate_index in range(11):
            with self.subTest(gate=f"G{gate_index}"):
                self.assertIn(f"G{gate_index}", workflow)

        self.assertNotIn("### 1. `materials-intake`", workflow)

    def test_build_platform_course_uses_blueprint_as_authoring_truth(self):
        skill_path = ROOT / "skills" / "build-platform-course" / "SKILL.md"
        workflow_path = (
            ROOT
            / "skills"
            / "build-platform-course"
            / "references"
            / "workflow.md"
        )
        combined = "\n".join(
            [
                skill_path.read_text(encoding="utf-8"),
                workflow_path.read_text(encoding="utf-8"),
            ]
        )
        required = (
            ".course-work/course-blueprint.json",
            "authoring source of truth",
            "import-legacy-course.py",
            "does not carry forward legacy approval",
            "compile-course.py",
            "never hand edit `course/course.json`",
            "shared student Zod contract",
            "current compilation hashes",
            "validate-course-v2.py",
            "complete-gate ROOT G6",
            "accept-warning",
            "course-validation-report.json",
            "manage-annotations.py reconcile",
            "annotation-revision-plan.json",
            "manage-annotations.py prepare",
            "confirm-decision",
            "manage-annotations.py apply",
            "applied annotations remain unverified",
            "student renderer",
            "browser preview",
            "OSS",
            "real course POST",
            "publish-course.py init-state",
            "publication-preflight.json",
            "stable slug",
            "no second blind create",
            "publish-course.py execute",
            "live publication adapter",
        )
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, combined)

        self.assertNotIn(
            "the repository still generates legacy `schemaVersion: 1.1`",
            combined,
        )
        self.assertNotIn("still being added", combined)

    def test_build_platform_course_follows_the_teachers_language(self):
        skill_path = ROOT / "skills" / "build-platform-course" / "SKILL.md"
        skill = skill_path.read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        required = (
            "跟随老师当前使用的语言",
            "老师使用中文时",
            "澄清问题、设计表、批注处理、检查结果和发布计划",
            "内部字段名、稳定 ID、文件路径和命令",
        )
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, skill)

        self.assertIn("老师只需要用中文自然交流", readme)
        self.assertIn("不需要把批注或确认翻译成英文", readme)

    def test_teacher_credentials_are_stored_without_command_line_work(self):
        build_skill = (
            ROOT / "skills" / "build-platform-course" / "SKILL.md"
        ).read_text(encoding="utf-8")
        publish_skill = (
            ROOT / "skills" / "publish-platform-course" / "SKILL.md"
        ).read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        combined = "\n".join((build_skill, publish_skill, readme))

        for phrase in (
            "课程目录的 `.env`",
            "老师不需要执行命令",
            "不得回显凭证",
            "`.env.example`",
            "进程环境变量优先",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, combined)

    def test_pdf_rules_are_consistent_across_skill_references(self):
        required = {
            ROOT
            / "skills"
            / "build-platform-course"
            / "references"
            / "course-contract.md": (
                "assets/pdfs/",
                "`pdf`",
                "不得包含 `blocking`",
            ),
            ROOT
            / "skills"
            / "build-platform-course"
            / "references"
            / "workflow.md": ("完整 PDF", "blocking: true"),
            ROOT
            / "skills"
            / "review-platform-course"
            / "references"
            / "review-rubric.md": ("`pdf`", "完整文档", "%PDF-", "%%EOF"),
        }
        for path, phrases in required.items():
            text = path.read_text(encoding="utf-8")
            for phrase in phrases:
                with self.subTest(path=path.name, phrase=phrase):
                    self.assertIn(phrase, text)

    def test_course_frame_rules_are_consistent_across_skill_references(self):
        required = {
            ROOT
            / "skills"
            / "build-platform-course"
            / "references"
            / "course-contract.md": (
                'schema version `1.1`',
                "course.introduction",
                "course.conclusion",
                "开始学习",
            ),
            ROOT
            / "skills"
            / "build-platform-course"
            / "references"
            / "workflow.md": (
                "课程首尾设计表",
                "objectiveAlignment",
                "课程开场",
            ),
            ROOT
            / "skills"
            / "review-platform-course"
            / "references"
            / "review-rubric.md": (
                "CourseDefinition 2.0",
                "migration-required",
                "evidenceBlockIds",
            ),
        }
        for path, phrases in required.items():
            text = path.read_text(encoding="utf-8")
            for phrase in phrases:
                with self.subTest(path=path.name, phrase=phrase):
                    self.assertIn(phrase, text)

    def test_video_and_html_quality_rules_are_consistent_across_references(self):
        required = {
            ROOT
            / "skills"
            / "design-video-interactions"
            / "references"
            / "video-contract.md": (
                "H.264",
                "AAC",
                "faststart",
                "long-video",
                "500 MiB",
            ),
            ROOT
            / "skills"
            / "design-course-html"
            / "references"
            / "html-contract.md": (
                "16px",
                "14px",
                "html-reports",
                "browserCheckRequired",
            ),
            ROOT
            / "skills"
            / "review-platform-course"
            / "references"
            / "review-rubric.md": (
                "unsupported-video-codec",
                "missing-faststart",
                "completion/student-data",
                "真实 iframe",
            ),
        }
        for path, phrases in required.items():
            text = path.read_text(encoding="utf-8")
            for phrase in phrases:
                with self.subTest(path=path.name, phrase=phrase):
                    self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
