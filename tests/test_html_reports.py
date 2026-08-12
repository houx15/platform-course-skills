import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from course_toolkit.html_reports import (
    build_html_report,
    render_html_report,
    validate_html_report,
)
from course_toolkit.jsonio import load_json
from tests.helpers import ROOT
from tests.test_html_validation import VALID_HTML


class HtmlReportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.html_path = self.root / "task.html"
        self.html_path.write_text(VALID_HTML, encoding="utf-8")
        self.source = "interactions/html/task.html"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_builds_deterministic_passing_report(self):
        report = build_html_report("interaction-block", self.source, self.html_path)

        self.assertEqual(report["schemaVersion"], "1.0")
        self.assertEqual(report["blockId"], "interaction-block")
        self.assertEqual(report["source"], self.source)
        self.assertEqual(
            report["sha256"],
            hashlib.sha256(self.html_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(report["finalStatus"], "pass")
        self.assertTrue(report["browserCheckRequired"])
        self.assertNotIn("timestamp", report)
        self.assertEqual(len(report["checks"]), 10)
        self.assertEqual(
            validate_html_report(
                report,
                "interaction-block",
                self.source,
                self.html_path,
            ),
            [],
        )

    def test_markdown_contains_complete_check_table(self):
        report = build_html_report("interaction-block", self.source, self.html_path)
        markdown = render_html_report(report)

        self.assertTrue(markdown.startswith("# HTML 检查报告：interaction-block\n"))
        self.assertIn("| 检查项 | 结果 | 证据与修改建议 |", markdown)
        self.assertIn("| 基础字号 | pass |", markdown)
        self.assertIn("| 浏览器复核边界 | required |", markdown)
        self.assertIn("| 最终结论 | pass |", markdown)
        self.assertIn("仍需在真实 iframe 中完成浏览器检查", markdown)
        self.assertTrue(markdown.endswith("\n"))

    def test_changed_html_makes_report_stale(self):
        report = build_html_report("interaction-block", self.source, self.html_path)
        self.html_path.write_text(VALID_HTML.replace("完成任务", "完成"), encoding="utf-8")

        codes = {
            issue.code
            for issue in validate_html_report(
                report,
                "interaction-block",
                self.source,
                self.html_path,
            )
        }

        self.assertIn("stale-html-report", codes)

    def test_cli_writes_json_and_markdown(self):
        output_dir = self.root / "html-reports"
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "generate-html-report.py"),
                str(self.html_path),
                "--block-id",
                "interaction-block",
                "--source",
                self.source,
                "--output-dir",
                str(output_dir),
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )

        report = load_json(output_dir / "interaction-block.json")
        self.assertEqual(report["finalStatus"], "pass")
        self.assertEqual(
            (output_dir / "interaction-block.md").read_text(encoding="utf-8"),
            render_html_report(report),
        )


if __name__ == "__main__":
    unittest.main()
