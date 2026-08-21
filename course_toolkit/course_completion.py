import copy
import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from course_toolkit.jsonio import write_json_atomic


CATALOG_VERSION = "1.0"
TARGET_CONTRACT_VERSION = "2.0"
COMPLETION_PLAN_VERSION = "1.0"
VALID_LAYOUT_SLOTS = {
    "full": ("main",),
    "split-horizontal": ("left", "right"),
    "split-vertical": ("top", "bottom"),
}
VALID_SPLIT_RATIOS = {"1:1", "3:2", "2:3", "2:1", "1:2", "3:1", "1:3"}


def _canonical_hash(data: object) -> str:
    encoded = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _issue(
    path: str,
    code: str,
    message: str,
    *,
    category: str = "generation",
    severity: str = "blocker",
) -> dict:
    return {
        "path": path,
        "code": code,
        "category": category,
        "severity": severity,
        "message": message,
    }


def _course_from_draft(draft: object) -> Optional[dict]:
    if not isinstance(draft, dict):
        return None
    course = draft.get("course")
    if isinstance(course, dict):
        return course
    if isinstance(draft.get("parts"), list):
        return draft
    return None


def _valid_non_empty_list(value: object) -> bool:
    return isinstance(value, list) and bool(value)


def _slice_status(issues: Sequence[dict]) -> str:
    blockers = [issue for issue in issues if issue["severity"] == "blocker"]
    if any(issue["category"] == "teacher-decision" for issue in blockers):
        return "needs-teacher-decision"
    if blockers:
        return "needs-generation"
    return "ready-for-contract-validation"


