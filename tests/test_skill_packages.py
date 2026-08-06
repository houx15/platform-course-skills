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


if __name__ == "__main__":
    unittest.main()
