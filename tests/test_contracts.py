import json
import tempfile
import unittest
from pathlib import Path

from course_toolkit.errors import ValidationIssue
from course_toolkit.jsonio import load_json
from tests.helpers import ROOT


class ContractTests(unittest.TestCase):
    def test_schema_documents_are_valid_json(self):
        for name in ("course.schema.json", "video-interactions.schema.json"):
            data = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
            self.assertEqual(
                data["$schema"],
                "https://json-schema.org/draft/2020-12/schema",
            )
            self.assertEqual(data["type"], "object")

    def test_load_json_reports_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid.json"
            path.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Invalid JSON"):
                load_json(path)

    def test_validation_issue_serializes(self):
        issue = ValidationIssue("course.parts", "required", "parts is required")
        self.assertEqual(
            issue.as_dict(),
            {
                "path": "course.parts",
                "code": "required",
                "message": "parts is required",
            },
        )


if __name__ == "__main__":
    unittest.main()