def _layout_issues(slice_data: dict, base: str) -> List[dict]:
    layout = slice_data.get("layout")
    if not isinstance(layout, dict):
        return [_issue(f"{base}.layout", "missing-layout", "Choose and fully assign a supported desktop layout.")]

    issues: List[dict] = []
    preset = layout.get("preset")
    slots = layout.get("slots")
    if preset not in {"full", "split-horizontal", "split-vertical", "grid"}:
        issues.append(_issue(f"{base}.layout.preset", "invalid-layout-preset", "Use one of the four runtime layout presets."))
    if preset in {"split-horizontal", "split-vertical"} and layout.get("ratio") not in VALID_SPLIT_RATIOS:
        issues.append(_issue(f"{base}.layout.ratio", "missing-layout-ratio", "Split layouts require an explicit supported ratio."))
    if not isinstance(slots, list):
        issues.append(_issue(f"{base}.layout.slots", "missing-layout-slots", "Layout slots must explicitly assign every Slice block."))
        return issues

    slot_ids = [slot.get("id") for slot in slots if isinstance(slot, dict)]
    expected = VALID_LAYOUT_SLOTS.get(preset)
    if expected is not None and tuple(slot_ids) != expected:
        issues.append(_issue(f"{base}.layout.slots", "invalid-layout-slots", f"The {preset} layout requires slots {list(expected)} in canonical order."))
    if preset == "grid":
        canonical = [f"cell-{index}" for index in range(1, len(slot_ids) + 1)]
        if len(slot_ids) not in {2, 3, 4} or slot_ids != canonical:
            issues.append(_issue(f"{base}.layout.slots", "invalid-layout-slots", "Grid requires two to four slots named cell-1 through cell-N in order."))

    if preset in {"split-horizontal", "split-vertical"}:
        for slot_index, slot in enumerate(slots):
            block_ids = slot.get("blockIds") if isinstance(slot, dict) else None
            if not isinstance(block_ids, list) or not block_ids:
                issues.append(
                    _issue(
                        f"{base}.layout.slots[{slot_index}].blockIds",
                        "layout-empty-slot",
                        "Split layout Slots must be non-empty. Use full for one focused Block, redistribute content across both sides, or split the teaching sequence into separate Slices.",
                    )
                )

    blocks = slice_data.get("blocks")
    block_ids = [block.get("id") for block in blocks if isinstance(block, dict)] if isinstance(blocks, list) else []
    assigned: List[object] = []
    for slot in slots:
        if isinstance(slot, dict) and isinstance(slot.get("blockIds"), list):
            assigned.extend(slot["blockIds"])
    if sorted(assigned) != sorted(block_ids) or len(assigned) != len(set(assigned)):
        issues.append(_issue(f"{base}.layout.slots", "invalid-layout-assignment", "Every Slice block must appear in exactly one layout slot."))

    # Teacher-side composition policy is deliberately narrower than the
    # student contract. The renderer keeps accepting split-vertical for
    # backward compatibility, but new courses must not turn text/assessment
    # into shallow horizontal strips.
    if preset == "split-vertical":
        issues.append(
            _issue(
                f"{base}.layout.preset",
                "split-vertical-discouraged",
                "Do not author split-vertical by default. Use a horizontal split or split the content into separate Slices.",
            )
        )

    if preset == "full" and len(block_ids) > 1:
        issues.append(
            _issue(
                f"{base}.layout.slots",
                "full-layout-stacks-blocks",
                "A full layout may contain one focused Block only; use split-horizontal/grid or split the Slice instead of stacking Blocks.",
            )
        )

    # New horizontal splits are balanced by default. The only authoring-side
    # exception is one dominant video paired with a small amount of supporting
    # text; in that case the video may own the larger column. Slot contents are
    # vertically centred by the shared renderer, not by arbitrary course CSS.
    if preset == "split-horizontal" and isinstance(blocks, list) and isinstance(slots, list):
        block_by_id = {
            block.get("id"): block
            for block in blocks
            if isinstance(block, dict) and isinstance(block.get("id"), str)
        }
        block_types = {
            block_id: block.get("type")
            for block_id, block in block_by_id.items()
        }
        def slots_containing(block_type: str) -> set:
            return {
                slot.get("id")
                for slot in slots
                if isinstance(slot, dict)
                and isinstance(slot.get("blockIds"), list)
                and any(block_types.get(block_id) == block_type for block_id in slot["blockIds"])
            }

        right_slot = next(
            (slot for slot in slots if isinstance(slot, dict) and slot.get("id") == "right"),
            None,
        )
        if isinstance(right_slot, dict) and isinstance(right_slot.get("blockIds"), list):
            answerable_types = {"singleChoice", "fillBlank", "interactiveHtml"}
            answerable_ids = {
                block_id
                for block_id, block_type in block_types.items()
                if block_type in answerable_types
            }
            if answerable_ids and not answerable_ids.intersection(right_slot["blockIds"]):
                issues.append(
                    _issue(
                        f"{base}.layout.slots",
                        "assessment-should-be-right",
                        "In a horizontal split, place the answerable Block in the right slot unless the source material requires a different reading order.",
                    )
                )

        if layout.get("ratio") in VALID_SPLIT_RATIOS:
            left_weight, right_weight = (int(value) for value in layout["ratio"].split(":"))
            video_slots = slots_containing("video")
            video_slot = next(iter(video_slots)) if len(video_slots) == 1 else None
            video_is_wider = (
                video_slot == "left" and left_weight > right_weight
            ) or (
                video_slot == "right" and right_weight > left_weight
            )
            other_slot_id = "right" if video_slot == "left" else "left"
            other_slot = next(
                (slot for slot in slots if isinstance(slot, dict) and slot.get("id") == other_slot_id),
                None,
            )
            other_ids = other_slot.get("blockIds", []) if isinstance(other_slot, dict) else []
            short_supporting_text = bool(other_ids) and all(
                block_types.get(block_id) == "text"
                for block_id in other_ids
            ) and sum(
                len(str(block_by_id.get(block_id, {}).get("content", "")))
                for block_id in other_ids
            ) <= 360
            asymmetric = left_weight != right_weight
            asymmetric_video_exception = bool(
                asymmetric
                and video_slot
                and video_is_wider
                and short_supporting_text
            )
            if asymmetric and video_slot and not video_is_wider:
                issues.append(
                    _issue(
                        f"{base}.layout.ratio",
                        "video-slot-too-narrow",
                        "When a horizontal split is asymmetric for a dominant video, the video must own the larger side.",
                    )
                )
            if asymmetric and not asymmetric_video_exception:
                issues.append(
                    _issue(
                        f"{base}.layout.ratio",
                        "split-ratio-should-default-one-to-one",
                        "Horizontal splits default to 1:1. Use an asymmetric ratio only for one dominant video paired with a small amount of supporting text.",
                    )
                )
    return issues


