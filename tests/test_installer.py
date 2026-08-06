import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT


SCRIPT = ROOT / "scripts" / "install-skills.py"
SKILL_NAMES = {
    "analyze-course-materials",
    "build-platform-course",
    "design-course-html",
    "design-video-interactions",
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
        self.assertTrue((runtime / "schemas" / "course.schema.json").is_file())
        self.assertTrue((runtime / "scripts" / "validate-course.py").is_file())
        self.assertFalse(any(parent.rglob("*.zip")))

    def test_installs_codex_copy_and_preserves_unrelated_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            unrelated = home / ".agents" / "skills" / "my-skill"
            unrelated.mkdir(parents=True)
            (unrelated / "SKILL.md").write_text("keep", encoding="utf-8")
            self.run_installer(home, "--target", "codex")
            self.assert_install(home / ".agents" / "skills")
            self.assertEqual(
                (unrelated / "SKILL.md").read_text(encoding="utf-8"),
                "keep",
            )

    def test_installs_both_hosts(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.run_installer(home, "--target", "both")
            self.assert_install(home / ".agents" / "skills")
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
            self.assert_install(home / ".agents" / "skills")


if __name__ == "__main__":
    unittest.main()
