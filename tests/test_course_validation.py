import copy
import unittest

from course_toolkit.course_validation import validate_course_data
from tests.helpers import minimal_course


def pdf_block():
    return {
        "id": "source-paper",
        "type": "pdf",
        "title": "研究论文原文（结构测试材料）",
        "source": "assets/pdfs/source-paper.pdf",
    }


class CourseValidationTests(unittest.TestCase):
    def codes(self, data):
        return {issue.code for issue in validate_course_data(data)}

    def test_minimal_course_is_valid(self):
        self.assertEqual(validate_course_data(minimal_course()), [])

    def test_duplicate_ids_fail(self):
        data = minimal_course()
        data["course"]["parts"][0]["pieces"][0]["id"] = "part-1"
        self.assertIn("duplicate-id", self.codes(data))

    def test_unknown_block_type_fails(self):
        data = minimal_course()
        data["course"]["parts"][0]["pieces"][0]["blocks"][0]["type"] = "audio"
        self.assertIn("unsupported-type", self.codes(data))

    def test_empty_image_alt_fails(self):
        data = minimal_course()
        data["course"]["parts"][0]["pieces"][0]["blocks"] = [
            {
                "id": "images",
                "type": "images",
                "items": [{"source": "assets/images/a.png", "alt": ""}],
            }
        ]
        self.assertIn("required", self.codes(data))

    def test_pdf_block_is_valid(self):
        data = minimal_course()
        data["course"]["parts"][0]["pieces"][0]["blocks"] = [pdf_block()]
        self.assertEqual(validate_course_data(data), [])

    def test_pdf_block_requires_title_and_source(self):
        for field in ("title", "source"):
            data = minimal_course()
            block = pdf_block()
            del block[field]
            data["course"]["parts"][0]["pieces"][0]["blocks"] = [block]
            with self.subTest(field=field):
                self.assertIn("required", self.codes(data))

    def test_pdf_block_does_not_accept_completion_fields(self):
        data = minimal_course()
        block = pdf_block()
        block["blocking"] = True
        block["completion"] = {"rule": "submit-any"}
        data["course"]["parts"][0]["pieces"][0]["blocks"] = [block]

        self.assertEqual(validate_course_data(data), [])

    def test_graded_choice_needs_correct_option(self):
        data = minimal_course()
        data["course"]["parts"][0]["pieces"][0]["blocks"] = [
            {
                "id": "question",
                "type": "singleChoice",
                "blocking": True,
                "prompt": "选一个",
                "options": [
                    {"id": "a", "label": "A"},
                    {"id": "b", "label": "B"},
                ],
                "assessment": {"mode": "graded"},
            }
        ]
        self.assertIn("required", self.codes(data))

    def test_survey_choice_rejects_correct_answer(self):
        data = minimal_course()
        block = {
            "id": "question",
            "type": "singleChoice",
            "blocking": True,
            "prompt": "选一个",
            "options": [
                {"id": "a", "label": "A"},
                {"id": "b", "label": "B"},
            ],
            "assessment": {"mode": "survey", "correctOptionId": "a"},
        }
        data["course"]["parts"][0]["pieces"][0]["blocks"] = [block]
        self.assertIn("forbidden", self.codes(data))

    def test_reflection_needs_rubric(self):
        data = minimal_course()
        data["course"]["parts"][0]["pieces"][0]["blocks"] = [
            {
                "id": "reflection",
                "type": "fillBlank",
                "blocking": True,
                "prompt": "想一想",
                "assessment": {"mode": "reflection"},
            }
        ]
        self.assertIn("required", self.codes(data))

    def test_graded_fill_needs_answers(self):
        data = minimal_course()
        data["course"]["parts"][0]["pieces"][0]["blocks"] = [
            {
                "id": "answer",
                "type": "fillBlank",
                "blocking": True,
                "prompt": "填写",
                "assessment": {"mode": "graded"},
            }
        ]
        self.assertIn("required", self.codes(data))

    def test_invalid_id_fails(self):
        data = copy.deepcopy(minimal_course())
        data["course"]["id"] = "Bad ID"
        self.assertIn("invalid-id", self.codes(data))


if __name__ == "__main__":
    unittest.main()