def _answer_position_issues(course: dict) -> List[dict]:
    graded: List[Tuple[str, int, int]] = []
    for part_index, part in enumerate(course.get("parts", [])):
        if not isinstance(part, dict):
            continue
        for slice_index, slice_data in enumerate(part.get("slices", [])):
            if not isinstance(slice_data, dict):
                continue
            for block_index, block in enumerate(slice_data.get("blocks", [])):
                if not isinstance(block, dict) or block.get("type") != "singleChoice":
                    continue
                assessment = block.get("assessment")
                options = block.get("options")
                if not isinstance(assessment, dict) or assessment.get("mode") != "graded" or not isinstance(options, list):
                    continue
                correct_id = assessment.get("correctOptionId")
                positions = [
                    index
                    for index, option in enumerate(options)
                    if isinstance(option, dict) and option.get("id") == correct_id
                ]
                if len(positions) == 1:
                    graded.append(
                        (
                            f"$.course.parts[{part_index}].slices[{slice_index}].blocks[{block_index}]",
                            positions[0],
                            len(options),
                        )
                    )
    if len(graded) >= 3 and len({position for _, position, _ in graded}) == 1:
        position = graded[0][1] + 1
        return [
            _issue(
                "$.course.parts",
                "single-choice-answer-position-pattern",
                f"All {len(graded)} graded single-choice questions use answer position {position}. Reorder options so correct answer positions vary while preserving every answer's meaning and ID binding.",
            )
        ]
    return []


def _block_issues(blocks: object, base: str) -> List[dict]:
    if not _valid_non_empty_list(blocks):
        return [_issue(f"{base}.blocks", "missing-blocks", "Add at least one complete runtime Block.")]

    issues: List[dict] = []
    for index, block in enumerate(blocks):
        path = f"{base}.blocks[{index}]"
        if not isinstance(block, dict):
            issues.append(_issue(path, "invalid-block", "Block must be an object."))
            continue
        block_type = block.get("type")
        if not isinstance(block.get("id"), str) or not block["id"].strip():
            issues.append(_issue(f"{path}.id", "missing-block-id", "Give the Block a stable lower-case hyphenated ID."))
        if block_type not in {"text", "richText", "images", "pdf", "video", "interactiveHtml", "fillBlank", "singleChoice"}:
            issues.append(_issue(f"{path}.type", "missing-block-type", "Choose one of the eight runtime Block types."))
            continue
        if block_type == "richText":
            if not isinstance(block.get("html"), str) or not block["html"].strip():
                issues.append(_issue(f"{path}.html", "missing-rich-text-html", "Write one self-contained static HTML fragment for the richText Block."))
            if block.get("completion") is not None:
                issues.append(_issue(f"{path}.completion", "rich-text-cannot-complete", "richText is display-only and cannot carry a completion rule."))
            continue
        if block_type == "video" and isinstance(block.get("interaction"), dict) and not isinstance(block.get("completion"), dict):
            issues.append(_issue(f"{path}.completion", "missing-video-completion", "Choose whether completion requires the video end alone or the video end plus required cues."))
        if block_type == "interactiveHtml":
            if "capabilities" not in block:
                issues.append(
                    _issue(
                        f"{path}.capabilities",
                        "html-audio-capability-undecided",
                        "Confirm whether this HTML uses audio; declare capabilities.audio explicitly when it does.",
                        category="teacher-decision",
                    )
                )
            if block.get("completion") is None:
                issues.append(_issue(f"{path}.completion", "missing-html-completion", "Declare interaction-complete when this HTML produces completion evidence."))
        if block_type == "fillBlank":
            assessment = block.get("assessment") if isinstance(block.get("assessment"), dict) else {}
            completion = block.get("completion") if isinstance(block.get("completion"), dict) else {}
            if assessment.get("mode") == "graded":
                if completion.get("rule") == "submit-correct":
                    issues.append(
                        _issue(
                            f"{path}.completion.rule",
                            "fillblank-unbounded-correctness-gate",
                            "A graded fillBlank must not block forever waiting for an exact answer. Use submit-correct-or-exhausted with at most three attempts and a teaching exit.",
                        )
                    )
                attempts = completion.get("maxAttempts")
                if completion.get("rule") == "submit-correct-or-exhausted" and (
                    not isinstance(attempts, int) or isinstance(attempts, bool) or not 1 <= attempts <= 3
                ):
                    issues.append(
                        _issue(
                            f"{path}.completion.maxAttempts",
                            "fillblank-attempt-limit-required",
                            "A graded fillBlank may allow no more than three attempts before explanation or continuation.",
                        )
                    )
                feedback = assessment.get("incorrectFeedback")
                if not isinstance(feedback, str) or not feedback.strip():
                    issues.append(
                        _issue(
                            f"{path}.assessment.incorrectFeedback",
                            "fillblank-missing-incorrect-feedback",
                            "A graded fillBlank needs actionable incorrect feedback before the learner retries or continues.",
                        )
                    )
            elif assessment.get("mode") == "reflection" and completion.get("rule") != "submit-any":
                issues.append(
                    _issue(
                        f"{path}.completion.rule",
                        "reflection-must-submit-any",
                        "Open reflection must accept the learner's submission instead of grading it as an exact answer.",
                    )
                )
    return issues


