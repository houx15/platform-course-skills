import copy
import tempfile
import unittest
from pathlib import Path

from course_toolkit.course_compiler import (
    canonical_json_hash,
    compile_blueprint,
    write_compilation_outputs_atomic,
)
from course_toolkit.course_package_validation import (
    build_course_validation_report,
    sync_validation_issues,
    write_current_validation_report,
)
from course_toolkit.decisions import DecisionStore
from course_toolkit.jsonio import dump_json, load_json, write_json_atomic
from course_toolkit.legacy_course_import import import_legacy_course
from course_toolkit.workflow import verify_g6_validation
from tests.helpers import ROOT
from tests.test_html_validation import VALID_HTML_V2


REAL_ROOT = ROOT / "e2e" / "for-test-course"
LEGACY_COURSE = REAL_ROOT / "course" / "course.json"
STORYBOARD = REAL_ROOT / ".course-work" / "course-storyboard.json"
DECIDED_AT = "2026-08-16T00:00:00Z"


class RealCourseMigrationTests(unittest.TestCase):
    def test_real_legacy_course_migrates_after_explicit_assumption_decision(self):
        legacy = load_json(LEGACY_COURSE)
        storyboard = load_json(STORYBOARD)
        blueprint = import_legacy_course(legacy, storyboard)

        self.assertFalse(blueprint["approval"]["teacherConfirmed"])
        assumption_ids = [
            item["id"] for item in blueprint["migration"]["assumptions"]
        ]
        context_hash = canonical_json_hash(blueprint["migration"]["assumptions"])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "migrated-course"
            store = DecisionStore(root / ".course-work/decisions.json")
            store.request(
                "decision-legacy-two-migration",
                "Approve the recorded CourseDefinition 2.0 migration assumptions?",
                context_hash,
                context={"assumptionIds": assumption_ids},
                options=("approve", "revise"),
                affected_artifact_ids=("course-blueprint",),
                requested_at=DECIDED_AT,
            )
            decision = store.confirm(
                "decision-legacy-two-migration",
                {"choice": "approve", "assumptionIds": assumption_ids},
                DECIDED_AT,
            )
            store.save()

            confirmed = copy.deepcopy(blueprint)
            confirmed["approval"] = {
                "teacherConfirmed": decision.status == "confirmed",
                "decisionIds": [decision.id],
            }
            first = compile_blueprint(confirmed)
            second = compile_blueprint(copy.deepcopy(confirmed))

            write_json_atomic(
                root / ".course-work/course-blueprint.json",
                confirmed,
            )
            write_compilation_outputs_atomic(root, first)
            pdf = root / "course/assets/pdfs/source-paper-test.pdf"
            pdf.parent.mkdir(parents=True, exist_ok=True)
            pdf.write_bytes(
                (REAL_ROOT / "course/assets/pdfs/source-paper-test.pdf").read_bytes()
            )
            html = root / "course/interactions/html/urban-heat-island-check.html"
            html.parent.mkdir(parents=True, exist_ok=True)
            html.write_text(VALID_HTML_V2, encoding="utf-8")
            first_validation = build_course_validation_report(root)
            second_validation = build_course_validation_report(root)
            write_current_validation_report(root, first_validation)
            sync_validation_issues(root, first_validation, DECIDED_AT)
            g6_evidence = verify_g6_validation(root)

        course = first.document["course"]
        self.assertEqual(len(course["parts"]), 6)
        self.assertEqual(sum(len(part["slices"]) for part in course["parts"]), 13)
        self.assertEqual(
            sum(
                len(slice_data["blocks"])
                for part in course["parts"]
                for slice_data in part["slices"]
            ),
            27,
        )
        self.assertEqual(dump_json(first.document), dump_json(second.document))
        self.assertEqual(dump_json(first.source_map), dump_json(second.source_map))
        self.assertEqual(first.report["status"], "compiled")
        self.assertEqual(first.report["issues"], [])
        self.assertEqual(first_validation, second_validation)
        self.assertEqual(first_validation["status"], "clear")
        self.assertEqual(first_validation["issues"], [])
        self.assertEqual(first_validation["warnings"], [])
        self.assertEqual(
            first_validation["summary"],
            {
                "partCount": 6,
                "sliceCount": 13,
                "blockCount": 27,
                "assetCount": 2,
            },
        )
        self.assertEqual(
            canonical_json_hash(first_validation),
            canonical_json_hash(second_validation),
        )
        self.assertEqual(
            g6_evidence["@course/asset-set"],
            first_validation["assetSetHash"],
        )


if __name__ == "__main__":
    unittest.main()
