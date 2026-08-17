import copy
import json
import tempfile
import unittest
from pathlib import Path

from course_toolkit.course_completion import (
    audit_course_draft,
    write_completion_plan,
)
from tests.helpers import ROOT


APPROVED = (
    ROOT
    / "tests"
    / "fixtures"
    / "course-blueprint"
    / "approved-blueprint.json"
)


def incomplete_draft():
    return {
        "schemaVersion": "1.0",
        "targetContractVersion": "2.0",
        "approval": {"teacherConfirmed": False, "decisionIds": []},
        "course": {
            "id": "draft-course",
            "title": "Draft Course",
            "language": "en",
            "estimatedMinutes": 4,
            "objectives": [
                {
                    "id": "explain-case",
                    "text": "Explain the case.",
                    "evidenceBlockIds": ["case-question"],
                }
            ],
            "parts": [
                {
                    "id": "part-one",
                    "title": "Part One",
                    "objectiveIds": ["explain-case"],
                    "slices": [
                        {
                            "id": "case-slice",
                            "title": "The Case",
                            "blocks": [
                                {
                                    "id": "case-text",
                                    "type": "text",
                                    "content": "A concise case.",
                                },
                                {
                                    "id": "case-question",
                                    "type": "singleChoice",
                                    "prompt": "Which explanation fits?",
                                    "options": [
                                        {"id": "a", "label": "A"},
                                        {"id": "b", "label": "B"},
                                    ],
                                    "assessment": {
                                        "mode": "graded",
                                        "correctOptionId": "b",
                                    },
                                    "completion": {"rule": "submit-correct"},
                                },
                            ],
                        }
                    ],
                }
            ],
        },
        "provenance": [],
        "migration": None,
    }


class CourseCompletionTests(unittest.TestCase):
    def test_audit_reports_every_missing_runtime_slice_layer(self):
        draft = incomplete_draft()

        plan = audit_course_draft(draft)

        self.assertEqual(plan["courseId"], "draft-course")
        self.assertEqual(plan["summary"]["sliceCount"], 1)
        record = plan["slices"][0]
        self.assertEqual(record["sliceId"], "case-slice")
        self.assertEqual(record["status"], "needs-generation")
        codes = {issue["code"] for issue in record["issues"]}
        self.assertTrue(
            {
                "missing-objective-ids",
                "missing-estimated-seconds",
                "missing-layout",
                "missing-narrations",
                "missing-workflow",
                "missing-navigation",
            }.issubset(codes)
        )

    def test_audit_never_mutates_valid_authored_content(self):
        draft = incomplete_draft()
        before = copy.deepcopy(draft)

        audit_course_draft(draft)

        self.assertEqual(draft, before)

    def test_complete_blueprint_is_ready_for_contract_validation(self):
        blueprint = json.loads(APPROVED.read_text(encoding="utf-8"))

        plan = audit_course_draft(blueprint)

        self.assertEqual(plan["summary"]["statusCounts"], {"ready-for-contract-validation": 1})
        self.assertEqual(plan["slices"][0]["issues"], [])

    def test_html_without_audio_declaration_requires_a_capability_decision(self):
        draft = incomplete_draft()
        block = {
            "id": "case-html",
            "type": "interactiveHtml",
            "source": "interactions/html/case.html",
            "protocolVersion": "1.0",
            "aspectRatio": "4:3",
            "completion": {"rule": "interaction-complete"},
        }
        draft["course"]["parts"][0]["slices"][0]["blocks"].append(block)

        plan = audit_course_draft(draft)

        issues = plan["slices"][0]["issues"]
        audio_issue = next(issue for issue in issues if issue["code"] == "html-audio-capability-undecided")
        self.assertEqual(audio_issue["category"], "teacher-decision")
        self.assertEqual(plan["slices"][0]["status"], "needs-teacher-decision")

    def test_plan_persists_as_the_single_completion_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = audit_course_draft(incomplete_draft())

            output = write_completion_plan(root, plan)

            self.assertEqual(
                output,
                (root / ".course-work" / "course-completion-plan.json").resolve(),
            )
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), plan)


if __name__ == "__main__":
    unittest.main()
