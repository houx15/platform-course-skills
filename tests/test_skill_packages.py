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
            "teacher-authored preview annotation is an explicit change instruction",
            "CourseDefinition 2.0",
            "New steps apply when a course reaches them",
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

    def test_build_platform_course_uses_confirmed_teaching_design_and_page_plan_before_autonomous_production(self):
        skill = (
            ROOT / "skills" / "build-platform-course" / "SKILL.md"
        ).read_text(encoding="utf-8")
        workflow = (
            ROOT
            / "skills"
            / "build-platform-course"
            / "references"
            / "workflow.md"
        ).read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        combined = "\n".join((skill, workflow, readme))

        for phrase in (
            "理解材料",
            "确认教学设计与逐页计划",
            "制作并自检",
            "预览并发布",
            "真正阻塞项",
            "逐页视觉自检",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, combined)

        self.assertNotIn("等待教师确认 both tables as one complete design gate", skill)
        self.assertNotIn("confirm the material summary", skill.lower())
        self.assertIn("studentPerspectiveReview", skill)
        self.assertIn("experiences a course rather than a test", skill)

    def test_apply_preview_feedback_treats_exact_annotation_as_instruction(self):
        skill = (
            ROOT / "skills" / "apply-preview-feedback" / "SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn("annotation itself is the explicit teacher instruction", skill)
        self.assertIn("do not request duplicate approval", skill)
        self.assertIn("use the annotation text as the decision rationale", skill)
        self.assertNotIn(
            "Never infer approval from the original annotation",
            skill,
        )

    def test_blueprint_completion_does_not_pause_before_preview(self):
        skill = (
            ROOT / "skills" / "design-course-blueprint" / "SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn("approved teaching design", skill)
        self.assertIn("continue directly to compilation", skill)
        self.assertIn("teacher reviews the rendered result later", skill)
        self.assertNotIn("Batch related semantic decisions for teacher confirmation", skill)

    def test_material_analysis_returns_ai_draft_without_group_confirmation(self):
        skill = (
            ROOT / "skills" / "analyze-course-materials" / "SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn("teacherConfirmed: false", skill)
        self.assertIn("Do not ask the teacher to confirm inventory categories separately", skill)
        self.assertIn("record that none was detected", skill)
        self.assertNotIn("Ask for one 分组确认", skill)

    def test_media_specialists_generate_source_backed_drafts_before_preview(self):
        html = (
            ROOT / "skills" / "design-course-html" / "SKILL.md"
        ).read_text(encoding="utf-8")
        video = (
            ROOT / "skills" / "design-video-interactions" / "SKILL.md"
        ).read_text(encoding="utf-8")

        for text in (html, video):
            self.assertIn("source-backed AI draft", text)
            self.assertIn("true blocker", text)
        self.assertNotIn("wait for 教师确认", html)
        self.assertNotIn("obtain 教师确认", video)

    def test_html_skill_repairs_legacy_protocol_without_teacher_code_work(self):
        skill = (
            ROOT / "skills" / "design-course-html" / "SKILL.md"
        ).read_text(encoding="utf-8")
        contract = (
            ROOT
            / "skills"
            / "design-course-html"
            / "references"
            / "html-contract.md"
        ).read_text(encoding="utf-8")
        director = (
            ROOT / "skills" / "build-platform-course" / "SKILL.md"
        ).read_text(encoding="utf-8")

        for phrase in (
            "directly edit the delivery copy",
            "do not ask the teacher to modify code",
            ".course-work/html-backups/",
            "original SHA-256",
            "preserve the existing questions, answers, scoring, feedback, completion threshold, DOM, and CSS",
            "legacy payload",
            "recompile the course",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, skill)

        self.assertIn("repair the HTML directly", director)
        self.assertIn("pendingFrameMessages", contract)
        self.assertIn("let completionSent = false", contract)
        self.assertIn("function completeInteraction", contract)
        self.assertNotIn("if (!sessionToken) return;", contract)
        self.assertNotIn('\nsend("completed", {', contract)

    def test_video_skill_offers_safe_ffmpeg_processing_and_waits_for_confirmation(self):
        skill = (
            ROOT / "skills" / "design-video-interactions" / "SKILL.md"
        ).read_text(encoding="utf-8")
        director = (
            ROOT / "skills" / "build-platform-course" / "SKILL.md"
        ).read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        combined = "\n".join((skill, director, readme))

        for phrase in (
            "可以使用 `ffmpeg` 帮忙处理",
            "do not force a separate session",
            "ffmpeg -n",
            "原视频保持不变并作为回滚备份",
            ".course-work/video-backups/",
            "候选视频",
            "teacher confirms the processed video",
            "before updating the Blueprint",
            "语义锚点逐个重新核对",
            "不得按时长比例机械缩放",
            "source SHA-256 immediately before ffmpeg",
            "append-only processing manifest",
            ".course-work/video-processing-decisions/",
            "no-clobber copy",
            "old time, semantic anchor, new time",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, combined)

        self.assertNotIn("Recommend opening a 新会话", director)
        self.assertNotIn("不得生成、剪辑、转码或修改 MP4", skill)

    def test_course_catalog_identity_metadata_and_preseeded_covers_are_fixed(self):
        director = (ROOT / "skills/build-platform-course/SKILL.md").read_text(encoding="utf-8")
        publisher = (ROOT / "skills/publish-platform-course/SKILL.md").read_text(encoding="utf-8")
        api_contract = (
            ROOT / "skills/publish-platform-course/references/api-contract.md"
        ).read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        combined = "\n".join((director, publisher, api_contract, readme))

        for phrase in (
            "33-course catalog",
            "manage-course-catalog.py propose",
            "teacher-confirmed catalog binding",
            "course-authoring-v1.4.0",
            "structured `introduction`",
            "`cardIds`",
            "featured_rank",
            "canonical `course-01` through `course-33` slug",
            "preseeded once",
            "Do not call image generation",
            "never a teacher upload",
            "The teacher makes only one catalog decision",
            "selects the human-readable course name",
            "Do not ask the teacher to review or approve any of those fields separately",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, combined)
        self.assertNotIn("Final generated-cover publication remains blocked", combined)
        self.assertNotIn("authoring API v1.3.0", combined)

    def test_authoring_rules_prevent_invented_video_questions_and_repeated_answer_positions(self):
        director = (ROOT / "skills/build-platform-course/SKILL.md").read_text(encoding="utf-8")
        blueprint = (ROOT / "skills/design-course-blueprint/SKILL.md").read_text(encoding="utf-8")
        video = (ROOT / "skills/design-video-interactions/SKILL.md").read_text(encoding="utf-8")
        runtime = (ROOT / "skills/design-course-blueprint/references/runtime-authoring-standard.md").read_text(encoding="utf-8")
        combined = "\n".join((director, blueprint, video, runtime))

        for phrase in (
            "Never invent a video question",
            "teacher-provided video questions",
            "no video interaction",
            "correct answer positions",
            "do not default every correct answer to the first option",
            "split-horizontal defaults to `1:1`",
            "two to four cells",
            "vertically centred",
            "answerable Block in the right slot",
            "same Slice",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, combined)

    def test_external_preview_handoff_and_non_empty_split_rule_are_explicit(self):
        director = (ROOT / "skills/build-platform-course/SKILL.md").read_text(encoding="utf-8")
        workflow = (
            ROOT / "skills/build-platform-course/references/workflow.md"
        ).read_text(encoding="utf-8")
        blueprint = (ROOT / "skills/design-course-blueprint/SKILL.md").read_text(encoding="utf-8")
        runtime = (
            ROOT / "skills/design-course-blueprint/references/runtime-authoring-standard.md"
        ).read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        combined = "\n".join((director, workflow, blueprint, runtime, readme))

        for phrase in (
            "split Slots must be non-empty",
            "proactively remind the teacher",
            "publish to the student platform",
            "ZIP archive",
            "127.0.0.1",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, combined)

    def test_pdf_authoring_uses_equal_slots_and_popup_reading(self):
        blueprint = (ROOT / "skills/design-course-blueprint/SKILL.md").read_text(encoding="utf-8")
        runtime = (ROOT / "skills/design-course-blueprint/references/runtime-authoring-standard.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        combined = "\n".join((blueprint, runtime, readme))

        for phrase in (
            "course-authoring-v1.6.0",
            "放大阅读",
            "near-fullscreen modal",
            "text-and-PDF split remains `1:1`",
            "does not justify an asymmetric column",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, combined)

    def test_preview_runs_visual_check_and_preserves_teacher_freedom(self):
        preview = (ROOT / "skills/preview-platform-course/SKILL.md").read_text(encoding="utf-8")

        for phrase in (
            "open every Slice",
            "one screenshot per Slice",
            "no empty side of a split",
            "available on the same Slice",
            "上一页",
            "Existing annotations may be edited, deleted, marked complete, or reopened",
            "现在发布到学生端吗？",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, preview)

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
