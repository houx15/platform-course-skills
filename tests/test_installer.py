import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT


SCRIPT = ROOT / "scripts" / "install-skills.py"
SKILL_NAMES = {
    "apply-preview-feedback",
    "analyze-course-materials",
    "build-platform-course",
    "design-course-html",
    "design-course-blueprint",
    "design-video-interactions",
    "preview-platform-course",
    "publish-platform-course",
    "review-platform-course",
}


class InstallerTests(unittest.TestCase):
    def run_installer(self, home, *args, check=True):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--home",
                str(home),
                *args,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=check,
        )

    def assert_install(self, parent):
        for name in SKILL_NAMES:
            self.assertTrue((parent / name / "SKILL.md").is_file())
        runtime = parent / "_course-toolkit"
        self.assertTrue((runtime / "course_toolkit" / "package_review.py").is_file())
        self.assertTrue((runtime / "course_toolkit" / "course_catalog.json").is_file())
        self.assertTrue((runtime / "course_toolkit" / "course_catalog.py").is_file())
        self.assertTrue((runtime / "course_toolkit" / "course_cover.py").is_file())
        self.assertTrue((runtime / "scripts" / "manage-course-catalog.py").is_file())
        self.assertTrue((runtime / "scripts" / "manage-course-cover.py").is_file())
        self.assertTrue((runtime / "course_toolkit" / "runtime_dist" / "preview" / "index.html").is_file())
        self.assertTrue((runtime / "scripts" / "preview-course.py").is_file())
        self.assertTrue((runtime / "scripts" / "review-course-v2.py").is_file())
        self.assertTrue((runtime / "scripts" / "publish-course.py").is_file())
        self.assertTrue((runtime / "schemas" / "course.schema.json").is_file())
        self.assertTrue((runtime / "scripts" / "validate-course.py").is_file())
        self.assertTrue((runtime / "scripts" / "generate-html-report.py").is_file())
        self.assertFalse(any(parent.rglob("*.zip")))

    def test_installs_codex_copy_and_preserves_unrelated_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            unrelated = home / ".codex" / "skills" / "my-skill"
            unrelated.mkdir(parents=True)
            (unrelated / "SKILL.md").write_text("keep", encoding="utf-8")
            self.run_installer(home, "--target", "codex")
            self.assert_install(home / ".codex" / "skills")
            self.assertEqual(
                (unrelated / "SKILL.md").read_text(encoding="utf-8"),
                "keep",
            )

    def test_installs_both_hosts(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.run_installer(home, "--target", "both")
            self.assert_install(home / ".codex" / "skills")
            self.assert_install(home / ".claude" / "skills")

    def test_symlink_mode_links_skills_and_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.run_installer(home, "--target", "claude", "--symlink")
            parent = home / ".claude" / "skills"
            self.assertTrue((parent / "build-platform-course").is_symlink())
            self.assertTrue((parent / "_course-toolkit").is_symlink())
            self.assert_install(parent)

    def test_existing_toolkit_requires_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.run_installer(home, "--target", "codex")
            result = self.run_installer(
                home,
                "--target",
                "codex",
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.run_installer(home, "--target", "codex", "--replace")
            self.assert_install(home / ".codex" / "skills")

    def test_readme_exposes_one_sentence_codex_install_contract(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "帮我安装这套 Skills：https://github.com/houx15/platform-course-skills",
            readme,
        )
        self.assertIn(
            "python3 scripts/install-skills.py --target codex",
            readme,
        )
        self.assertIn("不要把仓库根目录当作单个 Skill", readme)
        self.assertIn("一行对应一个 Slice", readme)
        self.assertIn("CourseDefinition 2.0", readme)
        self.assertIn("真实学生端 renderer", readme)
        self.assertIn("apply-preview-feedback", readme)
        self.assertIn("稳定 slug", readme)
        self.assertIn("OSS_ADMIN_KEY", readme)
        self.assertIn("课程首尾设计表", readme)
        self.assertIn("开始学习", readme)
        self.assertIn("G0–G10", readme)

    def test_readme_hands_the_workflow_to_another_agent(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        required = (
            "## Agent 接手协议",
            "如果你是正在读取本 README 的 Agent",
            "不要只向老师复述本文",
            "先判断 Skills 是否已安装",
            "根据当前宿主选择 Codex 或 Claude",
            "只安装或更新",
            "开始一门新课程",
            "继续已有课程",
            "课程文件夹的绝对路径",
            "新建还是继续",
            "`index.md` 或主要入口材料",
            "由 Agent 自己执行",
            "不要在课程开始时索取 `OSS_ADMIN_KEY`",
            "读取 `.course-work/session.json`",
            "存在 `.course-work/session.json` 时默认按继续处理",
            "不得上传或发布",
        )
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)

        self.assertLess(
            readme.index("## Agent 接手协议"),
            readme.index("## 老师如何使用"),
        )

    def test_readme_distinguishes_teacher_preview_chrome_from_student_shell(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        required = (
            "额外的教师预览工具",
            "不属于学生端课程界面",
            "学生端本身还有自己的侧边栏",
            "不能单独证明学生端完整外壳",
            "不得通过修改课程 JSON 掩盖",
        )
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)


if __name__ == "__main__":
    unittest.main()
