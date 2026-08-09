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

    def test_course_schema_defines_non_blocking_pdf_block(self):
        schema = json.loads(
            (ROOT / "schemas" / "course.schema.json").read_text(encoding="utf-8")
        )
        pdf_schema = schema["$defs"]["pdfBlock"]
        block_refs = {
            entry["$ref"]
            for entry in schema["$defs"]["piece"]["properties"]["blocks"]["items"][
                "oneOf"
            ]
        }

        self.assertIn("#/$defs/pdfBlock", block_refs)
        self.assertEqual(
            pdf_schema["required"],
            ["id", "type", "title", "source"],
        )
        self.assertFalse(pdf_schema["additionalProperties"])
        self.assertNotIn("blocking", pdf_schema["properties"])
        self.assertNotIn("completion", pdf_schema["properties"])

    def test_course_schema_requires_11_introduction_and_conclusion(self):
        schema = json.loads(
            (ROOT / "schemas" / "course.schema.json").read_text(encoding="utf-8")
        )
        course = schema["$defs"]["course"]
        introduction = schema["$defs"]["introduction"]
        conclusion = schema["$defs"]["conclusion"]

        self.assertEqual(schema["properties"]["schemaVersion"]["const"], "1.1")
        self.assertIn("introduction", course["required"])
        self.assertIn("conclusion", course["required"])
        self.assertFalse(introduction["additionalProperties"])
        self.assertEqual(
            introduction["properties"]["objectives"]["maxItems"],
            5,
        )
        self.assertEqual(introduction["properties"]["keyPoints"]["minItems"], 2)
        self.assertFalse(conclusion["additionalProperties"])
        self.assertEqual(conclusion["properties"]["takeaways"]["minItems"], 2)
        self.assertEqual(
            conclusion["properties"]["transferApplications"]["maxItems"],
            8,
        )

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

    def test_public_docs_describe_pdf_course_delivery(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        report = (ROOT / "docs" / "validation-report.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("PDF", readme)
        self.assertIn("`pdf`", readme)
        self.assertIn("PDF", report)
        self.assertIn("invalid-pdf-header", report)


if __name__ == "__main__":
    unittest.main()
