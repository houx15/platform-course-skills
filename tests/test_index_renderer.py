import copy
import tempfile
import unittest
from pathlib import Path

from course_toolkit.index_renderer import render_index
from course_toolkit.paths import resolve_course_path, validate_referenced_paths
from tests.helpers import minimal_course


class IndexRendererTests(unittest.TestCase):
    def test_rejects_absolute_and_parent_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for raw in ("/etc/passwd", "../secret.png"):
                with self.subTest(raw=raw):
                    with self.assertRaisesRegex(ValueError, "Unsafe course path"):
                        resolve_course_path(root, raw)

    def test_reports_missing_resource(self):
        data = minimal_course()
        data["course"]["parts"][0]["pieces"][0]["blocks"] = [
            {
                "id": "images",
                "type": "images",
                "items": [{"source": "assets/images/a.png", "alt": "示例"}],
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            issues = validate_referenced_paths(Path(tmp), data)
        self.assertIn("missing-file", {issue.code for issue in issues})

    def test_valid_nested_resource_passes(self):
        data = minimal_course()
        data["course"]["parts"][0]["pieces"][0]["blocks"] = [
            {
                "id": "images",
                "type": "images",
                "items": [{"source": "assets/images/a.png", "alt": "示例"}],
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "assets" / "images" / "a.png"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"png")
            self.assertEqual(validate_referenced_paths(root, data), [])

    def test_render_is_deterministic_and_structured(self):
        data = minimal_course()
        first = render_index(data)
        second = render_index(copy.deepcopy(data))
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("# 样例课程\n"))
        self.assertIn("## 第一部分", first)
        self.assertIn("### 第一内容块", first)
        self.assertIn("[文字]", first)
        self.assertNotIn("最终产物不需要", first)
        self.assertTrue(first.endswith("\n"))

    def test_renders_images_video_html_and_assessments(self):
        data = minimal_course()
        data["course"]["parts"][0]["pieces"][0]["blocks"] = [
            {
                "id": "images",
                "type": "images",
                "items": [{"source": "assets/images/a.png", "alt": "图像说明"}],
            },
            {
                "id": "video",
                "type": "video",
                "blocking": True,
                "source": "assets/videos/a.mp4",
                "interaction": {
                    "data": "interactions/video/a.json",
                    "document": "interactions/video/a.md",
                },
            },
            {
                "id": "html",
                "type": "interactiveHtml",
                "blocking": False,
                "source": "interactions/html/a.html",
            },
            {
                "id": "reflection",
                "type": "fillBlank",
                "blocking": True,
                "prompt": "说说你的想法",
                "assessment": {"mode": "reflection", "rubric": "结合材料回答"},
            },
        ]
        text = render_index(data)
        self.assertIn("![图像说明](assets/images/a.png)", text)
        self.assertIn("[视频]", text)
        self.assertIn("- 阻塞：是", text)
        self.assertIn("- 交互数据：interactions/video/a.json", text)
        self.assertIn("[交互]", text)
        self.assertIn("- 阻塞：否", text)
        self.assertIn("- 评价要求：结合材料回答", text)


if __name__ == "__main__":
    unittest.main()
