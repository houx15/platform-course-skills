import tempfile
import unittest
from pathlib import Path

from course_toolkit.instructional_validation import (
    validate_layout_assignment,
    validate_plan_correspondence,
    validate_workflow_availability,
)
from course_toolkit.jsonio import write_json_atomic


PART = "part-evidence"
SLICE = "slice-read-source"
PATH = f"part:{PART}/slice:{SLICE}"


def course_document():
    return {
        "schemaVersion": "2.0",
        "course": {
            "id": "instructional-validation",
            "parts": [
                {
                    "id": PART,
                    "slices": [
                        {
                            "id": SLICE,
                            "blocks": [
                                {"id": "reference-text", "type": "text", "content": "参考上面的原文，选择最合适的结论。"},
                                {"id": "source-pdf", "type": "pdf", "title": "原文", "source": "materials/original.pdf"},
                                {"id": "source-image", "type": "images", "presentation": "single", "items": [{"id": "source-image-item", "source": "materials/figure.png", "alt": "证据图"}]},
                                {"id": "answer-block", "type": "singleChoice", "prompt": "证据支持哪项判断？", "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}], "assessment": {"mode": "survey"}, "completion": {"rule": "submit-any"}},
                            ],
                            "layout": {"preset": "split-horizontal", "ratio": "1:1", "slots": [{"id": "left", "blockIds": ["reference-text", "source-pdf", "source-image"]}, {"id": "right", "blockIds": ["answer-block"]}]},
                            "workflow": {"version": "1.0", "initialStepId": "answer", "initialState": {"visibleBlockIds": ["reference-text", "source-pdf", "source-image", "answer-block"], "enabledBlockIds": ["answer-block"]}, "steps": [{"id": "answer", "enterActions": [], "transitions": [{"on": {"type": "block.completed", "sourceId": "answer-block"}, "to": "complete"}]}, {"id": "complete", "enterActions": [{"type": "completeSlice"}], "transitions": []}]},
                        }
                    ],
                }
            ],
        },
    }


def coverage_document():
    return {
        "schemaVersion": "2.0",
        "items": [
            {"sourceId": "source-original", "sourceFile": "materials/original.pdf", "location": "page:1", "summary": "需同时查看的原文", "disposition": "required-evidence", "bindings": [{"partId": PART, "sliceId": SLICE, "blockId": "source-pdf", "role": "question-reference", "supportsIds": ["answer-block"]}]},
            {"sourceId": "source-figure", "sourceFile": "materials/figure.png", "location": "image:1", "summary": "需对应问题的图", "disposition": "required-evidence", "bindings": [{"partId": PART, "sliceId": SLICE, "blockId": "source-image", "role": "question-reference", "supportsIds": ["answer-block"]}]},
        ],
    }


def plan_document():
    return {
        "schemaVersion": "2.0",
        "title": "证据判断",
        "parts": [{"partId": PART, "title": "证据", "slices": [{
            "partId": PART,
            "sliceId": SLICE,
            "title": "读原文并作答",
            "teachingPurpose": "让学生在原文和图的支持下作答。",
            "sourceUses": [{"sourceId": "source-original", "locator": "page:1", "materialRole": "原文证据"}, {"sourceId": "source-figure", "locator": "image:1", "materialRole": "图示证据"}],
            "learnerSees": "原文、图和题目。",
            "learnerAction": {"kind": "answer", "description": "参考原文和图作答。", "referencePolicy": "co-visible", "referenceSourceIds": ["source-original", "source-figure"], "targetId": "question:answer-block"},
            "completionEvidence": {"event": "block.completed"},
            "layoutIntent": {"preset": "split-horizontal", "ratio": "1:1"},
            "coVisibleRequirements": [{"sourceId": "source-original", "targetId": "question:answer-block", "reason": "作答时必须看到原文。"}, {"sourceId": "source-figure", "targetId": "question:answer-block", "reason": "作答时必须看到图。"}],
            "imageRelationships": [{"sourceId": "source-figure", "targetType": "question", "targetId": "question:answer-block", "relationship": "图示支持题目。"}],
            "unresolvedBlockers": [],
            "proposedExclusions": [],
        }]}],
    }


class InstructionalValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        write_json_atomic(self.root / ".course-work/course-storyboard.json", plan_document())
        write_json_atomic(self.root / ".course-work/source-coverage.json", coverage_document())

    def tearDown(self):
        self.temporary.cleanup()

    def correspondence(self, course=None):
        return validate_plan_correspondence(self.root, course or course_document())

    def test_required_image_omitted_has_stable_part_slice_block_path(self):
        course = course_document()
        course["course"]["parts"][0]["slices"][0]["blocks"] = [
            block for block in course["course"]["parts"][0]["slices"][0]["blocks"] if block["id"] != "source-image"
        ]

        issues = self.correspondence(course)

        self.assertIn(
            (f"{PATH}/block:source-image", "plan-required-source-omitted"),
            {(issue.path, issue.code) for issue in issues},
        )

    def test_split_stack_with_empty_side_has_stable_block_path(self):
        course = course_document()
        course["course"]["parts"][0]["slices"][0]["layout"]["slots"] = [
            {"id": "left", "blockIds": ["reference-text", "source-pdf", "source-image", "answer-block"]},
            {"id": "right", "blockIds": []},
        ]

        issues = validate_layout_assignment(course)

        findings = {(issue.path, issue.code) for issue in issues}
        self.assertIn((f"{PATH}/block:reference-text", "layout-split-stack-empty-side"), findings)
        self.assertIn((f"{PATH}/layout-slot:1", "layout-empty-slot"), findings)

    def test_image_bound_to_wrong_support_target_is_blocked(self):
        coverage = coverage_document()
        coverage["items"][1]["bindings"][0]["supportsIds"] = ["other-question"]
        write_json_atomic(self.root / ".course-work/source-coverage.json", coverage)

        issues = self.correspondence()

        self.assertIn(
            (f"{PATH}/block:answer-block", "image-support-target-mismatch"),
            {(issue.path, issue.code) for issue in issues},
        )

    def test_deictic_reference_requires_source_surface_in_same_slice(self):
        course = course_document()
        course["course"]["parts"][0]["slices"][0]["blocks"] = [
            block for block in course["course"]["parts"][0]["slices"][0]["blocks"] if block["id"] != "source-pdf"
        ]

        issues = self.correspondence(course)

        self.assertIn(
            (f"{PATH}/block:reference-text", "deictic-reference-source-absent"),
            {(issue.path, issue.code) for issue in issues},
        )

    def test_valid_co_visible_reference_and_answer_slice_passes(self):
        course = course_document()

        self.assertEqual(self.correspondence(course), [])
        self.assertEqual(validate_layout_assignment(course), [])
        self.assertEqual(validate_workflow_availability(course), [])

    def test_workflow_reports_enable_before_reveal_and_unreachable_completion(self):
        course = course_document()
        slice_data = course["course"]["parts"][0]["slices"][0]
        slice_data["workflow"] = {
            "version": "1.0",
            "initialStepId": "start",
            "initialState": {"visibleBlockIds": ["reference-text"], "enabledBlockIds": []},
            "steps": [{"id": "start", "enterActions": [{"type": "enable", "targetId": "answer-block"}], "transitions": []}],
        }

        findings = {(issue.path, issue.code) for issue in validate_workflow_availability(course)}

        self.assertIn((f"{PATH}/block:answer-block", "workflow-enable-before-reveal"), findings)
        self.assertIn((f"{PATH}/block:answer-block", "workflow-completion-unreachable"), findings)

    def test_unreachable_completion_transition_does_not_satisfy_availability(self):
        course = course_document()
        course["course"]["parts"][0]["slices"][0]["workflow"] = {
            "version": "1.0",
            "initialStepId": "start",
            "initialState": {"visibleBlockIds": ["answer-block"], "enabledBlockIds": ["answer-block"]},
            "steps": [
                {"id": "start", "enterActions": [], "transitions": []},
                {"id": "unreachable", "enterActions": [], "transitions": [{"on": {"type": "block.completed", "sourceId": "answer-block"}, "to": "complete"}]},
                {"id": "complete", "enterActions": [{"type": "completeSlice"}], "transitions": []},
            ],
        }

        findings = {(issue.path, issue.code) for issue in validate_workflow_availability(course)}

        self.assertIn((f"{PATH}/block:answer-block", "workflow-completion-unreachable"), findings)

    def test_plan_completion_event_must_match_a_reachable_transition(self):
        plan = plan_document()
        plan["parts"][0]["slices"][0]["completionEvidence"] = {"event": "answer.submitted"}
        write_json_atomic(self.root / ".course-work/course-storyboard.json", plan)

        findings = {(issue.path, issue.code) for issue in self.correspondence()}

        self.assertIn((f"{PATH}/block:answer-block", "plan-completion-event-unreachable"), findings)

    def test_branch_states_are_not_unioned_into_false_covisibility(self):
        course = course_document()
        course["course"]["parts"][0]["slices"][0]["workflow"] = {
            "version": "1.0", "initialStepId": "start",
            "initialState": {"visibleBlockIds": ["reference-text", "source-pdf", "source-image", "answer-block"], "enabledBlockIds": []},
            "steps": [
                {"id": "start", "enterActions": [], "transitions": [{"on": {"type": "student.continue"}, "to": "reference-only"}, {"on": {"type": "timer.elapsed"}, "to": "answer-only"}]},
                {"id": "reference-only", "enterActions": [], "transitions": [{"on": {"type": "student.continue"}, "to": "join"}]},
                {"id": "answer-only", "enterActions": [{"type": "hide", "targetId": "source-pdf"}, {"type": "hide", "targetId": "source-image"}, {"type": "enable", "targetId": "answer-block"}], "transitions": [{"on": {"type": "student.continue"}, "to": "join"}]},
                {"id": "join", "enterActions": [], "transitions": [{"on": {"type": "block.completed", "sourceId": "answer-block"}, "to": "complete"}]},
                {"id": "complete", "enterActions": [{"type": "completeSlice"}], "transitions": []},
            ],
        }

        findings = {(issue.path, issue.code) for issue in self.correspondence(course)}

        self.assertIn((f"{PATH}/block:answer-block", "workflow-covisibility-unavailable"), findings)

    def test_hiding_reference_before_answer_blocks_covisibility(self):
        course = course_document()
        course["course"]["parts"][0]["slices"][0]["workflow"] = {
            "version": "1.0", "initialStepId": "hide-reference",
            "initialState": {"visibleBlockIds": ["reference-text", "source-pdf", "source-image", "answer-block"], "enabledBlockIds": []},
            "steps": [
                {"id": "hide-reference", "enterActions": [{"type": "hide", "targetId": "source-pdf"}, {"type": "hide", "targetId": "source-image"}], "transitions": [{"on": {"type": "student.continue"}, "to": "answer"}]},
                {"id": "answer", "enterActions": [{"type": "enable", "targetId": "answer-block"}], "transitions": [{"on": {"type": "block.completed", "sourceId": "answer-block"}, "to": "complete"}]},
                {"id": "complete", "enterActions": [{"type": "completeSlice"}], "transitions": []},
            ],
        }

        self.assertIn(
            (f"{PATH}/block:answer-block", "workflow-covisibility-unavailable"),
            {(issue.path, issue.code) for issue in self.correspondence(course)},
        )

    def test_show_then_enable_in_same_step_is_available(self):
        course = course_document()
        course["course"]["parts"][0]["slices"][0]["workflow"] = {
            "version": "1.0", "initialStepId": "show-answer",
            "initialState": {"visibleBlockIds": ["reference-text", "source-pdf", "source-image"], "enabledBlockIds": []},
            "steps": [
                {"id": "show-answer", "enterActions": [{"type": "show", "targetId": "answer-block"}, {"type": "enable", "targetId": "answer-block"}], "transitions": [{"on": {"type": "block.completed", "sourceId": "answer-block"}, "to": "complete"}]},
                {"id": "complete", "enterActions": [{"type": "completeSlice"}], "transitions": []},
            ],
        }

        codes = {issue.code for issue in validate_workflow_availability(course)}

        self.assertNotIn("workflow-enable-before-reveal", codes)
        self.assertNotIn("workflow-answer-unavailable", codes)

    def test_source_map_runtime_pointer_mismatch_blocks_correspondence(self):
        write_json_atomic(
            self.root / ".course-work/course-runtime-source-map.json",
            {"mappings": [{"targetId": "block:source-pdf", "runtimePointer": "/course/parts/99/slices/99/blocks/99", "sourceIds": ["source-original"]}]},
        )
        course = course_document()
        course["course"]["parts"][0]["slices"][0]["blocks"] = [
            block for block in course["course"]["parts"][0]["slices"][0]["blocks"] if block["id"] != "source-pdf"
        ]
        # Keep a source-mapped text target so correspondence cannot fall back to
        # a typed asset path for the planned original.
        course["course"]["parts"][0]["slices"][0]["blocks"].append({"id": "source-pdf", "type": "text", "content": "原文摘要"})

        findings = {(issue.path, issue.code) for issue in self.correspondence(course)}

        self.assertIn((f"{PATH}/block:source-pdf", "source-map-pointer-mismatch"), findings)

    def test_invalid_slot_ids_are_reported_by_public_layout_check(self):
        course = course_document()
        course["course"]["parts"][0]["slices"][0]["layout"]["slots"][0]["id"] = "evidence"

        self.assertIn(
            (PATH, "layout-slot-ids-invalid"),
            {(issue.path, issue.code) for issue in validate_layout_assignment(course)},
        )
