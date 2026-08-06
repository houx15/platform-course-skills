import tempfile
import unittest
import zipfile
from pathlib import Path

from course_toolkit.coverage import validate_coverage
from course_toolkit.materials import extract_paths
from tests.helpers import ROOT


class MaterialsTests(unittest.TestCase):
    def test_extracts_markdown_and_html_with_locations(self):
        result = extract_paths(
            [
                ROOT / "tests" / "fixtures" / "materials" / "lesson.md",
                ROOT / "tests" / "fixtures" / "materials" / "lesson.html",
            ]
        )
        texts = {item.text for item in result.items}
        self.assertIn("课程标题", texts)
        self.assertIn("这是第一段课程内容。", texts)
        self.assertIn("HTML 课程标题", texts)
        self.assertIn("HTML 段落内容。", texts)
        self.assertIn("列表活动", texts)
        self.assertIn("表格证据", texts)
        self.assertTrue(all(item.location for item in result.items))

    def test_extracts_docx_and_txt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docx = root / "lesson.docx"
            document_xml = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Word 标题</w:t></w:r></w:p>
    <w:p><w:r><w:t>Word 正文</w:t></w:r></w:p>
    <w:tbl>
      <w:tr>
        <w:tc><w:p><w:r><w:t>表格证据</w:t></w:r></w:p></w:tc>
      </w:tr>
    </w:tbl>
  </w:body>
</w:document>"""
            with zipfile.ZipFile(docx, "w") as archive:
                archive.writestr("word/document.xml", document_xml)
            text = root / "notes.txt"
            text.write_text("第一段\n\n第二段", encoding="utf-8")
            result = extract_paths([docx, text])
        values = {(item.kind, item.text) for item in result.items}
        self.assertIn(("heading", "Word 标题"), values)
        self.assertIn(("paragraph", "Word 正文"), values)
        table_item = next(item for item in result.items if item.text == "表格证据")
        self.assertEqual(table_item.kind, "table-cell")
        self.assertEqual(table_item.location, "table:1/row:1/cell:1/paragraph:1")
        self.assertIn(("paragraph", "第一段"), values)

    def test_zip_is_ignored_and_pdf_is_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "export.zip"
            archive.write_bytes(b"zip")
            pdf = root / "appendix.pdf"
            pdf.write_bytes(b"%PDF")
            result = extract_paths([archive, pdf])
        self.assertEqual([item.name for item in result.ignored], ["export.zip"])
        self.assertEqual([item.name for item in result.unsupported], ["appendix.pdf"])

    def test_source_ids_are_stable(self):
        path = ROOT / "tests" / "fixtures" / "materials" / "lesson.md"
        first = extract_paths([path])
        second = extract_paths([path])
        self.assertEqual(
            [item.source_id for item in first.items],
            [item.source_id for item in second.items],
        )

    def test_coverage_rejects_unresolved_and_unapproved_discard(self):
        data = {
            "items": [
                {"sourceId": "source-1", "status": "unresolved"},
                {"sourceId": "source-2", "status": "discard-proposed"},
            ]
        }
        codes = {issue.code for issue in validate_coverage(data)}
        self.assertIn("unresolved", codes)
        self.assertIn("discard-proposed", codes)

    def test_coverage_accepts_resolved_items(self):
        data = {
            "items": [
                {
                    "sourceId": "source-1",
                    "sourceFile": "lesson.docx",
                    "location": "paragraph:1",
                    "summary": "开场",
                    "status": "mapped",
                    "destinations": ["part-1/piece-1/intro"],
                },
                {
                    "sourceId": "source-2",
                    "sourceFile": "lesson.docx",
                    "location": "paragraph:2",
                    "summary": "例子",
                    "status": "merged",
                    "destinations": ["part-1/piece-1/intro"],
                },
                {
                    "sourceId": "source-3",
                    "sourceFile": "lesson.docx",
                    "location": "paragraph:3",
                    "summary": "重复内容",
                    "status": "discard-approved",
                    "teacherConfirmed": True,
                    "reason": "重复内容",
                },
            ]
        }
        self.assertEqual(validate_coverage(data), [])


if __name__ == "__main__":
    unittest.main()
