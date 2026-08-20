"""Renderer-backed visual evidence required before teacher preview.

The browser driver is intentionally outside this module.  A driver records a
closed, deterministic evidence document; this module verifies that the
document covers every authored runtime state, that its screenshots are real
files below the course's visual-check directory, and that the observations do
not contain a visual blocker.  The committed report is bound to the exact
approved plan, compiled course, asset bytes, semantic audit, renderer snapshot,
and preview bundle that were inspected.
"""

from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Dict, List, Mapping, Sequence, Set, Tuple

from .hashing import canonical_json_hash
from .instructional_audit import (
    InstructionalAuditError,
    _safe_json as _audit_safe_json,
    _safe_root as _audit_safe_root,
    verify_instructional_audit,
)
from .instructional_plan import PlanApprovalError, _plan_guard
from .jsonio import dump_json, load_json
from .preview_evidence import PREVIEW_BUNDLE, RUNTIME_SNAPSHOT, _renderer_record
from .workflow import hash_path


VISUAL_REPORT_VERSION = "1.0"
MAX_AUTONOMOUS_REPAIR_ROUNDS = 3
VISUAL_REPORT_RELATIVE_PATH = ".course-work/prepreview-visual-report.json"
SCREENSHOT_ROOT_RELATIVE_PATH = ".course-work/visual-check/screenshots"
VIEWPORT_PROFILES = ("desktop", "desktop-sidebar")

MAX_CANDIDATE_BYTES = 8 * 1024 * 1024
MAX_SCREENSHOT_BYTES = 40 * 1024 * 1024
MAX_DEAD_REGION_RATIO = 0.35
MIN_DESKTOP_WIDTH = 1200
MIN_DESKTOP_HEIGHT = 700
MIN_CONTENT_WIDTH = 640
MIN_CONTENT_HEIGHT = 500

VISUAL_BLOCKER_CODES = frozenset(
    {
        "missing-content",
        "zero-size-content",
        "offscreen-content",
        "occluded-content",
        "unclickable-content",
        "unreachable-content",
        "empty-split-side",
        "large-dead-region",
        "unreadable-content",
        "aspect-distortion",
        "incorrect-reading-order",
        "broken-co-visibility",
        "unexpected-core-scroll",
        "plan-screenshot-contradiction",
        "runtime-error",
    }
)

_HASH_FIELDS = (
    "planContentHash",
    "materialsExtractedHash",
    "sourceCoverageHash",
    "blueprintHash",
    "courseDefinitionHash",
    "sourceMapHash",
    "assetSetHash",
    "decisionStoreHash",
    "instructionalAuditHash",
    "rendererHash",
    "previewBundleHash",
)
_PAYLOAD_FIELDS = frozenset(
    {
        "schemaVersion",
        "artifactHashes",
        "captureAvailable",
        "repairRound",
        "capturedAt",
        "states",
        "blockerCount",
    }
)
_COMMIT_FIELDS = frozenset(set(_PAYLOAD_FIELDS) | {"reportHash"})
_STATE_FIELDS = frozenset(
    {
        "stateId",
        "partId",
        "sliceId",
        "viewportProfile",
        "viewport",
        "screenshotPath",
        "screenshotSha256",
        "visibleBlockIds",
        "enabledBlockIds",
        "domRects",
        "overflow",
        "occlusion",
        "scroll",
        "focus",
        "layout",
        "runtimeErrors",
        "planBindingIds",
        "findings",
    }
)
_RECT_REQUIRED_FIELDS = frozenset(
    {"blockId", "x", "y", "width", "height", "intersectionRatio", "visible", "clickable", "occluded"}
)
_RECT_OPTIONAL_FIELDS = frozenset({"fontSizePx", "intrinsicAspectRatio", "renderedAspectRatio"})
_FINDING_FIELDS = frozenset({"code", "severity", "message", "blockIds"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SCREENSHOT_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})
_SECRET_TEXT = re.compile(r"OSS_ADMIN_KEY|oss-admin-[0-9a-z]+|authorization\s*:\s*bearer", re.I)


class VisualReportError(ValueError):
    """Visual evidence is missing, stale, unsafe, or blocking."""

    def __init__(self, code: str, message: str, *, path: str = VISUAL_REPORT_RELATIVE_PATH) -> None:
        self.code = code
        self.path = path
        super().__init__(message)


def _safe_root(root: Path) -> Path:
    try:
        return _audit_safe_root(root)
    except InstructionalAuditError as exc:
        raise VisualReportError(exc.code, str(exc), path=exc.path) from exc


def _safe_json(root: Path, relative: str, *, required: bool = True) -> object | None:
    try:
        return _audit_safe_json(root, relative, required=required)
    except InstructionalAuditError as exc:
        raise VisualReportError(exc.code, str(exc), path=exc.path) from exc


def _nonempty(value: object, *, maximum: int = 1600) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _course_parts(course: Mapping[str, object]) -> List[Tuple[str, List[dict]]]:
    definition = course.get("course")
    if not isinstance(definition, dict) or not isinstance(definition.get("parts"), list):
        raise VisualReportError("invalid-course", "course definition has no readable Part/Slice structure", path="course/course.json")
    result: List[Tuple[str, List[dict]]] = []
    part_ids: Set[str] = set()
    slice_ids: Set[str] = set()
    for part in definition["parts"]:
        if not isinstance(part, dict) or not _nonempty(part.get("id")) or not isinstance(part.get("slices"), list):
            raise VisualReportError("invalid-course", "course definition has an invalid Part", path="course/course.json")
        part_id = part["id"]
        if part_id in part_ids:
            raise VisualReportError("invalid-course", "course definition has duplicate Part IDs", path="course/course.json")
        part_ids.add(part_id)
        slices: List[dict] = []
        for slice_data in part["slices"]:
            if not isinstance(slice_data, dict) or not _nonempty(slice_data.get("id")) or not isinstance(slice_data.get("blocks"), list):
                raise VisualReportError("invalid-course", "course definition has an invalid Slice", path="course/course.json")
            if slice_data["id"] in slice_ids:
                raise VisualReportError("invalid-course", "course definition has duplicate Slice IDs", path="course/course.json")
            slice_ids.add(slice_data["id"])
            slices.append(slice_data)
        if not slices:
            raise VisualReportError("invalid-course", "every Part must contain a Slice", path="course/course.json")
        result.append((part_id, slices))
    if not result:
        raise VisualReportError("invalid-course", "course definition must contain a Part", path="course/course.json")
    return result


