import importlib
import hashlib
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT


EXPECTED_CATEGORIES = {
    "stance-value",
    "source-check",
    "media-literacy",
    "self-knowledge",
    "data-literacy",
    "research-process",
    "argument-writing",
}


class CourseCatalogTests(unittest.TestCase):
    def catalog_module(self):
        module_path = ROOT / "course_toolkit" / "course_catalog.py"
        if not module_path.is_file():
            self.fail("course catalog implementation is missing")
        return importlib.import_module("course_toolkit.course_catalog")

    def test_catalog_is_the_complete_pinned_33_course_dictionary(self):
        module = self.catalog_module()
        catalog = module.load_course_catalog()

        self.assertEqual(catalog["schemaVersion"], "1.0")
        self.assertEqual(catalog["studentAuthoringTag"], "course-authoring-v1.4.0")
        self.assertEqual(len(catalog["courses"]), 33)
        self.assertEqual(len({course["catalogId"] for course in catalog["courses"]}), 33)
        self.assertEqual(len({course["title"] for course in catalog["courses"]}), 33)
        self.assertEqual({course["category"] for course in catalog["courses"]}, EXPECTED_CATEGORIES)

        first = catalog["courses"][0]
        self.assertEqual(first["catalogId"], "course-01")
        self.assertEqual(first["category"], "stance-value")
        self.assertEqual(first["cardIds"], ["belief-spectrum", "perspective-matrix"])
        self.assertIn("同一场气候争议", first["introduction"]["hook"])
        self.assertIn("用 X 轴定位", first["introduction"]["whatYouDo"])
        self.assertEqual(set(first["introduction"]["alignment"]), {"ib", "otherIntl", "domestic"})
        self.assertGreaterEqual(len(first["introduction"]["takeaways"]), 2)
        self.assertGreaterEqual(len(first["introduction"]["keywords"]), 2)
        source = ROOT / catalog["source"]["path"]
        self.assertEqual(
            catalog["source"]["sha256"],
            hashlib.sha256(source.read_bytes()).hexdigest(),
        )

        course_30 = catalog["courses"][29]
        self.assertIn("真实任务", course_30["introduction"]["whatYouDo"])
        self.assertTrue(course_30["introduction"]["alignment"]["ib"])
        course_31 = catalog["courses"][30]
        self.assertEqual(course_31["introduction"]["alignment"]["ib"], [])
        self.assertTrue(course_31["introduction"]["alignment"]["otherIntl"])
        course_33 = catalog["courses"][32]
        self.assertEqual(course_33["category"], "stance-value")
        self.assertEqual(course_33["cardIds"], ["ethics-lenses", "money-trail"])
        self.assertIn("AI伦理", course_33["aliases"])
        self.assertIn("版权", course_33["introduction"]["keywords"])
        self.assertTrue(all(course_33["introduction"]["alignment"].values()))

    def test_title_matching_proposes_but_never_confirms(self):
        module = self.catalog_module()
        exact = module.propose_course_matches("把争议放回证据里：立场光谱与视角对照矩阵")
        self.assertEqual(exact[0]["catalogId"], "course-01")
        self.assertEqual(exact[0]["matchKind"], "exact")
        self.assertFalse(exact[0]["teacherConfirmed"])

        normalized = module.propose_course_matches('AI 公司的“焚书坑儒”：谁为 AI 付了账？')
        self.assertEqual(normalized[0]["catalogId"], "course-33")
        self.assertIn(normalized[0]["matchKind"], {"normalized", "exact"})

    def test_teacher_confirmation_persists_the_full_catalog_payload(self):
        module = self.catalog_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            selection = module.confirm_course_selection(
                root,
                "course-01",
                teacher_response="确认，这是第一门课。",
                confirmed_at="2026-08-20T00:00:00Z",
            )
            loaded = module.load_confirmed_course_selection(root)

        self.assertEqual(loaded, selection)
        self.assertTrue(loaded["teacherConfirmed"])
        self.assertEqual(loaded["category"], "stance-value")
        self.assertEqual(loaded["cardIds"], ["belief-spectrum", "perspective-matrix"])
        self.assertIn("introduction", loaded)
        self.assertEqual(len(loaded["catalogHash"]), 64)

    def test_missing_or_tampered_selection_is_rejected_for_publication(self):
        module = self.catalog_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(module.CourseCatalogError, "33-course catalog"):
                module.load_confirmed_course_selection(root)
            selection = module.confirm_course_selection(
                root,
                "course-01",
                teacher_response="确认",
                confirmed_at="2026-08-20T00:00:00Z",
            )
            path = root / ".course-work/course-catalog-selection.json"
            selection["category"] = "source-check"
            module.write_json_atomic(path, selection)
            with self.assertRaisesRegex(module.CourseCatalogError, "changed"):
                module.load_confirmed_course_selection(root)


if __name__ == "__main__":
    unittest.main()
