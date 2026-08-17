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
    if preset in {"split-horizontal", "split-vertical"} and layout.get("ratio") not in {"1:1", "2:1", "1:2"}:
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

    blocks = slice_data.get("blocks")
    block_ids = [block.get("id") for block in blocks if isinstance(block, dict)] if isinstance(blocks, list) else []
    assigned: List[object] = []
    for slot in slots:
        if isinstance(slot, dict) and isinstance(slot.get("blockIds"), list):
            assigned.extend(slot["blockIds"])
    if sorted(assigned) != sorted(block_ids) or len(assigned) != len(set(assigned)):
        issues.append(_issue(f"{base}.layout.slots", "invalid-layout-assignment", "Every Slice block must appear in exactly one layout slot."))
    return issues


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
        if block_type not in {"text", "images", "pdf", "video", "interactiveHtml", "fillBlank", "singleChoice"}:
            issues.append(_issue(f"{path}.type", "missing-block-type", "Choose one of the seven runtime Block types."))
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