def _assessment_branches(block: Mapping[str, object]) -> List[str]:
    assessment = block.get("assessment")
    completion = block.get("completion")
    if isinstance(assessment, dict) and assessment.get("mode") == "graded":
        result = ["correct", "incorrect"]
        if isinstance(completion, dict) and completion.get("rule") == "submit-correct-or-exhausted":
            result.append("attempts-exhausted")
        return result
    return ["submitted"]


def _expected_state_specs(course: Mapping[str, object]) -> List[dict]:
    """Return ordered logical state specs, retaining their subject Block."""
    specs: List[dict] = []
    for part_id, slices in _course_parts(course):
        for slice_data in slices:
            slice_id = slice_data["id"]
            prefix = f"{part_id}/{slice_id}"
            for kind in ("initial", "narration-complete", "action-ready"):
                specs.append({"stateId": f"{prefix}/{kind}", "partId": part_id, "sliceId": slice_id, "kind": kind, "blockId": None})
            for block in slice_data["blocks"]:
                if not isinstance(block, dict) or not _nonempty(block.get("id")) or not _nonempty(block.get("type")):
                    raise VisualReportError("invalid-course", "Slice contains an invalid Block", path="course/course.json")
                block_id = block["id"]
                if block["type"] in {"singleChoice", "fillBlank"}:
                    for branch in _assessment_branches(block):
                        specs.append(
                            {
                                "stateId": f"{prefix}/answer:{block_id}:{branch}",
                                "partId": part_id,
                                "sliceId": slice_id,
                                "kind": f"answer-{branch}",
                                "blockId": block_id,
                            }
                        )
                elif block["type"] == "video" and isinstance(block.get("interaction"), dict):
                    specs.append(
                        {
                            "stateId": f"{prefix}/video-modal:{block_id}",
                            "partId": part_id,
                            "sliceId": slice_id,
                            "kind": "video-modal",
                            "blockId": block_id,
                        }
                    )
                elif block["type"] == "interactiveHtml":
                    for html_state in ("ready", "active", "completed", "error"):
                        specs.append(
                            {
                                "stateId": f"{prefix}/html:{block_id}:{html_state}",
                                "partId": part_id,
                                "sliceId": slice_id,
                                "kind": f"html-{html_state}",
                                "blockId": block_id,
                            }
                        )
            specs.append(
                {
                    "stateId": f"{prefix}/final-pre-completion",
                    "partId": part_id,
                    "sliceId": slice_id,
                    "kind": "final-pre-completion",
                    "blockId": None,
                }
            )
    return specs


def expected_visual_states(course: dict) -> Sequence[str]:
    """Return every logical visual state required by the current course."""
    return tuple(spec["stateId"] for spec in _expected_state_specs(course))


def _slice_map(course: Mapping[str, object]) -> Dict[Tuple[str, str], dict]:
    return {
        (part_id, slice_data["id"]): slice_data
        for part_id, slices in _course_parts(course)
        for slice_data in slices
    }


def _plan_bindings(plan: Mapping[str, object]) -> Dict[Tuple[str, str], List[str]]:
    result: Dict[Tuple[str, str], List[str]] = {}
    parts = plan.get("parts") if isinstance(plan.get("parts"), list) else []
    for part in parts:
        if not isinstance(part, dict) or not isinstance(part.get("partId"), str):
            continue
        for slice_data in part.get("slices", []) if isinstance(part.get("slices"), list) else []:
            if not isinstance(slice_data, dict) or not isinstance(slice_data.get("sliceId"), str):
                continue
            values: Set[str] = set()
            for source_use in slice_data.get("sourceUses", []) if isinstance(slice_data.get("sourceUses"), list) else []:
                if isinstance(source_use, dict) and isinstance(source_use.get("sourceId"), str):
                    values.add(f"source:{source_use['sourceId']}")
            action = slice_data.get("learnerAction")
            if isinstance(action, dict) and isinstance(action.get("targetId"), str):
                values.add(f"action-target:{action['targetId']}")
            for item in slice_data.get("coVisibleRequirements", []) if isinstance(slice_data.get("coVisibleRequirements"), list) else []:
                if isinstance(item, dict) and isinstance(item.get("sourceId"), str) and isinstance(item.get("targetId"), str):
                    values.add(f"co-visible:{item['sourceId']}->{item['targetId']}")
            for item in slice_data.get("imageRelationships", []) if isinstance(slice_data.get("imageRelationships"), list) else []:
                if isinstance(item, dict) and isinstance(item.get("sourceId"), str) and isinstance(item.get("targetId"), str):
                    values.add(f"image:{item['sourceId']}->{item['targetId']}")
            result[(part["partId"], slice_data["sliceId"])] = sorted(values)
    return result


def _renderer_hash() -> str:
    snapshot = load_json(RUNTIME_SNAPSHOT)
    return canonical_json_hash(_renderer_record(snapshot))