def _workflow_issues(slice_data: dict, base: str) -> List[dict]:
    workflow = slice_data.get("workflow")
    if not isinstance(workflow, dict):
        return [_issue(f"{base}.workflow", "missing-workflow", "Generate the Slice's explicit deterministic workflow.")]
    issues: List[dict] = []
    if workflow.get("version") != "1.0":
        issues.append(_issue(f"{base}.workflow.version", "missing-workflow-version", "Workflow version must be 1.0."))
    if not isinstance(workflow.get("initialStepId"), str):
        issues.append(_issue(f"{base}.workflow.initialStepId", "missing-initial-step", "Choose an existing initial Workflow Step."))
    if not _valid_non_empty_list(workflow.get("steps")):
        issues.append(_issue(f"{base}.workflow.steps", "missing-workflow-steps", "Generate at least one reachable Workflow Step and a valid terminal path."))
    if "initialState" not in workflow:
        issues.append(_issue(f"{base}.workflow.initialState", "missing-initial-state", "Make initial visibility and interactivity explicit for authoring review."))
    return issues


def _slice_issues(slice_data: dict, base: str) -> List[dict]:
    issues: List[dict] = []
    if not _valid_non_empty_list(slice_data.get("objectiveIds")):
        issues.append(_issue(f"{base}.objectiveIds", "missing-objective-ids", "Align the Slice to at least one course objective."))
    estimated = slice_data.get("estimatedSeconds")
    if not isinstance(estimated, (int, float)) or isinstance(estimated, bool) or estimated <= 0:
        issues.append(_issue(f"{base}.estimatedSeconds", "missing-estimated-seconds", "Estimate the complete Slice duration in positive seconds."))
    issues.extend(_block_issues(slice_data.get("blocks"), base))
    issues.extend(_layout_issues(slice_data, base))
    narrations = slice_data.get("narrations")
    if not _valid_non_empty_list(narrations):
        issues.append(_issue(f"{base}.narrations", "missing-narrations", "Draft the prepared narration segments and their audio asset paths."))
    issues.extend(_workflow_issues(slice_data, base))
    if not isinstance(slice_data.get("navigation"), dict):
        issues.append(_issue(f"{base}.navigation", "missing-navigation", "Declare previous, manualNext, autoNext, and revisit behavior."))
    return issues


