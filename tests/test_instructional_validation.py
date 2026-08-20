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
                {"id": "start", "enterActions": [{"type": "startTimer", "timerId": "choice", "durationSeconds": 5}], "transitions": [{"on": {"type": "student.continue"}, "to": "reference-only"}, {"on": {"type": "timer.elapsed", "sourceId": "choice"}, "to": "answer-only"}]},
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

    def test_hidden_answer_event_cannot_reveal_that_answer(self):
        course = course_document()
        answer = course["course"]["parts"][0]["slices"][0]["blocks"][3]
        answer["assessment"] = {"mode": "graded", "correctOptionId": "a"}
        course["course"]["parts"][0]["slices"][0]["workflow"] = {
            "version": "1.0", "initialStepId": "wait",
            "initialState": {"visibleBlockIds": ["reference-text", "source-pdf", "source-image"], "enabledBlockIds": []},
            "steps": [
                {"id": "wait", "enterActions": [], "transitions": [{"on": {"type": "answer.correct", "sourceId": "answer-block"}, "to": "reveal"}]},
                {"id": "reveal", "enterActions": [{"type": "show", "targetId": "answer-block"}, {"type": "enable", "targetId": "answer-block"}], "transitions": []},
            ],
        }

        findings = {(issue.path, issue.code) for issue in validate_workflow_availability(course)}

        self.assertIn((f"{PATH}/block:answer-block", "workflow-answer-unavailable"), findings)

    def test_covisibility_must_hold_on_every_reachable_answerable_path(self):
        course = course_document()
        course["course"]["parts"][0]["slices"][0]["workflow"] = {
            "version": "1.0", "initialStepId": "answer-with-reference",
            "initialState": {"visibleBlockIds": ["reference-text", "source-pdf", "source-image", "answer-block"], "enabledBlockIds": ["answer-block"]},
            "steps": [
                {"id": "answer-with-reference", "enterActions": [], "transitions": [{"on": {"type": "student.continue"}, "to": "answer-without-reference"}]},
                {"id": "answer-without-reference", "enterActions": [{"type": "hide", "targetId": "source-pdf"}, {"type": "hide", "targetId": "source-image"}], "transitions": []},
            ],
        }

        findings = {(issue.path, issue.code) for issue in self.correspondence(course)}

        self.assertIn((f"{PATH}/block:answer-block", "workflow-covisibility-unavailable"), findings)

    def test_plan_completion_event_respects_survey_and_graded_renderer_modes(self):
        plan = plan_document()
        plan["parts"][0]["slices"][0]["completionEvidence"] = {"event": "answer.correct"}
        write_json_atomic(self.root / ".course-work/course-storyboard.json", plan)
        survey = course_document()
        survey["course"]["parts"][0]["slices"][0]["workflow"]["steps"][0]["transitions"][0]["on"]["type"] = "answer.correct"

        survey_findings = {(issue.path, issue.code) for issue in self.correspondence(survey)}
        self.assertIn((f"{PATH}/block:answer-block", "plan-completion-event-unreachable"), survey_findings)

        graded = course_document()
        graded["course"]["parts"][0]["slices"][0]["blocks"][3]["assessment"] = {"mode": "graded", "correctOptionId": "a"}
        graded["course"]["parts"][0]["slices"][0]["workflow"]["steps"][0]["transitions"][0]["on"]["type"] = "answer.correct"

        self.assertNotIn(
            (f"{PATH}/block:answer-block", "plan-completion-event-unreachable"),
            {(issue.path, issue.code) for issue in self.correspondence(graded)},
        )

    def test_reversed_split_slot_order_is_not_canonical(self):
        horizontal = course_document()
        horizontal["course"]["parts"][0]["slices"][0]["layout"]["slots"].reverse()
        vertical = course_document()
        layout = vertical["course"]["parts"][0]["slices"][0]["layout"]
        layout["preset"] = "split-vertical"
        layout["slots"][0]["id"] = "bottom"
        layout["slots"][1]["id"] = "top"
        full = course_document()
        full_layout = full["course"]["parts"][0]["slices"][0]["layout"]
        full_layout["preset"] = "full"
        full_layout.pop("ratio")
        full_layout["slots"] = [{"id": "content", "blockIds": ["reference-text", "source-pdf", "source-image", "answer-block"]}]

        for course in (horizontal, vertical, full):
            self.assertIn(
                (PATH, "layout-slot-ids-invalid"),
                {(issue.path, issue.code) for issue in validate_layout_assignment(course)},
            )

    def test_unstarted_timer_and_unplayed_narration_do_not_make_reveal_reachable(self):
        for event, narrations in (
            ({"type": "timer.elapsed", "sourceId": "wait"}, []),
            ({"type": "narration.ended", "sourceId": "intro"}, [{"id": "intro", "text": "开场", "audio": "audio/intro.mp3"}]),
        ):
            course = course_document()
            slice_data = course["course"]["parts"][0]["slices"][0]
            slice_data["narrations"] = narrations
            slice_data["workflow"] = {
                "version": "1.0", "initialStepId": "wait",
                "initialState": {"visibleBlockIds": ["reference-text", "source-pdf", "source-image"], "enabledBlockIds": []},
                "steps": [
                    {"id": "wait", "enterActions": [], "transitions": [{"on": event, "to": "reveal"}]},
                    {"id": "reveal", "enterActions": [{"type": "show", "targetId": "answer-block"}, {"type": "enable", "targetId": "answer-block"}], "transitions": []},
                ],
            }

            self.assertIn(
                (f"{PATH}/block:answer-block", "workflow-answer-unavailable"),
                {(issue.path, issue.code) for issue in validate_workflow_availability(course)},
            )

    def test_replaced_narration_cannot_later_emit_its_ended_event(self):
        course = course_document()
        slice_data = course["course"]["parts"][0]["slices"][0]
        slice_data["narrations"] = [
            {"id": "first", "text": "第一段", "audio": "audio/first.mp3"},
            {"id": "second", "text": "第二段", "audio": "audio/second.mp3"},
        ]
        slice_data["workflow"] = {
            "version": "1.0", "initialStepId": "play-first",
            "initialState": {"visibleBlockIds": ["reference-text", "source-pdf", "source-image"], "enabledBlockIds": []},
            "steps": [
                {"id": "play-first", "enterActions": [{"type": "playNarration", "narrationId": "first"}], "transitions": [{"on": {"type": "student.continue"}, "to": "replace"}]},
                {"id": "replace", "enterActions": [{"type": "playNarration", "narrationId": "second"}], "transitions": [{"on": {"type": "narration.ended", "sourceId": "first"}, "to": "reveal"}]},
                {"id": "reveal", "enterActions": [{"type": "show", "targetId": "answer-block"}, {"type": "enable", "targetId": "answer-block"}], "transitions": []},
            ],
        }

        self.assertIn(
            (f"{PATH}/block:answer-block", "workflow-answer-unavailable"),
            {(issue.path, issue.code) for issue in validate_workflow_availability(course)},
        )

    def test_one_shot_block_completion_cannot_be_reused_across_steps(self):
        course = course_document()
        slice_data = course["course"]["parts"][0]["slices"][0]
        slice_data["blocks"].append(
            {"id": "followup", "type": "fillBlank", "prompt": "补充说明", "assessment": {"mode": "reflection", "rubric": "说明理由"}, "completion": {"rule": "submit-any"}}
        )
        slice_data["workflow"] = {
            "version": "1.0", "initialStepId": "first-completion",
            "initialState": {"visibleBlockIds": ["reference-text", "source-pdf", "source-image", "answer-block"], "enabledBlockIds": ["answer-block"]},
            "steps": [
                {"id": "first-completion", "enterActions": [], "transitions": [{"on": {"type": "block.completed", "sourceId": "answer-block"}, "to": "reused-completion"}]},
                {"id": "reused-completion", "enterActions": [], "transitions": [{"on": {"type": "block.completed", "sourceId": "answer-block"}, "to": "reveal-followup"}]},
                {"id": "reveal-followup", "enterActions": [{"type": "show", "targetId": "followup"}, {"type": "enable", "targetId": "followup"}], "transitions": []},
            ],
        }

        self.assertIn(
            (f"{PATH}/block:followup", "workflow-answer-unavailable"),
            {(issue.path, issue.code) for issue in validate_workflow_availability(course)},
        )

    def test_successive_wildcard_timers_consume_one_timer_per_transition(self):
        course = course_document()
        course["course"]["parts"][0]["slices"][0]["workflow"] = {
            "version": "1.0", "initialStepId": "start-timers",
            "initialState": {"visibleBlockIds": ["reference-text", "source-pdf", "source-image"], "enabledBlockIds": []},
            "steps": [
                {"id": "start-timers", "enterActions": [{"type": "startTimer", "timerId": "first", "durationSeconds": 5}, {"type": "startTimer", "timerId": "second", "durationSeconds": 10}], "transitions": [{"on": {"type": "timer.elapsed"}, "to": "after-one"}]},
                {"id": "after-one", "enterActions": [], "transitions": [{"on": {"type": "timer.elapsed"}, "to": "reveal"}]},
                {"id": "reveal", "enterActions": [{"type": "show", "targetId": "answer-block"}, {"type": "enable", "targetId": "answer-block"}], "transitions": []},
            ],
        }

        self.assertNotIn(
            (f"{PATH}/block:answer-block", "workflow-answer-unavailable"),
            {(issue.path, issue.code) for issue in validate_workflow_availability(course)},
        )

    def test_graded_retries_keep_submitted_and_incorrect_reachable_until_max_attempts(self):
        course = course_document()
        slice_data = course["course"]["parts"][0]["slices"][0]
        answer = slice_data["blocks"][3]
        answer["assessment"] = {"mode": "graded", "correctOptionId": "a"}
        answer["completion"] = {"rule": "submit-correct-or-exhausted", "maxAttempts": 3}
        slice_data["blocks"].append({"id": "followup", "type": "fillBlank", "prompt": "说明补救", "assessment": {"mode": "reflection", "rubric": "说明"}, "completion": {"rule": "submit-any"}})
        slice_data["workflow"] = {
            "version": "1.0", "initialStepId": "first-submit",
            "initialState": {"visibleBlockIds": ["reference-text", "source-pdf", "source-image", "answer-block"], "enabledBlockIds": ["answer-block"]},
            "steps": [
                {"id": "first-submit", "enterActions": [], "transitions": [{"on": {"type": "answer.submitted", "sourceId": "answer-block"}, "to": "first-outcome"}]},
                {"id": "first-outcome", "enterActions": [], "transitions": [{"on": {"type": "answer.incorrect", "sourceId": "answer-block"}, "to": "remediate"}]},
                {"id": "remediate", "enterActions": [], "transitions": [{"on": {"type": "student.continue"}, "to": "second-submit"}]},
                {"id": "second-submit", "enterActions": [], "transitions": [{"on": {"type": "answer.submitted", "sourceId": "answer-block"}, "to": "second-outcome"}]},
                {"id": "second-outcome", "enterActions": [], "transitions": [{"on": {"type": "answer.incorrect", "sourceId": "answer-block"}, "to": "reveal-followup"}]},
                {"id": "reveal-followup", "enterActions": [{"type": "show", "targetId": "followup"}, {"type": "enable", "targetId": "followup"}], "transitions": []},
            ],
        }

        self.assertNotIn((f"{PATH}/block:followup", "workflow-answer-unavailable"), {(issue.path, issue.code) for issue in validate_workflow_availability(course)})

    def test_assessment_cascade_survives_a_submitted_transition_that_disables_source(self):
        course = course_document()
        slice_data = course["course"]["parts"][0]["slices"][0]
        slice_data["blocks"].append({"id": "followup", "type": "fillBlank", "prompt": "后续", "assessment": {"mode": "reflection", "rubric": "说明"}, "completion": {"rule": "submit-any"}})
        slice_data["workflow"] = {
            "version": "1.0", "initialStepId": "submitted",
            "initialState": {"visibleBlockIds": ["reference-text", "source-pdf", "source-image", "answer-block"], "enabledBlockIds": ["answer-block"]},
            "steps": [
                {"id": "submitted", "enterActions": [], "transitions": [{"on": {"type": "answer.submitted", "sourceId": "answer-block"}, "to": "disabled"}]},
                {"id": "disabled", "enterActions": [{"type": "disable", "targetId": "answer-block"}], "transitions": [{"on": {"type": "block.completed", "sourceId": "answer-block"}, "to": "reveal-followup"}]},
                {"id": "reveal-followup", "enterActions": [{"type": "show", "targetId": "followup"}, {"type": "enable", "targetId": "followup"}], "transitions": []},
            ],
        }

        self.assertNotIn((f"{PATH}/block:followup", "workflow-answer-unavailable"), {(issue.path, issue.code) for issue in validate_workflow_availability(course)})

    def test_assessment_submissions_do_not_reuse_past_max_attempts(self):
        course = course_document()
        slice_data = course["course"]["parts"][0]["slices"][0]
        answer = slice_data["blocks"][3]
        answer["assessment"] = {"mode": "graded", "correctOptionId": "a"}
        answer["completion"] = {"rule": "submit-correct-or-exhausted", "maxAttempts": 3}
        slice_data["blocks"].append({"id": "followup", "type": "fillBlank", "prompt": "后续", "assessment": {"mode": "reflection", "rubric": "说明"}, "completion": {"rule": "submit-any"}})
        steps = [
            {"id": "attempt-one", "enterActions": [], "transitions": [{"on": {"type": "answer.submitted", "sourceId": "answer-block"}, "to": "attempt-two"}]},
            {"id": "attempt-two", "enterActions": [], "transitions": [{"on": {"type": "answer.submitted", "sourceId": "answer-block"}, "to": "attempt-three"}]},
            {"id": "attempt-three", "enterActions": [], "transitions": [{"on": {"type": "answer.submitted", "sourceId": "answer-block"}, "to": "attempt-four"}]},
            {"id": "attempt-four", "enterActions": [], "transitions": [{"on": {"type": "answer.submitted", "sourceId": "answer-block"}, "to": "reveal"}]},
            {"id": "reveal", "enterActions": [{"type": "show", "targetId": "followup"}, {"type": "enable", "targetId": "followup"}], "transitions": []},
        ]
        slice_data["workflow"] = {"version": "1.0", "initialStepId": "attempt-one", "initialState": {"visibleBlockIds": ["reference-text", "source-pdf", "source-image", "answer-block"], "enabledBlockIds": ["answer-block"]}, "steps": steps}

        self.assertIn((f"{PATH}/block:followup", "workflow-answer-unavailable"), {(issue.path, issue.code) for issue in validate_workflow_availability(course)})

    def test_disabled_video_cannot_play_or_reveal_an_answer(self):
        course = course_document()
        slice_data = course["course"]["parts"][0]["slices"][0]
        slice_data["blocks"].append({"id": "video", "type": "video", "source": "materials/video.mp4", "completion": {"rule": "video-ended"}})
        slice_data["workflow"] = {
            "version": "1.0", "initialStepId": "play",
            "initialState": {"visibleBlockIds": ["reference-text", "source-pdf", "source-image", "video"], "enabledBlockIds": []},
            "steps": [
                {"id": "play", "enterActions": [{"type": "playBlock", "targetId": "video"}], "transitions": [{"on": {"type": "video.started", "sourceId": "video"}, "to": "reveal"}]},
                {"id": "reveal", "enterActions": [{"type": "show", "targetId": "answer-block"}, {"type": "enable", "targetId": "answer-block"}], "transitions": []},
            ],
        }

        self.assertIn((f"{PATH}/block:answer-block", "workflow-answer-unavailable"), {(issue.path, issue.code) for issue in validate_workflow_availability(course)})

    def test_video_reset_rearms_playback_for_a_second_completion(self):
        course = course_document()
        slice_data = course["course"]["parts"][0]["slices"][0]
        slice_data["blocks"].append({"id": "video", "type": "video", "source": "materials/video.mp4", "completion": {"rule": "video-ended"}})
        slice_data["workflow"] = {
            "version": "1.0", "initialStepId": "first-play",
            "initialState": {"visibleBlockIds": ["reference-text", "source-pdf", "source-image", "video"], "enabledBlockIds": ["video"]},
            "steps": [
                {"id": "first-play", "enterActions": [{"type": "playBlock", "targetId": "video"}], "transitions": [{"on": {"type": "video.started", "sourceId": "video"}, "to": "first-ended"}]},
                {"id": "first-ended", "enterActions": [], "transitions": [{"on": {"type": "video.ended", "sourceId": "video"}, "to": "replay"}]},
                {"id": "replay", "enterActions": [{"type": "resetBlock", "targetId": "video"}, {"type": "playBlock", "targetId": "video"}], "transitions": [{"on": {"type": "video.started", "sourceId": "video"}, "to": "second-ended"}]},
                {"id": "second-ended", "enterActions": [], "transitions": [{"on": {"type": "video.ended", "sourceId": "video"}, "to": "reveal"}]},
                {"id": "reveal", "enterActions": [{"type": "show", "targetId": "answer-block"}, {"type": "enable", "targetId": "answer-block"}], "transitions": []},
            ],
        }

        self.assertNotIn((f"{PATH}/block:answer-block", "workflow-answer-unavailable"), {(issue.path, issue.code) for issue in validate_workflow_availability(course)})

    def test_repeated_timer_id_and_cancel_consume_one_handle_at_a_time(self):
        course = course_document()
        course["course"]["parts"][0]["slices"][0]["workflow"] = {
            "version": "1.0", "initialStepId": "start",
            "initialState": {"visibleBlockIds": ["reference-text", "source-pdf", "source-image"], "enabledBlockIds": []},
            "steps": [
                {"id": "start", "enterActions": [{"type": "startTimer", "timerId": "same", "durationSeconds": 5}, {"type": "startTimer", "timerId": "same", "durationSeconds": 10}], "transitions": [{"on": {"type": "student.continue"}, "to": "cancel-one"}]},
                {"id": "cancel-one", "enterActions": [{"type": "cancelTimer", "timerId": "same"}], "transitions": [{"on": {"type": "timer.elapsed", "sourceId": "same"}, "to": "reveal"}]},
                {"id": "reveal", "enterActions": [{"type": "show", "targetId": "answer-block"}, {"type": "enable", "targetId": "answer-block"}], "transitions": []},
            ],
        }

        self.assertNotIn((f"{PATH}/block:answer-block", "workflow-answer-unavailable"), {(issue.path, issue.code) for issue in validate_workflow_availability(course)})