def _current_context_at(root: Path) -> Tuple[Dict[str, str], dict, dict]:
    try:
        audit_evidence = verify_instructional_audit(root)
    except Exception as exc:
        code = getattr(exc, "code", "instructional-audit-not-current")
        path = getattr(exc, "path", ".course-work/instructional-audit.json")
        raise VisualReportError(code, "instructional audit is missing, blocking, or stale", path=path) from exc
    plan = _safe_json(root, ".course-work/course-storyboard.json")
    course = _safe_json(root, "course/course.json")
    if not isinstance(plan, dict) or not isinstance(course, dict):
        raise VisualReportError("invalid-evidence", "visual evidence inputs must be JSON objects")
    hashes = {field: audit_evidence[field] for field in _HASH_FIELDS if field in audit_evidence}
    hashes.update(
        {
            "rendererHash": _renderer_hash(),
            "previewBundleHash": hash_path(PREVIEW_BUNDLE),
        }
    )
    if set(hashes) != set(_HASH_FIELDS):
        raise VisualReportError("hashes-required", "current course evidence does not provide every visual binding hash", path="artifactHashes")
    return hashes, plan, course


def _safe_screenshot_bytes(root: Path, relative: str) -> bytes:
    if not isinstance(relative, str):
        raise VisualReportError("screenshot-outside-root", "screenshot must be an image below .course-work/visual-check/screenshots", path=str(relative))
    path = Path(relative)
    parts = relative.split("/")
    expected = (".course-work", "visual-check", "screenshots")
    if (
        not relative
        or path.is_absolute()
        or "\\" in relative
        or any(part in {"", ".", ".."} for part in parts)
        or tuple(parts[:3]) != expected
        or len(parts) == 3
        or path.suffix.lower() not in _SCREENSHOT_SUFFIXES
    ):
        raise VisualReportError("screenshot-outside-root", "screenshot must be an image below .course-work/visual-check/screenshots", path=str(relative))
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    directory_flags = flags | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(root, directory_flags)
    except OSError as exc:
        raise VisualReportError("unsafe-evidence-root", "course root cannot be opened safely", path=relative) from exc
    try:
        for index, component in enumerate(parts):
            child_flags = flags if index == len(parts) - 1 else directory_flags
            try:
                child = os.open(component, child_flags, dir_fd=descriptor)
            except FileNotFoundError as exc:
                raise VisualReportError("missing-screenshot", "visual state screenshot is missing", path=relative) from exc
            except OSError as exc:
                raise VisualReportError("symlink-screenshot", "screenshot path may not traverse a symlink", path=relative) from exc
            os.close(descriptor)
            descriptor = child
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0:
            raise VisualReportError("missing-screenshot", "visual state screenshot must be a nonempty regular file", path=relative)
        if metadata.st_size > MAX_SCREENSHOT_BYTES:
            raise VisualReportError("screenshot-too-large", "visual state screenshot exceeds the allowed size", path=relative)
        chunks: List[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        content = b"".join(chunks)
        suffix = path.suffix.lower()
        valid_magic = (
            (suffix == ".png" and content.startswith(b"\x89PNG\r\n\x1a\n"))
            or (suffix in {".jpg", ".jpeg"} and content.startswith(b"\xff\xd8\xff"))
            or (suffix == ".webp" and len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP")
        )
        if not valid_magic:
            raise VisualReportError("invalid-screenshot", "visual state screenshot is not a valid declared image format", path=relative)
        return content
    finally:
        os.close(descriptor)


def _stable_ids(value: object, *, field: str, known: Set[str] | None = None) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise VisualReportError("stable-ids-required", f"{field} must be an array of stable IDs", path=field)
    if len(value) != len(set(value)):
        raise VisualReportError("duplicate-id", f"{field} must not contain duplicate IDs", path=field)
    if known is not None:
        unknown = next((item for item in value if item not in known), None)
        if unknown is not None:
            raise VisualReportError("unknown-block", f"{field} contains an unknown Block ID", path=field)
    return sorted(value)


def _validate_viewport(value: object, profile: str, *, path: str) -> dict:
    fields = {"width", "height", "contentWidth", "contentHeight"}
    if not isinstance(value, dict) or set(value) != fields:
        raise VisualReportError("invalid-viewport", "viewport must contain width, height, contentWidth, and contentHeight", path=path)
    if any(isinstance(value[field], bool) or not isinstance(value[field], int) for field in fields):
        raise VisualReportError("invalid-viewport", "viewport dimensions must be integers", path=path)
    if value["width"] < MIN_DESKTOP_WIDTH or value["height"] < MIN_DESKTOP_HEIGHT:
        raise VisualReportError("invalid-viewport", "visual inspection requires the supported desktop viewport", path=path)
    if value["contentWidth"] < MIN_CONTENT_WIDTH or value["contentHeight"] < MIN_CONTENT_HEIGHT:
        raise VisualReportError("invalid-viewport", "student content area is too small for the supported desktop shell", path=path)
    if value["contentWidth"] > value["width"] or value["contentHeight"] > value["height"]:
        raise VisualReportError("invalid-viewport", "content dimensions must fit inside the viewport", path=path)
    if profile not in VIEWPORT_PROFILES:
        raise VisualReportError("invalid-viewport-profile", "viewportProfile is unsupported", path=path)
    return {field: value[field] for field in ("width", "height", "contentWidth", "contentHeight")}


def _validate_rects(value: object, *, block_types: Mapping[str, str], path: str) -> List[dict]:
    if not isinstance(value, list):
        raise VisualReportError("dom-rects-required", "domRects must contain every Slice Block", path=path)
    result: List[dict] = []
    seen: Set[str] = set()
    for index, raw in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(raw, dict) or not _RECT_REQUIRED_FIELDS.issubset(raw) or set(raw).difference(_RECT_REQUIRED_FIELDS | _RECT_OPTIONAL_FIELDS):
            raise VisualReportError("invalid-dom-rect", "DOM rectangle has unknown or missing fields", path=item_path)
        block_id = raw.get("blockId")
        if block_id not in block_types or block_id in seen:
            raise VisualReportError("invalid-dom-rect", "DOM rectangle must identify one current Block exactly once", path=item_path)
        seen.add(block_id)
        for field in ("x", "y", "width", "height", "intersectionRatio"):
            if not _number(raw.get(field)):
                raise VisualReportError("invalid-dom-rect", "DOM rectangle geometry must contain finite numbers", path=item_path)
        if not 0 <= float(raw["intersectionRatio"]) <= 1:
            raise VisualReportError("invalid-dom-rect", "intersectionRatio must be between zero and one", path=item_path)
        for field in ("visible", "clickable", "occluded"):
            if not isinstance(raw.get(field), bool):
                raise VisualReportError("invalid-dom-rect", "DOM rectangle flags must be booleans", path=item_path)
        normalized = {field: raw[field] for field in _RECT_REQUIRED_FIELDS}
        for field in _RECT_OPTIONAL_FIELDS:
            if field in raw:
                if not _number(raw[field]) or float(raw[field]) <= 0:
                    raise VisualReportError("invalid-dom-rect", f"{field} must be a positive finite number", path=item_path)
                normalized[field] = raw[field]
        result.append(normalized)
    if seen != set(block_types):
        raise VisualReportError("dom-rect-coverage", "domRects must contain every current Slice Block exactly once", path=path)
    return sorted(result, key=lambda item: item["blockId"])


def _validate_observations(state: Mapping[str, object], *, has_co_visibility: bool, path: str) -> dict:
    overflow = state.get("overflow")
    if not isinstance(overflow, dict) or set(overflow) != {"horizontal", "vertical", "clippedBlockIds"} or not isinstance(overflow.get("horizontal"), bool) or not isinstance(overflow.get("vertical"), bool):
        raise VisualReportError("invalid-observation", "overflow observation is invalid", path=f"{path}.overflow")
    clipped = _stable_ids(overflow.get("clippedBlockIds"), field=f"{path}.overflow.clippedBlockIds")

    occlusion = state.get("occlusion")
    if not isinstance(occlusion, dict) or set(occlusion) != {"occludedBlockIds"}:
        raise VisualReportError("invalid-observation", "occlusion observation is invalid", path=f"{path}.occlusion")
    occluded = _stable_ids(occlusion.get("occludedBlockIds"), field=f"{path}.occlusion.occludedBlockIds")

    scroll = state.get("scroll")
    if not isinstance(scroll, dict) or set(scroll) != {"x", "y", "maxX", "maxY", "coreTaskRequiresUnexpectedScroll"}:
        raise VisualReportError("invalid-observation", "scroll observation is invalid", path=f"{path}.scroll")
    if any(not _number(scroll.get(field)) or float(scroll[field]) < 0 for field in ("x", "y", "maxX", "maxY")) or not isinstance(scroll.get("coreTaskRequiresUnexpectedScroll"), bool):
        raise VisualReportError("invalid-observation", "scroll values are invalid", path=f"{path}.scroll")
    if float(scroll["x"]) > float(scroll["maxX"]) or float(scroll["y"]) > float(scroll["maxY"]):
        raise VisualReportError("invalid-observation", "scroll position exceeds its declared maximum", path=f"{path}.scroll")

    focus = state.get("focus")
    if not isinstance(focus, dict) or set(focus) != {"expectedTargetId", "actualTargetId", "visible"}:
        raise VisualReportError("invalid-observation", "focus observation is invalid", path=f"{path}.focus")
    if any(value is not None and not _nonempty(value) for value in (focus.get("expectedTargetId"), focus.get("actualTargetId"))) or not isinstance(focus.get("visible"), bool):
        raise VisualReportError("invalid-observation", "focus targets or visibility are invalid", path=f"{path}.focus")

    layout = state.get("layout")
    layout_fields = {
        "emptySlotIds",
        "deadRegionRatio",
        "unreadableBlockIds",
        "aspectDistortedBlockIds",
        "readingOrderMatchesPlan",
        "coVisibilitySatisfied",
        "planMatchesScreenshot",
        "unreachableBlockIds",
    }
    if not isinstance(layout, dict) or set(layout) != layout_fields:
        raise VisualReportError("invalid-observation", "layout observation is invalid", path=f"{path}.layout")
    if not _number(layout.get("deadRegionRatio")) or not 0 <= float(layout["deadRegionRatio"]) <= 1:
        raise VisualReportError("invalid-observation", "deadRegionRatio must be between zero and one", path=f"{path}.layout")
    for field in ("readingOrderMatchesPlan", "coVisibilitySatisfied", "planMatchesScreenshot"):
        if not isinstance(layout.get(field), bool):
            raise VisualReportError("invalid-observation", f"{field} must be boolean", path=f"{path}.layout")
    normalized_layout = {
        field: _stable_ids(layout.get(field), field=f"{path}.layout.{field}")
        for field in ("emptySlotIds", "unreadableBlockIds", "aspectDistortedBlockIds", "unreachableBlockIds")
    }
    normalized_layout.update(
        {
            "deadRegionRatio": layout["deadRegionRatio"],
            "readingOrderMatchesPlan": layout["readingOrderMatchesPlan"],
            "coVisibilitySatisfied": layout["coVisibilitySatisfied"],
            "planMatchesScreenshot": layout["planMatchesScreenshot"],
        }
    )
    if has_co_visibility and layout["coVisibilitySatisfied"] is not True:
        raise VisualReportError("broken-co-visibility", "approved co-visible evidence and action are not co-visible", path=f"{path}.layout")
    return {
        "overflow": {"horizontal": overflow["horizontal"], "vertical": overflow["vertical"], "clippedBlockIds": clipped},
        "occlusion": {"occludedBlockIds": occluded},
        "scroll": {field: scroll[field] for field in ("x", "y", "maxX", "maxY", "coreTaskRequiresUnexpectedScroll")},
        "focus": {field: focus[field] for field in ("expectedTargetId", "actualTargetId", "visible")},
        "layout": normalized_layout,
    }


def _validate_findings(value: object, *, known_blocks: Set[str], path: str) -> List[dict]:
    if not isinstance(value, list):
        raise VisualReportError("findings-required", "findings must be an array", path=path)
    result: List[dict] = []
    for index, raw in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(raw, dict) or set(raw) != _FINDING_FIELDS:
            raise VisualReportError("invalid-finding", "visual finding has unknown or missing fields", path=item_path)
        severity = raw.get("severity")
        if severity not in {"blocker", "warning", "review"} or not _nonempty(raw.get("code"), maximum=120) or not _nonempty(raw.get("message")):
            raise VisualReportError("invalid-finding", "visual finding requires code, severity, and message", path=item_path)
        if _SECRET_TEXT.search(raw["message"]):
            raise VisualReportError("credential-leak", "visual reports may not contain credentials", path=item_path)
        blocks = _stable_ids(raw.get("blockIds"), field=f"{item_path}.blockIds", known=known_blocks)
        if severity == "blocker" and raw["code"] not in VISUAL_BLOCKER_CODES:
            raise VisualReportError("unknown-blocker-code", "visual blocker must use a standardized blocker code", path=item_path)
        if raw["code"] in VISUAL_BLOCKER_CODES and severity != "blocker":
            raise VisualReportError("blocker-downgrade-forbidden", "a standardized visual blocker cannot be recorded at a lower severity", path=item_path)
        result.append({"code": raw["code"].strip(), "severity": severity, "message": raw["message"].strip(), "blockIds": blocks})
    return result


def _required_blocks(spec: Mapping[str, object], slice_data: Mapping[str, object]) -> Set[str]:
    subject = spec.get("blockId")
    if isinstance(subject, str):
        return {subject}
    blocks = [block for block in slice_data.get("blocks", []) if isinstance(block, dict) and isinstance(block.get("id"), str)]
    all_ids = {block["id"] for block in blocks}
    initial = slice_data.get("workflow", {}).get("initialState") if isinstance(slice_data.get("workflow"), dict) else None
    initial_visible = initial.get("visibleBlockIds") if isinstance(initial, dict) else None
    if spec.get("kind") in {"initial", "narration-complete"} and isinstance(initial_visible, list) and initial_visible:
        return {item for item in initial_visible if isinstance(item, str)}
    interactive = {block["id"] for block in blocks if block.get("type") in {"pdf", "video", "interactiveHtml", "singleChoice", "fillBlank"}}
    if spec.get("kind") in {"action-ready", "final-pre-completion"} and interactive:
        return interactive
    return all_ids


def _validate_state(
    raw: object,
    *,
    index: int,
    specs: Mapping[str, dict],
    slices: Mapping[Tuple[str, str], dict],
    plan_bindings: Mapping[Tuple[str, str], List[str]],
    root: Path,
) -> dict:
    path = f"states[{index}]"
    if not isinstance(raw, dict) or set(raw) != _STATE_FIELDS:
        raise VisualReportError("invalid-state", "visual state has unknown or missing fields", path=path)
    state_id = raw.get("stateId")
    spec = specs.get(state_id) if isinstance(state_id, str) else None
    if spec is None:
        raise VisualReportError("unknown-state", "visual evidence names an unexpected runtime state", path=f"{path}.stateId")
    if raw.get("partId") != spec["partId"] or raw.get("sliceId") != spec["sliceId"]:
        raise VisualReportError("state-identity-mismatch", "visual state Part/Slice does not match its stateId", path=path)
    profile = raw.get("viewportProfile")
    viewport = _validate_viewport(raw.get("viewport"), profile, path=f"{path}.viewport")
    slice_data = slices[(spec["partId"], spec["sliceId"])]
    blocks = slice_data.get("blocks")
    block_types = {block["id"]: block["type"] for block in blocks if isinstance(block, dict) and isinstance(block.get("id"), str) and isinstance(block.get("type"), str)}
    known_blocks = set(block_types)
    visible = _stable_ids(raw.get("visibleBlockIds"), field=f"{path}.visibleBlockIds", known=known_blocks)
    enabled = _stable_ids(raw.get("enabledBlockIds"), field=f"{path}.enabledBlockIds", known=known_blocks)
    if not set(enabled).issubset(visible):
        raise VisualReportError("enabled-content-hidden", "enabled Blocks must also be visible", path=f"{path}.enabledBlockIds")
    if spec.get("kind") == "initial":
        workflow = slice_data.get("workflow") if isinstance(slice_data.get("workflow"), dict) else {}
        initial = workflow.get("initialState") if isinstance(workflow.get("initialState"), dict) else {}
        expected_visible = sorted(initial.get("visibleBlockIds", known_blocks))
        expected_enabled = sorted(initial.get("enabledBlockIds", known_blocks))
        if visible != expected_visible or enabled != expected_enabled:
            raise VisualReportError("initial-state-mismatch", "initial visual evidence must match the authored Workflow initial state", path=path)
    rects = _validate_rects(raw.get("domRects"), block_types=block_types, path=f"{path}.domRects")
    rect_by_id = {rect["blockId"]: rect for rect in rects}
    required = _required_blocks(spec, slice_data)
    missing = sorted(required.difference(visible))
    if missing:
        raise VisualReportError("missing-content", f"required Block is not visible: {missing[0]}", path=f"{path}.visibleBlockIds")
    for block_id in visible:
        rect = rect_by_id[block_id]
        if not rect["visible"] or float(rect["width"]) <= 0 or float(rect["height"]) <= 0:
            raise VisualReportError("zero-size-content", f"visible Block has zero rendered size: {block_id}", path=f"{path}.domRects")
        x, y = float(rect["x"]), float(rect["y"])
        width, height = float(rect["width"]), float(rect["height"])
        intersection_width = max(0.0, min(x + width, viewport["contentWidth"]) - max(x, 0.0))
        intersection_height = max(0.0, min(y + height, viewport["contentHeight"]) - max(y, 0.0))
        calculated_intersection = (intersection_width * intersection_height) / (width * height)
        if abs(calculated_intersection - float(rect["intersectionRatio"])) > 0.02:
            raise VisualReportError("invalid-dom-rect", f"intersectionRatio contradicts Block geometry: {block_id}", path=f"{path}.domRects")
        if float(rect["intersectionRatio"]) <= 0:
            raise VisualReportError("offscreen-content", f"visible Block is outside the student content viewport: {block_id}", path=f"{path}.domRects")
        if block_id in required and float(rect["intersectionRatio"]) < 0.99:
            raise VisualReportError("offscreen-content", f"required Block is partly outside the student content viewport: {block_id}", path=f"{path}.domRects")
        if rect["occluded"]:
            raise VisualReportError("occluded-content", f"visible Block is occluded: {block_id}", path=f"{path}.domRects")
        if block_id in enabled and not rect["clickable"]:
            raise VisualReportError("unclickable-content", f"enabled Block cannot be clicked: {block_id}", path=f"{path}.domRects")
        if block_types[block_id] in {"images", "pdf", "video", "interactiveHtml"} and (float(rect["width"]) < 160 or float(rect["height"]) < 120):
            raise VisualReportError("unreadable-content", f"required media is too small to inspect: {block_id}", path=f"{path}.domRects")
        if "fontSizePx" in rect and block_types[block_id] in {"text", "singleChoice", "fillBlank"} and float(rect["fontSizePx"]) < 14:
            raise VisualReportError("unreadable-content", f"learner text is too small: {block_id}", path=f"{path}.domRects")
        if block_types[block_id] in {"video", "interactiveHtml"} and "intrinsicAspectRatio" in rect and "renderedAspectRatio" in rect:
            if abs(float(rect["intrinsicAspectRatio"]) - float(rect["renderedAspectRatio"])) / float(rect["intrinsicAspectRatio"]) > 0.05:
                raise VisualReportError("aspect-distortion", f"media aspect ratio is visibly distorted: {block_id}", path=f"{path}.domRects")

    observations = _validate_observations(raw, has_co_visibility=any(item.startswith("co-visible:") for item in plan_bindings.get((spec["partId"], spec["sliceId"]), [])), path=path)
    if observations["overflow"]["horizontal"] or observations["overflow"]["clippedBlockIds"]:
        raise VisualReportError("offscreen-content", "core visual content overflows or is clipped", path=f"{path}.overflow")
    if observations["occlusion"]["occludedBlockIds"]:
        raise VisualReportError("occluded-content", "visual observation contains occluded Blocks", path=f"{path}.occlusion")
    if observations["scroll"]["coreTaskRequiresUnexpectedScroll"]:
        raise VisualReportError("unexpected-core-scroll", "core task is discoverable only through unexpected scrolling", path=f"{path}.scroll")
    focus = observations["focus"]
    if focus["expectedTargetId"] is not None and (focus["actualTargetId"] != focus["expectedTargetId"] or not focus["visible"]):
        raise VisualReportError("unreachable-content", "expected focus target is not visibly focused", path=f"{path}.focus")
    layout = observations["layout"]
    if layout["emptySlotIds"]:
        raise VisualReportError("empty-split-side", "layout contains an empty visible Slot", path=f"{path}.layout")
    if float(layout["deadRegionRatio"]) > MAX_DEAD_REGION_RATIO:
        raise VisualReportError("large-dead-region", "layout contains a large dead region", path=f"{path}.layout")
    if layout["unreadableBlockIds"]:
        raise VisualReportError("unreadable-content", "layout contains unreadable Blocks", path=f"{path}.layout")
    if layout["aspectDistortedBlockIds"]:
        raise VisualReportError("aspect-distortion", "layout contains aspect-distorted media", path=f"{path}.layout")
    if layout["unreachableBlockIds"]:
        raise VisualReportError("unreachable-content", "layout contains unreachable Blocks", path=f"{path}.layout")
    if not layout["readingOrderMatchesPlan"]:
        raise VisualReportError("incorrect-reading-order", "visual reading order contradicts the approved page plan", path=f"{path}.layout")
    if not layout["planMatchesScreenshot"]:
        raise VisualReportError("plan-screenshot-contradiction", "screenshot contradicts the approved page plan", path=f"{path}.layout")

    runtime_errors = raw.get("runtimeErrors")
    if not isinstance(runtime_errors, list) or any(not _nonempty(item) for item in runtime_errors):
        raise VisualReportError("invalid-runtime-errors", "runtimeErrors must be an array of nonempty messages", path=f"{path}.runtimeErrors")
    if any(_SECRET_TEXT.search(item) for item in runtime_errors):
        raise VisualReportError("credential-leak", "visual reports may not contain credentials", path=f"{path}.runtimeErrors")
    if runtime_errors:
        raise VisualReportError("runtime-error", f"visual state has a runtime error: {runtime_errors[0]}", path=f"{path}.runtimeErrors")

    bindings = _stable_ids(raw.get("planBindingIds"), field=f"{path}.planBindingIds")
    if bindings != plan_bindings.get((spec["partId"], spec["sliceId"]), []):
        raise VisualReportError("plan-binding-mismatch", "visual state does not bind the exact approved Slice plan", path=f"{path}.planBindingIds")
    findings = _validate_findings(raw.get("findings"), known_blocks=known_blocks, path=f"{path}.findings")

    screenshot_path = raw.get("screenshotPath")
    screenshot_sha = raw.get("screenshotSha256")
    if not isinstance(screenshot_sha, str) or not _SHA256.fullmatch(screenshot_sha):
        raise VisualReportError("invalid-screenshot-sha", "screenshotSha256 must be a lowercase SHA-256", path=f"{path}.screenshotSha256")
    screenshot_bytes = _safe_screenshot_bytes(root, screenshot_path)
    if hashlib.sha256(screenshot_bytes).hexdigest() != screenshot_sha:
        raise VisualReportError("screenshot-sha-mismatch", "screenshot bytes do not match screenshotSha256", path=f"{path}.screenshotSha256")
    return {
        "stateId": state_id,
        "partId": spec["partId"],
        "sliceId": spec["sliceId"],
        "viewportProfile": profile,
        "viewport": viewport,
        "screenshotPath": screenshot_path,
        "screenshotSha256": screenshot_sha,
        "visibleBlockIds": visible,
        "enabledBlockIds": enabled,
        "domRects": rects,
        **observations,
        "runtimeErrors": [],
        "planBindingIds": bindings,
        "findings": findings,
    }


def _validate_static_layouts(course: Mapping[str, object]) -> None:
    for part_id, slices in _course_parts(course):
        for slice_data in slices:
            layout = slice_data.get("layout")
            if not isinstance(layout, dict) or not isinstance(layout.get("slots"), list):
                raise VisualReportError("invalid-course", "Slice has no readable layout", path="course/course.json")
            if layout.get("preset") in {"split-horizontal", "split-vertical"}:
                empty = next((slot for slot in layout["slots"] if isinstance(slot, dict) and slot.get("blockIds") == []), None)
                if empty is not None:
                    raise VisualReportError("empty-split-side", f"{part_id}/{slice_data['id']} has an empty split Slot", path="course/course.json")


def _validate_payload(payload: object, *, hashes: Mapping[str, str], plan: Mapping[str, object], course: Mapping[str, object], root: Path) -> dict:
    if not isinstance(payload, dict):
        raise VisualReportError("invalid-payload", "visual report candidate must be an object")
    if set(payload) != _PAYLOAD_FIELDS or payload.get("schemaVersion") != VISUAL_REPORT_VERSION:
        raise VisualReportError("invalid-version", "visual report candidate must use the closed 1.0 schema")
    reported_hashes = payload.get("artifactHashes")
    if not isinstance(reported_hashes, dict) or set(reported_hashes) != set(_HASH_FIELDS) or any(not isinstance(reported_hashes.get(field), str) for field in _HASH_FIELDS):
        raise VisualReportError("hashes-required", "visual report must bind every current artifact hash", path="artifactHashes")
    if dict(reported_hashes) != dict(hashes):
        raise VisualReportError("visual-report-stale", "visual report hashes do not match the current course", path="artifactHashes")
    if payload.get("captureAvailable") is not True:
        raise VisualReportError("capture-unavailable", "browser control and screenshot capture are required before teacher preview", path="captureAvailable")
    repair_round = payload.get("repairRound")
    if isinstance(repair_round, bool) or not isinstance(repair_round, int) or repair_round < 0:
        raise VisualReportError("invalid-repair-round", "repairRound must be a nonnegative integer", path="repairRound")
    if repair_round > MAX_AUTONOMOUS_REPAIR_ROUNDS:
        raise VisualReportError("repair-limit-exceeded", "a fourth autonomous visual repair attempt is forbidden", path="repairRound")
    if not _nonempty(payload.get("capturedAt"), maximum=100):
        raise VisualReportError("captured-at-required", "capturedAt must be a nonempty timestamp", path="capturedAt")
    if _SECRET_TEXT.search(payload["capturedAt"]):
        raise VisualReportError("credential-leak", "visual reports may not contain credentials", path="capturedAt")
    _validate_static_layouts(course)
    specs_list = _expected_state_specs(course)
    specs = {spec["stateId"]: spec for spec in specs_list}
    slices = _slice_map(course)
    bindings = _plan_bindings(plan)
    states = payload.get("states")
    if not isinstance(states, list):
        raise VisualReportError("states-required", "visual report states must be an array", path="states")
    normalized = [
        _validate_state(item, index=index, specs=specs, slices=slices, plan_bindings=bindings, root=root)
        for index, item in enumerate(states)
    ]
    actual_keys = [(state["stateId"], state["viewportProfile"]) for state in normalized]
    if len(actual_keys) != len(set(actual_keys)):
        raise VisualReportError("duplicate-state-coverage", "each logical state and viewport profile must occur exactly once", path="states")
    expected_keys = [(spec["stateId"], profile) for spec in specs_list for profile in VIEWPORT_PROFILES]
    if set(actual_keys) != set(expected_keys):
        missing = next((key for key in expected_keys if key not in set(actual_keys)), None)
        suffix = f": {missing[0]} @ {missing[1]}" if missing else ""
        raise VisualReportError("state-coverage", f"every required state needs both desktop viewport profiles{suffix}", path="states")
    screenshot_paths = [state["screenshotPath"] for state in normalized]
    if len(screenshot_paths) != len(set(screenshot_paths)):
        raise VisualReportError("duplicate-screenshot", "each visual state/profile capture needs its own screenshot file", path="states")
    state_rank = {spec["stateId"]: index for index, spec in enumerate(specs_list)}
    profile_rank = {profile: index for index, profile in enumerate(VIEWPORT_PROFILES)}
    normalized.sort(key=lambda state: (state_rank[state["stateId"]], profile_rank[state["viewportProfile"]]))
    grouped: Dict[str, Dict[str, dict]] = {}
    for state in normalized:
        grouped.setdefault(state["stateId"], {})[state["viewportProfile"]] = state
    for state_id, by_profile in grouped.items():
        standard = by_profile["desktop"]["viewport"]
        constrained = by_profile["desktop-sidebar"]["viewport"]
        if standard["width"] != constrained["width"] or standard["height"] != constrained["height"] or constrained["contentWidth"] >= standard["contentWidth"]:
            raise VisualReportError("viewport-profile-mismatch", f"sidebar profile must prove a narrower student content width: {state_id}", path="states")
    blockers = [finding for state in normalized for finding in state["findings"] if finding["severity"] == "blocker"]
    blocker_count = payload.get("blockerCount")
    if isinstance(blocker_count, bool) or not isinstance(blocker_count, int) or blocker_count != len(blockers):
        raise VisualReportError("blocker-count-mismatch", "blockerCount must exactly match visual findings", path="blockerCount")
    if blocker_count:
        raise VisualReportError("visual-check-blocked", "visual report contains one or more unresolved blockers", path="blockerCount")
    return {
        "schemaVersion": VISUAL_REPORT_VERSION,
        "artifactHashes": dict(hashes),
        "captureAvailable": True,
        "repairRound": repair_round,
        "capturedAt": payload["capturedAt"].strip(),
        "states": normalized,
        "blockerCount": 0,
    }


def _commit_document(report: Mapping[str, object]) -> dict:
    return {**dict(report), "reportHash": canonical_json_hash(report)}


def _read_report(root: Path, *, required: bool = True) -> dict | None:
    commit = _safe_json(root, VISUAL_REPORT_RELATIVE_PATH, required=required)
    if commit is None:
        return None
    if not isinstance(commit, dict) or set(commit) != _COMMIT_FIELDS:
        raise VisualReportError("invalid-visual-commit", "visual report commit has an unsupported shape")
    report = {key: value for key, value in commit.items() if key != "reportHash"}
    if not isinstance(commit.get("reportHash"), str) or commit["reportHash"] != canonical_json_hash(report):
        raise VisualReportError("visual-commit-mismatch", "visual report changed outside its atomic commit")
    return report


def _write_all(descriptor: int, content: bytes) -> None:
    offset = 0
    while offset < len(content):
        written = os.write(descriptor, content[offset:])
        if not isinstance(written, int) or written <= 0:
            raise OSError("short visual report write")
        offset += written


def _write_report(root: Path, report: Mapping[str, object]) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    directory_flags = flags | getattr(os, "O_DIRECTORY", 0)
    root_fd = os.open(root, directory_flags)
    work_fd = None
    temporary = None
    try:
        work_fd = os.open(".course-work", directory_flags, dir_fd=root_fd)
        name = Path(VISUAL_REPORT_RELATIVE_PATH).name
        try:
            existing = os.stat(name, dir_fd=work_fd, follow_symlinks=False)
            if stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode):
                raise VisualReportError("symlink-evidence", "visual report destination must be a regular file", path=VISUAL_REPORT_RELATIVE_PATH)
            mode = stat.S_IMODE(existing.st_mode)
        except FileNotFoundError:
            mode = 0o644
        temporary = f".{name}.{secrets.token_hex(16)}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), mode, dir_fd=work_fd)
        try:
            _write_all(descriptor, dump_json(_commit_document(report)).encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.rename(temporary, name, src_dir_fd=work_fd, dst_dir_fd=work_fd)
        temporary = None
        try:
            os.fsync(work_fd)
        except OSError:
            pass
    except VisualReportError:
        raise
    except OSError as exc:
        raise VisualReportError("unsafe-destination", "visual report destination cannot be written safely", path=".course-work") from exc
    finally:
        if work_fd is not None:
            if temporary is not None:
                try:
                    os.unlink(temporary, dir_fd=work_fd)
                except OSError:
                    pass
            os.close(work_fd)
        os.close(root_fd)


def record_visual_report(root: Path, payload: dict) -> dict:
    """Validate and atomically commit current renderer-backed visual evidence."""
    root = _safe_root(root)
    try:
        with _plan_guard(root, timeout_seconds=30):
            hashes, plan, course = _current_context_at(root)
            report = _validate_payload(payload, hashes=hashes, plan=plan, course=course, root=root)
            _write_report(root, report)
            return report
    except PlanApprovalError as exc:
        if exc.code in {"plan-lock-timeout", "plan-lock-unavailable"}:
            raise VisualReportError("visual-retryable-lock", "visual report is waiting for a course edit; retry shortly", path=".course-work") from exc
        raise VisualReportError(exc.code, "approved page plan is unavailable for visual inspection", path=exc.path) from exc


def verify_prepreview_visual(root: Path) -> Dict[str, str]:
    """Return current visual gate evidence, or fail closed."""
    root = _safe_root(root)
    hashes, plan, course = _current_context_at(root)
    payload = _read_report(root)
    report = _validate_payload(payload, hashes=hashes, plan=plan, course=course, root=root)
    return {"prepreviewVisualHash": canonical_json_hash(report), **hashes}
