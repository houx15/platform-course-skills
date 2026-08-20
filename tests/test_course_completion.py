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

    def test_contract_split_ratio_outside_authoring_default_requires_revision(self):
        blueprint = json.loads(APPROVED.read_text(encoding="utf-8"))
        blueprint["course"]["parts"][0]["slices"][0]["layout"]["ratio"] = "3:2"

        plan = audit_course_draft(blueprint)

        self.assertFalse(plan["summary"]["ready"])
        self.assertIn(
            "split-ratio-should-default-one-to-one",
            {issue["code"] for issue in plan["slices"][0]["issues"]},
        )

    def test_split_vertical_is_rejected_by_teacher_authoring_policy(self):
        blueprint = json.loads(APPROVED.read_text(encoding="utf-8"))
        layout = blueprint["course"]["parts"][0]["slices"][0]["layout"]
        layout["preset"] = "split-vertical"
        layout["slots"] = [
            {"id": "top", "blockIds": ["claim-text"]},
            {"id": "bottom", "blockIds": ["evidence-question"]},
        ]

        plan = audit_course_draft(blueprint)

        issues = plan["slices"][0]["issues"]
        self.assertIn("split-vertical-discouraged", {issue["code"] for issue in issues})
        self.assertFalse(plan["summary"]["ready"])

    def test_full_layout_cannot_stack_multiple_blocks(self):
        blueprint = json.loads(APPROVED.read_text(encoding="utf-8"))
        layout = blueprint["course"]["parts"][0]["slices"][0]["layout"]
        layout["preset"] = "full"
        layout.pop("ratio", None)
        layout["slots"] = [
            {"id": "main", "blockIds": ["claim-text", "evidence-question"]},
        ]

        plan = audit_course_draft(blueprint)

        issues = plan["slices"][0]["issues"]
        self.assertIn("full-layout-stacks-blocks", {issue["code"] for issue in issues})
        self.assertFalse(plan["summary"]["ready"])

    def test_horizontal_split_places_assessment_on_right(self):
        blueprint = json.loads(APPROVED.read_text(encoding="utf-8"))
        slice_data = blueprint["course"]["parts"][0]["slices"][0]
        slice_data["layout"] = {
            "preset": "split-horizontal",
            "ratio": "1:1",
            "slots": [
                {"id": "left", "blockIds": ["evidence-question"]},
                {"id": "right", "blockIds": ["claim-text"]},
            ],
        }
        plan = audit_course_draft(blueprint)
        self.assertIn(
            "assessment-should-be-right",
            {issue["code"] for issue in plan["slices"][0]["issues"]},
        )

    def test_horizontal_split_prefers_one_to_one_without_aspect_exception(self):
        blueprint = json.loads(APPROVED.read_text(encoding="utf-8"))
        slice_data = blueprint["course"]["parts"][0]["slices"][0]
        slice_data["layout"]["ratio"] = "3:2"

        plan = audit_course_draft(blueprint)

        self.assertIn(
            "split-ratio-should-default-one-to-one",
            {issue["code"] for issue in plan["slices"][0]["issues"]},
        )

    def test_split_layout_cannot_leave_a_dead_empty_slot(self):
        blueprint = json.loads(APPROVED.read_text(encoding="utf-8"))
        slice_data = blueprint["course"]["parts"][0]["slices"][0]
        slice_data["layout"] = {
            "preset": "split-horizontal",
            "ratio": "3:1",
            "slots": [
                {
                    "id": "left",
                    "blockIds": ["claim-text", "evidence-question"],
                },
                {"id": "right", "blockIds": []},
            ],
        }

        plan = audit_course_draft(blueprint)

        self.assertIn(
            "layout-empty-slot",
            {issue["code"] for issue in plan["slices"][0]["issues"]},
        )
        self.assertFalse(plan["summary"]["ready"])

    def test_grid_may_use_two_to_four_cells(self):
        blueprint = json.loads(APPROVED.read_text(encoding="utf-8"))
        slice_data = blueprint["course"]["parts"][0]["slices"][0]
        for cell_count in (2, 3, 4):
            blocks = copy.deepcopy(slice_data["blocks"])
            while len(blocks) < cell_count:
                index = len(blocks) + 1
                blocks.append({"id": f"supporting-text-{index}", "type": "text", "content": "Supporting explanation."})
            candidate = copy.deepcopy(blueprint)
            candidate_slice = candidate["course"]["parts"][0]["slices"][0]
            candidate_slice["blocks"] = blocks[:cell_count]
            candidate_slice["layout"] = {
                "preset": "grid",
                "slots": [
                    {"id": f"cell-{index + 1}", "blockIds": [block["id"]]}
                    for index, block in enumerate(blocks[:cell_count])
                ],
            }

            plan = audit_course_draft(candidate)

            with self.subTest(cell_count=cell_count):
                self.assertNotIn(
                    "invalid-layout-slots",
                    {issue["code"] for issue in plan["slices"][0]["issues"]},
                )

    def test_repeated_first_option_answers_are_rejected_as_an_authoring_pattern(self):
        blueprint = json.loads(APPROVED.read_text(encoding="utf-8"))
        original = blueprint["course"]["parts"][0]["slices"][0]
        slices = []
        for index in range(3):
            slice_data = copy.deepcopy(original)
            slice_data["id"] = f"question-slice-{index + 1}"
            question = next(block for block in slice_data["blocks"] if block["type"] == "singleChoice")
            question["id"] = f"question-{index + 1}"
            question["assessment"]["correctOptionId"] = question["options"][0]["id"]
            for slot in slice_data["layout"]["slots"]:
                slot["blockIds"] = [question["id"] if block_id == "evidence-question" else block_id for block_id in slot["blockIds"]]
            slices.append(slice_data)
        blueprint["course"]["parts"][0]["slices"] = slices

        plan = audit_course_draft(blueprint)

        self.assertIn(
            "single-choice-answer-position-pattern",
            {issue["code"] for issue in plan["courseIssues"]},
        )

    def test_video_must_own_the_wider_horizontal_slot(self):
        blueprint = json.loads(APPROVED.read_text(encoding="utf-8"))
        slice_data = blueprint["course"]["parts"][0]["slices"][0]
        slice_data["blocks"][0] = {
            "id": "claim-text",
            "type": "video",
            "source": "assets/videos/claim.mp4",
        }
        slice_data["layout"]["ratio"] = "1:2"

        plan = audit_course_draft(blueprint)

        issues = plan["slices"][0]["issues"]
        self.assertIn("video-slot-too-narrow", {issue["code"] for issue in issues})

    def test_pdf_horizontal_split_stays_one_to_one(self):
        blueprint = json.loads(APPROVED.read_text(encoding="utf-8"))
        slice_data = blueprint["course"]["parts"][0]["slices"][0]
        slice_data["blocks"][1] = {
            "id": "evidence-question",
            "type": "pdf",
            "source": "assets/pdfs/evidence.pdf",
            "title": "Evidence",
        }
        slice_data["layout"]["ratio"] = "1:1"

        plan = audit_course_draft(blueprint)

        codes = {issue["code"] for issue in plan["slices"][0]["issues"]}
        self.assertNotIn("pdf-slot-too-narrow", codes)
        self.assertNotIn("split-ratio-should-default-one-to-one", codes)

    def test_large_video_with_short_supporting_text_may_use_asymmetric_split(self):
        blueprint = json.loads(APPROVED.read_text(encoding="utf-8"))
        slice_data = blueprint["course"]["parts"][0]["slices"][0]
        slice_data["blocks"] = [
            {
                "id": "case-video",
                "type": "video",
                "source": "assets/videos/case.mp4",
                "blocking": False,
                "completion": {"rule": "video-ended"},
            },
            {
                "id": "supporting-text",
                "type": "text",
                "content": "Watch for the change in evidence.",
            },
        ]
        slice_data["layout"] = {
            "preset": "split-horizontal",
            "ratio": "3:1",
            "slots": [
                {"id": "left", "blockIds": ["case-video"]},
                {"id": "right", "blockIds": ["supporting-text"]},
            ],
        }

        plan = audit_course_draft(blueprint)
        codes = {issue["code"] for issue in plan["slices"][0]["issues"]}

        self.assertNotIn("split-ratio-should-default-one-to-one", codes)
        self.assertNotIn("video-slot-too-narrow", codes)

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