def _slice_provenance(draft: dict, slice_id: str) -> dict:
    source_ids = set()
    decision_ids = set()
    statuses = set()
    prefixes = (f"slice:{slice_id}",)
    for record in draft.get("provenance", []):
        if not isinstance(record, dict):
            continue
        target = record.get("targetId")
        if not isinstance(target, str) or not target.startswith(prefixes):
            continue
        source_ids.update(value for value in record.get("sourceIds", []) if isinstance(value, str))
        decision_ids.update(value for value in record.get("decisionIds", []) if isinstance(value, str))
        if isinstance(record.get("status"), str):
            statuses.add(record["status"])
    status = "unresolved"
    if "teacher-confirmed" in statuses:
        status = "teacher-confirmed"
    elif "source-backed" in statuses:
        status = "source-backed"
    elif "ai-proposed" in statuses:
        status = "ai-proposed"
    return {
        "sourceIds": sorted(source_ids),
        "decisionIds": sorted(decision_ids),
        "status": status,
    }


def audit_course_draft(draft: object, *, source_path: Optional[str] = None) -> dict:
    immutable = copy.deepcopy(draft)
    course = _course_from_draft(immutable)
    course_issues: List[dict] = []
    slices: List[dict] = []
    course_id: Optional[str] = None

    if course is None:
        course_issues.append(_issue("$.course", "missing-course", "Draft must contain a course object."))
    else:
        if isinstance(course.get("id"), str):
            course_id = course["id"]
        for field in ("id", "title", "language", "estimatedMinutes", "objectives", "opening", "parts", "closing"):
            if field not in course:
                course_issues.append(_issue(f"$.course.{field}", f"missing-course-{field}", f"Complete course.{field} before contract validation."))
        parts = course.get("parts")
        if not _valid_non_empty_list(parts):
            course_issues.append(_issue("$.course.parts", "missing-parts", "Add at least one Part containing at least one Slice."))
        else:
            ordinal = 0
            for part_index, part in enumerate(parts):
                if not isinstance(part, dict):
                    course_issues.append(_issue(f"$.course.parts[{part_index}]", "invalid-part", "Part must be an object."))
                    continue
                part_slices = part.get("slices")
                if not _valid_non_empty_list(part_slices):
                    course_issues.append(_issue(f"$.course.parts[{part_index}].slices", "missing-slices", "Part must contain at least one Slice."))
                    continue
                for slice_index, slice_value in enumerate(part_slices):
                    ordinal += 1
                    base = f"$.course.parts[{part_index}].slices[{slice_index}]"
                    if not isinstance(slice_value, dict):
                        slice_value = {}
                    slice_id = slice_value.get("id")
                    if not isinstance(slice_id, str) or not slice_id.strip():
                        slice_id = f"unresolved-slice-{ordinal:03d}"
                    issues = _slice_issues(slice_value, base)
                    if slice_id.startswith("unresolved-slice-"):
                        issues.insert(0, _issue(f"{base}.id", "missing-slice-id", "Choose a stable lower-case hyphenated Slice ID.", category="teacher-decision"))
                    slices.append(
                        {
                            "sliceId": slice_id,
                            "partId": part.get("id"),
                            "pointer": base,
                            "status": _slice_status(issues),
                            "issues": issues,
                            "productionDecisions": [],
                            "provenance": _slice_provenance(immutable if isinstance(immutable, dict) else {}, slice_id),
                        }
                    )
        course_issues.extend(_answer_position_issues(course))

    status_counts: Dict[str, int] = {}
    for record in slices:
        status_counts[record["status"]] = status_counts.get(record["status"], 0) + 1
    return {
        "schemaVersion": COMPLETION_PLAN_VERSION,
        "catalogVersion": CATALOG_VERSION,
        "targetContractVersion": TARGET_CONTRACT_VERSION,
        "source": {
            "path": source_path,
            "draftHash": _canonical_hash(immutable),
        },
        "courseId": course_id,
        "courseIssues": course_issues,
        "summary": {
            "sliceCount": len(slices),
            "statusCounts": status_counts,
            "ready": not course_issues and all(record["status"] == "ready-for-contract-validation" for record in slices),
        },
        "slices": slices,
    }


def write_completion_plan(root: Path, plan: dict) -> Path:
    output = root.resolve() / ".course-work" / "course-completion-plan.json"
    write_json_atomic(output, plan)
    return output
