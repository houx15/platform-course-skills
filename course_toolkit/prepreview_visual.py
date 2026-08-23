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
from datetime import datetime, timezone
from pathlib import Path
import re
import secrets
import stat
import struct
from typing import Dict, List, Mapping, Sequence, Set, Tuple
import zlib

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
from .instructional_validation import _effective_step_states
from .workflow import hash_path


VISUAL_REPORT_VERSION = "1.0"
MAX_AUTONOMOUS_REPAIR_ROUNDS = 3
VISUAL_REPORT_RELATIVE_PATH = ".course-work/prepreview-visual-report.json"
SCREENSHOT_ROOT_RELATIVE_PATH = ".course-work/visual-check/screenshots"
VISUAL_ATTEMPT_LEDGER_RELATIVE_PATH = ".course-work/prepreview-visual-attempts.json"
VIEWPORT_PROFILES = ("desktop", "desktop-sidebar")

VIEWPORT_PROFILE_MANIFEST = {
    "desktop": {
        "viewport": {"width": 1440, "height": 900},
        "contentRect": {"x": 0, "y": 0, "width": 1440, "height": 900},
        "sidebarRect": None,
        "deviceScaleFactor": 1,
        "annotationPanelCollapsed": True,
    },
    "desktop-sidebar": {
        "viewport": {"width": 1440, "height": 900},
        "contentRect": {"x": 0, "y": 0, "width": 1120, "height": 900},
        "sidebarRect": {"x": 1120, "y": 0, "width": 320, "height": 900},
        "deviceScaleFactor": 1,
        "annotationPanelCollapsed": True,
    },
}
VIEWPORT_MEASUREMENT_CONTRACT = {"rectCoordinateSpace": "viewport-css-pixels"}

MAX_CANDIDATE_BYTES = 8 * 1024 * 1024
MAX_SCREENSHOT_BYTES = 40 * 1024 * 1024
MAX_DEAD_REGION_RATIO = 0.35
MIN_RENDERER_WIDTH = 1280
MIN_RENDERER_HEIGHT = 720

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
    "viewportProfileHash",
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
        "subjectBlockId",
        "action",
        "currentStepId",
        "workflowTrace",
        "stateMarkers",
        "protocolStatus",
        "viewportProfile",
        "viewport",
        "annotationPanelCollapsed",
        "rectCoordinateSpace",
        "screenshotPath",
        "screenshotSha256",
        "visibleBlockIds",
        "enabledBlockIds",
        "domRects",
        "mediaMeasurements",
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
_RECT_OPTIONAL_FIELDS = frozenset({"fontSizePx"})
_FINDING_FIELDS = frozenset({"code", "severity", "message", "blockIds"})
_ACTION_FIELDS = frozenset({"kind", "eventType", "sourceId", "interactionId"})
_TRACE_FIELDS = frozenset({"fromStepId", "eventType", "sourceId", "interactionId", "toStepId"})
_PROTOCOL_FIELDS = frozenset({"handshakeReceived", "activateReceived", "enableReceived", "completionSent", "sessionTokenEchoed"})
_MEDIA_FIELDS = frozenset({"blockId", "itemId", "kind", "width", "height", "intrinsicAspectRatio", "renderedAspectRatio", "pdfPagePortrait"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SCREENSHOT_SUFFIXES = frozenset({".png"})
_SECRET_TEXT = re.compile(r"OSS_ADMIN_KEY|oss" r"-admin-[0-9a-z]+|authorization\s*:\s*bearer", re.I)
_LEDGER_FIELDS = frozenset({"schemaVersion", "contexts", "ledgerHash"})
_LEDGER_CONTEXT_FIELDS = frozenset({"nextRepairRound", "failedAttempts", "successfulReportHash"})
_FAILED_ATTEMPT_FIELDS = frozenset({"repairRound", "payloadHash", "errorCode", "errorPath", "blockerCodes", "capturedAt"})


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


def _action(kind: str, event_type: str | None = None, source_id: str | None = None, interaction_id: str | None = None) -> dict:
    return {"kind": kind, "eventType": event_type, "sourceId": source_id, "interactionId": interaction_id}


def _workflow_steps(slice_data: Mapping[str, object]) -> Tuple[str, Dict[str, dict]]:
    workflow = slice_data.get("workflow") if isinstance(slice_data.get("workflow"), dict) else {}
    initial = workflow.get("initialStepId")
    steps = {
        step["id"]: step
        for step in workflow.get("steps", []) if isinstance(workflow.get("steps"), list)
        if isinstance(step, dict) and isinstance(step.get("id"), str)
    }
    if not isinstance(initial, str) or initial not in steps:
        raise VisualReportError("invalid-workflow", "Slice has no valid initial Workflow step", path="course/course.json")
    return initial, steps


def _transition_specs(slice_data: Mapping[str, object]) -> List[Tuple[str, dict, str]]:
    _initial, steps = _workflow_steps(slice_data)
    result: List[Tuple[str, dict, str]] = []
    for step_id, step in steps.items():
        for transition in step.get("transitions", []) if isinstance(step.get("transitions"), list) else []:
            if isinstance(transition, dict) and isinstance(transition.get("on"), dict) and isinstance(transition.get("to"), str):
                result.append((step_id, transition["on"], transition["to"]))
    return result


def _spec(
    *,
    state_id: str,
    part_id: str,
    slice_id: str,
    kind: str,
    subject_block_id: str | None,
    action: dict,
    allowed_steps: Sequence[str],
    markers: Sequence[str],
    event_observed: bool = False,
    requires_enabled: bool = False,
    requires_clickable: bool = False,
    requires_focused: bool = False,
    protocol_stage: str | None = None,
) -> dict:
    return {
        "stateId": state_id,
        "partId": part_id,
        "sliceId": slice_id,
        "kind": kind,
        "blockId": subject_block_id,
        "action": action,
        "allowedCurrentStepIds": tuple(sorted(set(allowed_steps))),
        "markers": tuple(sorted(set(markers))),
        "eventObserved": event_observed,
        "requiresEnabled": requires_enabled,
        "requiresClickable": requires_clickable,
        "requiresFocused": requires_focused,
        "protocolStage": protocol_stage,
    }


_LEARNER_ACTION_EVENTS = frozenset(
    {
        "student.continue",
        "pdf.opened",
        "pdf.pageChanged",
        "video.started",
        "video.paused",
        "video.ended",
        "video.interaction.completed",
        "interaction.completed",
        "answer.submitted",
        "answer.correct",
        "answer.incorrect",
        "answer.attemptsExhausted",
        "block.completed",
    }
)


def _expected_state_specs(course: Mapping[str, object]) -> List[dict]:
    """Return the course-only baseline; root-aware expansion adds video cues."""
    specs: List[dict] = []
    for part_id, slices in _course_parts(course):
        for slice_data in slices:
            slice_id = slice_data["id"]
            prefix = f"{part_id}/{slice_id}"
            initial_step, steps = _workflow_steps(slice_data)
            transitions = _transition_specs(slice_data)
            specs.append(
                _spec(
                    state_id=f"{prefix}/initial",
                    part_id=part_id,
                    slice_id=slice_id,
                    kind="initial",
                    subject_block_id=None,
                    action=_action("initial"),
                    allowed_steps=[initial_step],
                    markers=["slice.initial"],
                )
            )
            narration_ids = {
                item["id"]
                for item in slice_data.get("narrations", []) if isinstance(slice_data.get("narrations"), list)
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            }
            for narration_id in sorted(narration_ids):
                targets = [target for _step, event, target in transitions if event.get("type") == "narration.ended" and event.get("sourceId") == narration_id]
                if targets:
                    specs.append(
                        _spec(
                            state_id=f"{prefix}/narration-complete:{narration_id}",
                            part_id=part_id,
                            slice_id=slice_id,
                            kind="narration-complete",
                            subject_block_id=None,
                            action=_action("narration-complete", "narration.ended", narration_id),
                            allowed_steps=targets,
                            markers=[f"narration.completed:{narration_id}"],
                            event_observed=True,
                        )
                    )
            block_ids = {block.get("id") for block in slice_data["blocks"] if isinstance(block, dict)}
            for step_id, event, _target in transitions:
                event_type = event.get("type")
                if event_type not in _LEARNER_ACTION_EVENTS:
                    continue
                source_id = event.get("sourceId") if isinstance(event.get("sourceId"), str) else None
                interaction_id = event.get("interactionId") if isinstance(event.get("interactionId"), str) else None
                subject = source_id if source_id in block_ids else None
                suffix = ":".join(value for value in (step_id, event_type, source_id or "any", interaction_id or "any") if value)
                focus_required = any(
                    isinstance(action, dict)
                    and action.get("type") == "focus"
                    and isinstance(action.get("target"), dict)
                    and action["target"].get("blockId") == subject
                    for action in steps[step_id].get("enterActions", []) if isinstance(steps[step_id].get("enterActions"), list)
                )
                specs.append(
                    _spec(
                        state_id=f"{prefix}/action-ready:{suffix}",
                        part_id=part_id,
                        slice_id=slice_id,
                        kind="action-ready",
                        subject_block_id=subject,
                        action=_action("learner-action", event_type, source_id, interaction_id),
                        allowed_steps=[step_id],
                        markers=[f"action.ready:{event_type}:{source_id or 'any'}"],
                        requires_enabled=subject is not None,
                        requires_clickable=subject is not None,
                        requires_focused=focus_required,
                    )
                )
            for block in slice_data["blocks"]:
                if not isinstance(block, dict) or not _nonempty(block.get("id")) or not _nonempty(block.get("type")):
                    raise VisualReportError("invalid-course", "Slice contains an invalid Block", path="course/course.json")
                block_id = block["id"]
                if block["type"] in {"singleChoice", "fillBlank"}:
                    for branch in _assessment_branches(block):
                        event_type = {
                            "correct": "answer.correct",
                            "incorrect": "answer.incorrect",
                            "attempts-exhausted": "answer.attemptsExhausted",
                            "submitted": "answer.submitted",
                        }[branch]
                        specs.append(
                            _spec(
                                state_id=f"{prefix}/answer:{block_id}:{branch}",
                                part_id=part_id,
                                slice_id=slice_id,
                                kind=f"answer-{branch}",
                                subject_block_id=block_id,
                                action=_action("answer-branch", event_type, block_id),
                                allowed_steps=list(steps),
                                markers=[f"answer.{branch}:{block_id}"],
                                event_observed=True,
                                requires_enabled=True,
                                requires_clickable=True,
                            )
                        )
                elif block["type"] == "interactiveHtml":
                    for html_state in ("ready", "active"):
                        specs.append(
                            _spec(
                                state_id=f"{prefix}/html:{block_id}:{html_state}",
                                part_id=part_id,
                                slice_id=slice_id,
                                kind=f"html-{html_state}",
                                subject_block_id=block_id,
                                action=_action("html-protocol", None, block_id),
                                allowed_steps=list(steps),
                                markers=[f"html.{html_state}:{block_id}"],
                                requires_enabled=True,
                                requires_clickable=True,
                                protocol_stage=html_state,
                            )
                        )
                    if isinstance(block.get("completion"), dict) and block["completion"].get("rule") == "interaction-complete":
                        specs.append(
                            _spec(
                                state_id=f"{prefix}/html:{block_id}:completed",
                                part_id=part_id,
                                slice_id=slice_id,
                                kind="html-completed",
                                subject_block_id=block_id,
                                action=_action("html-protocol", "interaction.completed", block_id, block_id),
                                allowed_steps=list(steps),
                                markers=[f"html.completed:{block_id}"],
                                event_observed=True,
                                requires_enabled=True,
                                requires_clickable=True,
                                protocol_stage="completed",
                            )
                        )
            completion_sources: List[Tuple[str, dict]] = []
            completion_steps = {
                step_id
                for step_id, step in steps.items()
                if any(isinstance(action, dict) and action.get("type") == "completeSlice" for action in step.get("enterActions", []) if isinstance(step.get("enterActions"), list))
            }
            for step_id, event, target in transitions:
                if target in completion_steps:
                    completion_sources.append((step_id, event))
            if completion_sources:
                for step_id, event in completion_sources:
                    event_type = event.get("type")
                    source_id = event.get("sourceId") if isinstance(event.get("sourceId"), str) else None
                    interaction_id = event.get("interactionId") if isinstance(event.get("interactionId"), str) else None
                    specs.append(
                        _spec(
                            state_id=f"{prefix}/final-pre-completion:{step_id}:{event_type}:{source_id or 'any'}",
                            part_id=part_id,
                            slice_id=slice_id,
                            kind="final-pre-completion",
                            subject_block_id=source_id if source_id in block_ids else None,
                            action=_action("complete-slice", event_type, source_id, interaction_id),
                            allowed_steps=[step_id],
                            markers=["slice.pre-completion"],
                            requires_enabled=source_id in block_ids,
                            requires_clickable=source_id in block_ids,
                        )
                    )
            elif initial_step in completion_steps:
                specs.append(
                    _spec(
                        state_id=f"{prefix}/final-pre-completion:{initial_step}:immediate:any",
                        part_id=part_id,
                        slice_id=slice_id,
                        kind="final-pre-completion",
                        subject_block_id=None,
                        action=_action("complete-slice"),
                        allowed_steps=[initial_step],
                        markers=["slice.pre-completion"],
                    )
                )
    return specs


def _safe_course_json_asset(root: Path, relative: str) -> dict:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise VisualReportError("unsafe-video-interaction", "video interaction source must be a safe course-relative path", path=str(relative))
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise VisualReportError("unsafe-video-interaction", "video interaction source may not contain dot or parent components", path=relative)
    document = _safe_json(root, "course/" + relative)
    if not isinstance(document, dict):
        raise VisualReportError("invalid-video-interaction", "video interaction document must be a JSON object", path=relative)
    return document


def _validate_cue_activity(activity: object, *, path: str) -> dict:
    if not isinstance(activity, dict) or activity.get("type") not in {"singleChoice", "fillBlank"}:
        raise VisualReportError("invalid-video-interaction", "video cue activity type is invalid", path=path)
    activity_type = activity["type"]
    expected_fields = {"type", "assessment", "completion", "options"} if activity_type == "singleChoice" else {"type", "assessment", "completion"}
    if set(activity) != expected_fields:
        raise VisualReportError("invalid-video-interaction", "video cue activity has unknown or missing fields", path=path)
    option_ids: Set[str] = set()
    if activity_type == "singleChoice":
        options = activity.get("options")
        if not isinstance(options, list) or len(options) < 2:
            raise VisualReportError("invalid-video-interaction", "video cue choice activity needs at least two options", path=path)
        for option in options:
            if not isinstance(option, dict) or set(option) != {"id", "label"} or not _nonempty(option.get("id"), maximum=160) or not _nonempty(option.get("label")) or option["id"] in option_ids:
                raise VisualReportError("invalid-video-interaction", "video cue option is invalid or duplicated", path=path)
            option_ids.add(option["id"])
    assessment = activity.get("assessment")
    completion = activity.get("completion")
    if not isinstance(assessment, dict) or not isinstance(completion, dict):
        raise VisualReportError("invalid-video-interaction", "video cue assessment and completion are required", path=path)
    mode = assessment.get("mode")
    if activity_type == "singleChoice":
        if mode == "survey":
            assessment_valid = set(assessment) == {"mode"}
        elif mode == "graded":
            allowed = {"mode", "correctOptionId", "correctFeedback", "incorrectFeedback"}
            assessment_valid = (
                set(assessment).issubset(allowed)
                and {"mode", "correctOptionId"}.issubset(assessment)
                and assessment.get("correctOptionId") in option_ids
                and all(_nonempty(assessment[field]) for field in ("correctFeedback", "incorrectFeedback") if field in assessment)
            )
        elif expected_kind == "interactiveHtml":
            if (
                raw.get("pdfPagePortrait") is not None
                or not _number(raw.get("intrinsicAspectRatio"))
                or not _number(raw.get("renderedAspectRatio"))
                or float(raw["intrinsicAspectRatio"]) <= 0
                or float(raw["renderedAspectRatio"]) <= 0
            ):
                raise VisualReportError("invalid-media-measurement", "interactive HTML must report a positive design hint and rendered frame ratio", path=item_path)
            if float(raw["width"]) < 240 or float(raw["height"]) < 135:
                raise VisualReportError("unreadable-content", "interactive HTML is too small to inspect", path=item_path)
            declared = block.get("aspectRatio")
            expected_hint = {"1:1": 1.0, "4:3": 4 / 3}.get(declared)
            if expected_hint is not None and abs(float(raw["intrinsicAspectRatio"]) - expected_hint) > 0.01:
                raise VisualReportError("aspect-distortion", "HTML measurement contradicts its declared design hint", path=item_path)
            # v1.8.0 deliberately gives the iframe the complete Slot. Its
            # rendered frame ratio may differ from the design hint; that is fit,
            # not distortion. The document itself must be checked for reachable
            # content and internal scrolling in the browser.
        else:
            assessment_valid = False
    else:
        if mode == "reflection":
            assessment_valid = set(assessment) == {"mode", "rubric"} and _nonempty(assessment.get("rubric"))
        elif mode == "graded":
            allowed = {"mode", "acceptedAnswers", "caseSensitive", "correctFeedback", "incorrectFeedback"}
            answers = assessment.get("acceptedAnswers")
            assessment_valid = (
                set(assessment).issubset(allowed)
                and {"mode", "acceptedAnswers"}.issubset(assessment)
                and isinstance(answers, list)
                and bool(answers)
                and all(_nonempty(answer) for answer in answers)
                and ("caseSensitive" not in assessment or isinstance(assessment["caseSensitive"], bool))
                and all(_nonempty(assessment[field]) for field in ("correctFeedback", "incorrectFeedback") if field in assessment)
            )
        else:
            assessment_valid = False
    rule = completion.get("rule")
    completion_valid = (
        (rule in {"submit-any", "submit-correct"} and set(completion) == {"rule"})
        or (
            rule == "submit-correct-or-exhausted"
            and set(completion) == {"rule", "maxAttempts"}
            and isinstance(completion.get("maxAttempts"), int)
            and not isinstance(completion.get("maxAttempts"), bool)
            and completion["maxAttempts"] > 0
        )
    )
    if not assessment_valid or not completion_valid:
        raise VisualReportError("invalid-video-interaction", "video cue assessment or completion shape is invalid", path=path)
    return activity


def _cue_specs(root: Path, course: Mapping[str, object]) -> List[dict]:
    specs: List[dict] = []
    for part_id, slices in _course_parts(course):
        for slice_data in slices:
            prefix = f"{part_id}/{slice_data['id']}"
            _initial, steps = _workflow_steps(slice_data)
            for block in slice_data["blocks"]:
                interaction = block.get("interaction") if isinstance(block, dict) else None
                if block.get("type") != "video" or not isinstance(block.get("id"), str) or not isinstance(interaction, dict) or not isinstance(interaction.get("source"), str):
                    continue
                document = _safe_course_json_asset(root, interaction["source"])
                video = document.get("video")
                if (
                    set(document) != {"schemaVersion", "video"}
                    or document.get("schemaVersion") != "1.1"
                    or not isinstance(video, dict)
                    or set(video) != {"blockId", "source", "durationSeconds", "cues"}
                    or video.get("blockId") != block["id"]
                    or video.get("source") != block.get("source")
                    or not _number(video.get("durationSeconds"))
                    or float(video["durationSeconds"]) <= 0
                    or not isinstance(video.get("cues"), list)
                ):
                    raise VisualReportError("invalid-video-interaction", "video interaction document does not match its owning Block", path=interaction["source"])
                seen: Set[str] = set()
                previous_time = -1.0
                for cue in video["cues"]:
                    if (
                        not isinstance(cue, dict)
                        or set(cue) != {"id", "atSeconds", "pauseVideo", "required", "prompt", "activity"}
                        or not _nonempty(cue.get("id"), maximum=160)
                        or cue["id"] in seen
                        or not _number(cue.get("atSeconds"))
                        or float(cue["atSeconds"]) < 0
                        or float(cue["atSeconds"]) <= previous_time
                        or float(cue["atSeconds"]) > float(video["durationSeconds"])
                        or not isinstance(cue.get("pauseVideo"), bool)
                        or not isinstance(cue.get("required"), bool)
                        or not _nonempty(cue.get("prompt"))
                        or not isinstance(cue.get("activity"), dict)
                    ):
                        raise VisualReportError("invalid-video-interaction", "video interaction cue is invalid or duplicated", path=interaction["source"])
                    _validate_cue_activity(cue["activity"], path=interaction["source"])
                    seen.add(cue["id"])
                    previous_time = float(cue["atSeconds"])
                    cue_id = cue["id"]
                    base = dict(
                        part_id=part_id,
                        slice_id=slice_data["id"],
                        subject_block_id=block["id"],
                        allowed_steps=list(steps),
                        requires_enabled=True,
                        requires_clickable=True,
                    )
                    specs.append(
                        _spec(
                            state_id=f"{prefix}/video-modal:{block['id']}:{cue_id}",
                            kind="video-modal",
                            action=_action("video-cue", "video.interaction.shown", block["id"], cue_id),
                            markers=[f"video.modal:{block['id']}:{cue_id}"],
                            event_observed=True,
                            **base,
                        )
                    )
                    for branch in _assessment_branches(cue["activity"]):
                        branch_event = {
                            "correct": "answer.correct",
                            "incorrect": "answer.incorrect",
                            "attempts-exhausted": "answer.attemptsExhausted",
                            "submitted": "answer.submitted",
                        }[branch]
                        specs.append(
                            _spec(
                                state_id=f"{prefix}/video-modal:{block['id']}:{cue_id}:{branch}",
                                kind=f"video-modal-{branch}",
                                action=_action("video-cue-answer", branch_event, cue_id, cue_id),
                                markers=[f"video.modal:{block['id']}:{cue_id}", f"video.answer.{branch}:{block['id']}:{cue_id}"],
                                event_observed=True,
                                **base,
                            )
                        )
    return specs


def _root_expected_state_specs(root: Path, course: Mapping[str, object]) -> List[dict]:
    specs = [*_expected_state_specs(course), *_cue_specs(root, course)]
    if len({spec["stateId"] for spec in specs}) != len(specs):
        raise VisualReportError("duplicate-expected-state", "course expands to duplicate visual state identities", path="course/course.json")
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
            "viewportProfileHash": canonical_json_hash(
                {"profiles": VIEWPORT_PROFILE_MANIFEST, "measurementContract": VIEWPORT_MEASUREMENT_CONTRACT}
            ),
        }
    )
    if set(hashes) != set(_HASH_FIELDS):
        raise VisualReportError("hashes-required", "current course evidence does not provide every visual binding hash", path="artifactHashes")
    return hashes, plan, course


def _decode_png(content: bytes, *, path: str) -> Tuple[int, int]:
    if not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise VisualReportError("invalid-screenshot", "screenshot is not a PNG image", path=path)
    offset = 8
    ihdr: Tuple[int, int, int] | None = None
    compressed: List[bytes] = []
    saw_iend = False
    while offset < len(content):
        if len(content) - offset < 12:
            raise VisualReportError("invalid-screenshot", "PNG chunk is truncated", path=path)
        length = struct.unpack(">I", content[offset : offset + 4])[0]
        chunk_type = content[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if crc_end > len(content):
            raise VisualReportError("invalid-screenshot", "PNG chunk payload is truncated", path=path)
        data = content[data_start:data_end]
        expected_crc = struct.unpack(">I", content[data_end:crc_end])[0]
        if zlib.crc32(chunk_type + data) & 0xFFFFFFFF != expected_crc:
            raise VisualReportError("invalid-screenshot", "PNG chunk CRC is invalid", path=path)
        if chunk_type == b"IHDR":
            if ihdr is not None or offset != 8 or length != 13:
                raise VisualReportError("invalid-screenshot", "PNG IHDR is invalid", path=path)
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(">IIBBBBB", data)
            if width <= 1 or height <= 1 or width > 10000 or height > 10000 or bit_depth != 8 or color_type not in {2, 6} or compression != 0 or filtering != 0 or interlace != 0:
                raise VisualReportError("invalid-screenshot", "PNG screenshot dimensions or encoding are unsupported", path=path)
            ihdr = (width, height, 3 if color_type == 2 else 4)
        elif chunk_type == b"IDAT":
            if ihdr is None or saw_iend:
                raise VisualReportError("invalid-screenshot", "PNG IDAT ordering is invalid", path=path)
            compressed.append(data)
        elif chunk_type == b"IEND":
            if length != 0 or ihdr is None or not compressed:
                raise VisualReportError("invalid-screenshot", "PNG IEND is invalid", path=path)
            saw_iend = True
            offset = crc_end
            break
        offset = crc_end
    if not saw_iend or offset != len(content) or ihdr is None:
        raise VisualReportError("invalid-screenshot", "PNG screenshot is incomplete or has trailing bytes", path=path)
    width, height, channels = ihdr
    expected_size = height * (1 + width * channels)
    if expected_size > MAX_SCREENSHOT_BYTES:
        raise VisualReportError("screenshot-too-large", "decoded screenshot exceeds the allowed size", path=path)
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(b"".join(compressed), expected_size + 1)
        raw += decoder.flush()
    except zlib.error as exc:
        raise VisualReportError("invalid-screenshot", "PNG image data cannot be decoded", path=path) from exc
    if decoder.unconsumed_tail or decoder.unused_data or not decoder.eof or len(raw) != expected_size or any(raw[row * (1 + width * channels)] > 4 for row in range(height)):
        raise VisualReportError("invalid-screenshot", "PNG scanlines are truncated or invalid", path=path)
    return width, height


def _safe_screenshot_bytes(root: Path, relative: str) -> Tuple[bytes, Tuple[int, int]]:
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
        dimensions = _decode_png(content, path=relative)
        return content, dimensions
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
    if profile not in VIEWPORT_PROFILES:
        raise VisualReportError("invalid-viewport-profile", "viewportProfile is unsupported", path=path)
    expected = {key: item for key, item in VIEWPORT_PROFILE_MANIFEST[profile].items() if key != "annotationPanelCollapsed"}
    if value != expected:
        raise VisualReportError("invalid-viewport", "viewport must exactly match the canonical student-shell profile", path=path)
    if value["viewport"]["width"] < MIN_RENDERER_WIDTH or value["viewport"]["height"] < MIN_RENDERER_HEIGHT:
        raise VisualReportError("invalid-viewport", "renderer viewport is below the supported desktop minimum", path=path)
    return value


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
        if float(raw["width"]) < 0 or float(raw["height"]) < 0:
            raise VisualReportError("invalid-dom-rect", "DOM rectangle dimensions may not be negative", path=item_path)
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
        severity = raw.get("severity").strip().lower() if isinstance(raw.get("severity"), str) else raw.get("severity")
        code = raw.get("code").strip().lower() if isinstance(raw.get("code"), str) else raw.get("code")
        message = " ".join(raw.get("message").split()) if isinstance(raw.get("message"), str) else raw.get("message")
        if severity not in {"blocker", "warning", "review"} or not _nonempty(code, maximum=120) or not _nonempty(message):
            raise VisualReportError("invalid-finding", "visual finding requires code, severity, and message", path=item_path)
        if _SECRET_TEXT.search(message):
            raise VisualReportError("credential-leak", "visual reports may not contain credentials", path=item_path)
        blocks = _stable_ids(raw.get("blockIds"), field=f"{item_path}.blockIds", known=known_blocks)
        if severity == "blocker" and code not in VISUAL_BLOCKER_CODES:
            raise VisualReportError("unknown-blocker-code", "visual blocker must use a standardized blocker code", path=item_path)
        if code in VISUAL_BLOCKER_CODES and severity != "blocker":
            raise VisualReportError("blocker-downgrade-forbidden", "a standardized visual blocker cannot be recorded at a lower severity", path=item_path)
        result.append({"code": code, "severity": severity, "message": message, "blockIds": blocks})
    keys = [(item["code"], item["severity"], item["message"], tuple(item["blockIds"])) for item in result]
    if len(keys) != len(set(keys)):
        raise VisualReportError("duplicate-finding", "visual findings must not contain duplicates", path=path)
    return sorted(result, key=lambda item: (item["severity"], item["code"], item["message"], item["blockIds"]))


def _event_matches(matcher: Mapping[str, object], event: Mapping[str, object]) -> bool:
    return all(matcher.get(field) is None or matcher.get(field) == event.get(field) for field in ("type", "sourceId", "interactionId"))


def _apply_step_actions(step: Mapping[str, object], visible: Set[str], enabled: Set[str], focus: str | None) -> str | None:
    for action in step.get("enterActions", []) if isinstance(step.get("enterActions"), list) else []:
        if not isinstance(action, dict):
            continue
        action_type = action.get("type")
        target = action.get("targetId")
        if action_type == "show" and isinstance(target, str):
            visible.add(target)
        elif action_type == "hide" and isinstance(target, str):
            visible.discard(target)
        elif action_type == "enable" and isinstance(target, str):
            enabled.add(target)
        elif action_type == "disable" and isinstance(target, str):
            enabled.discard(target)
        elif action_type == "focus" and isinstance(action.get("target"), dict) and isinstance(action["target"].get("blockId"), str):
            focus = action["target"]["blockId"]
        elif action_type == "clearFocus":
            focus = None
    return focus


def _validate_action(value: object, expected: Mapping[str, object], *, path: str) -> dict:
    if not isinstance(value, dict) or set(value) != _ACTION_FIELDS:
        raise VisualReportError("invalid-action-evidence", "action must contain kind, eventType, sourceId, and interactionId", path=path)
    normalized = {
        field: value.get(field).strip() if isinstance(value.get(field), str) else value.get(field)
        for field in ("kind", "eventType", "sourceId", "interactionId")
    }
    if not _nonempty(normalized["kind"], maximum=120) or any(item is not None and not _nonempty(item, maximum=160) for item in (normalized["eventType"], normalized["sourceId"], normalized["interactionId"])):
        raise VisualReportError("invalid-action-evidence", "action identifiers must be nonempty strings or null", path=path)
    if normalized != dict(expected):
        raise VisualReportError("action-evidence-mismatch", "action evidence does not match the expected authored learner/runtime action", path=path)
    return normalized


def _replay_workflow_trace(slice_data: Mapping[str, object], value: object, *, path: str) -> Tuple[str, Set[str], Set[str], str | None, List[dict]]:
    if not isinstance(value, list) or len(value) > 128:
        raise VisualReportError("invalid-workflow-trace", "workflowTrace must be a bounded array", path=path)
    initial_step, steps = _workflow_steps(slice_data)
    blocks = {block["id"] for block in slice_data.get("blocks", []) if isinstance(block, dict) and isinstance(block.get("id"), str)}
    workflow = slice_data.get("workflow") if isinstance(slice_data.get("workflow"), dict) else {}
    initial_state = workflow.get("initialState") if isinstance(workflow.get("initialState"), dict) else {}
    visible = set(initial_state.get("visibleBlockIds", blocks))
    enabled = set(initial_state.get("enabledBlockIds", blocks))
    focused_target = initial_state.get("focusedTarget") if isinstance(initial_state.get("focusedTarget"), dict) else None
    focus = focused_target.get("blockId") if isinstance(focused_target, dict) and isinstance(focused_target.get("blockId"), str) else None
    current = initial_step
    focus = _apply_step_actions(steps[current], visible, enabled, focus)
    normalized: List[dict] = []
    for index, raw in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(raw, dict) or set(raw) != _TRACE_FIELDS:
            raise VisualReportError("invalid-workflow-trace", "workflow trace edge has unknown or missing fields", path=item_path)
        edge = {
            field: raw.get(field).strip() if isinstance(raw.get(field), str) else raw.get(field)
            for field in ("fromStepId", "eventType", "sourceId", "interactionId", "toStepId")
        }
        if edge["fromStepId"] != current or not _nonempty(edge["eventType"], maximum=160) or not _nonempty(edge["toStepId"], maximum=160) or any(item is not None and not _nonempty(item, maximum=160) for item in (edge["sourceId"], edge["interactionId"])):
            raise VisualReportError("invalid-workflow-trace", "workflow trace edge is disconnected or malformed", path=item_path)
        event = {"type": edge["eventType"], "sourceId": edge["sourceId"], "interactionId": edge["interactionId"]}
        transitions = [transition for transition in steps[current].get("transitions", []) if isinstance(steps[current].get("transitions"), list) and isinstance(transition, dict) and isinstance(transition.get("on"), dict) and _event_matches(transition["on"], event)]
        expected_target = transitions[0].get("to") if transitions else current
        if edge["toStepId"] != expected_target or expected_target not in steps:
            raise VisualReportError("unreachable-visual-state", "workflow trace does not follow the runtime's first matching transition", path=item_path)
        if edge["sourceId"] in blocks and edge["eventType"] in _LEARNER_ACTION_EVENTS and (edge["sourceId"] not in visible or edge["sourceId"] not in enabled):
            raise VisualReportError("unreachable-visual-state", "workflow trace emits a learner event from a hidden or disabled Block", path=item_path)
        current = expected_target
        if current != edge["fromStepId"]:
            focus = _apply_step_actions(steps[current], visible, enabled, focus)
        normalized.append(edge)
    return current, visible.intersection(blocks), enabled.intersection(blocks), focus, normalized


def _trace_contains_action(trace: Sequence[Mapping[str, object]], action: Mapping[str, object]) -> bool:
    return any(
        edge.get("eventType") == action.get("eventType")
        and edge.get("sourceId") == action.get("sourceId")
        and edge.get("interactionId") == action.get("interactionId")
        for edge in trace
    )


def _validate_protocol_status(value: object, stage: str | None, *, path: str) -> dict | None:
    if stage is None:
        if value is not None:
            raise VisualReportError("unexpected-protocol-status", "protocolStatus is allowed only for interactive HTML states", path=path)
        return None
    if not isinstance(value, dict) or set(value) != _PROTOCOL_FIELDS or any(not isinstance(value.get(field), bool) for field in _PROTOCOL_FIELDS):
        raise VisualReportError("invalid-protocol-status", "interactive HTML protocolStatus is incomplete", path=path)
    required = {
        "ready": {"handshakeReceived"},
        "active": {"handshakeReceived", "activateReceived", "enableReceived"},
        "completed": set(_PROTOCOL_FIELDS),
    }[stage]
    if any(value[field] is not True for field in required):
        raise VisualReportError("unreachable-visual-state", f"interactive HTML {stage} protocol handshake is incomplete", path=path)
    return {field: value[field] for field in sorted(_PROTOCOL_FIELDS)}


def _validate_media_measurements(value: object, *, slice_data: Mapping[str, object], visible: Set[str], path: str) -> List[dict]:
    if not isinstance(value, list):
        raise VisualReportError("media-measurements-required", "mediaMeasurements must be an array", path=path)
    blocks = {block["id"]: block for block in slice_data.get("blocks", []) if isinstance(block, dict) and isinstance(block.get("id"), str)}
    expected: Set[Tuple[str, str | None]] = set()
    for block_id in visible:
        block = blocks[block_id]
        if block.get("type") == "images":
            expected.update((block_id, item.get("id")) for item in block.get("items", []) if isinstance(item, dict) and isinstance(item.get("id"), str))
        elif block.get("type") in {"pdf", "video", "interactiveHtml"}:
            expected.add((block_id, None))
    result: List[dict] = []
    seen: Set[Tuple[str, str | None]] = set()
    for index, raw in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(raw, dict) or set(raw) != _MEDIA_FIELDS:
            raise VisualReportError("invalid-media-measurement", "media measurement has unknown or missing fields", path=item_path)
        block_id, item_id = raw.get("blockId"), raw.get("itemId")
        key = (block_id, item_id)
        if key not in expected or key in seen:
            raise VisualReportError("invalid-media-measurement", "media measurement does not identify one visible media surface", path=item_path)
        seen.add(key)
        block = blocks[block_id]
        expected_kind = "image" if block.get("type") == "images" else block.get("type")
        if raw.get("kind") != expected_kind or not _number(raw.get("width")) or not _number(raw.get("height")) or float(raw["width"]) <= 0 or float(raw["height"]) <= 0:
            raise VisualReportError("invalid-media-measurement", "media kind and rendered dimensions are invalid", path=item_path)
        normalized = dict(raw)
        if expected_kind == "pdf":
            if (
                raw.get("pdfPagePortrait") is not True
                or float(raw["width"]) < 320
                or float(raw["height"]) < 400
                or float(raw["height"]) <= float(raw["width"])
                or not _number(raw.get("intrinsicAspectRatio"))
                or not _number(raw.get("renderedAspectRatio"))
                or not 0 < float(raw["intrinsicAspectRatio"]) < 1
                or not 0 < float(raw["renderedAspectRatio"]) < 1
                or abs(float(raw["intrinsicAspectRatio"]) - float(raw["renderedAspectRatio"])) / float(raw["intrinsicAspectRatio"]) > 0.03
            ):
                raise VisualReportError("unreadable-content", "PDF must provide a readable portrait page/viewer surface", path=item_path)
        else:
            if raw.get("pdfPagePortrait") is not None or not _number(raw.get("intrinsicAspectRatio")) or not _number(raw.get("renderedAspectRatio")) or float(raw["intrinsicAspectRatio"]) <= 0 or float(raw["renderedAspectRatio"]) <= 0:
                raise VisualReportError("invalid-media-measurement", "visual media must bind intrinsic and rendered aspect ratios", path=item_path)
            if (
                expected_kind != "interactiveHtml"
                and abs(float(raw["intrinsicAspectRatio"]) - float(raw["renderedAspectRatio"])) / float(raw["intrinsicAspectRatio"]) > 0.03
            ):
                raise VisualReportError("aspect-distortion", "visual media is stretched beyond the allowed tolerance", path=item_path)
            if float(raw["width"]) < 240 or float(raw["height"]) < 135:
                raise VisualReportError("unreadable-content", "visual media is too small to inspect", path=item_path)
        result.append(normalized)
    if seen != expected:
        raise VisualReportError("media-measurement-coverage", "every visible media surface needs type-appropriate measurements", path=path)
    return sorted(result, key=lambda item: (item["blockId"], item["itemId"] or ""))


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
    if raw.get("subjectBlockId") != spec["blockId"]:
        raise VisualReportError("state-subject-mismatch", "visual state subjectBlockId does not match its expected runtime subject", path=path)
    action = _validate_action(raw.get("action"), spec["action"], path=f"{path}.action")
    profile = raw.get("viewportProfile")
    viewport = _validate_viewport(raw.get("viewport"), profile, path=f"{path}.viewport")
    if raw.get("annotationPanelCollapsed") is not True:
        raise VisualReportError("annotation-panel-open", "pre-preview inspection requires the teacher annotation panel to be collapsed", path=f"{path}.annotationPanelCollapsed")
    if raw.get("rectCoordinateSpace") != VIEWPORT_MEASUREMENT_CONTRACT["rectCoordinateSpace"]:
        raise VisualReportError("invalid-coordinate-space", "DOM rectangles must use viewport CSS-pixel coordinates", path=f"{path}.rectCoordinateSpace")
    slice_data = slices[(spec["partId"], spec["sliceId"])]
    blocks = slice_data.get("blocks")
    block_types = {block["id"]: block["type"] for block in blocks if isinstance(block, dict) and isinstance(block.get("id"), str) and isinstance(block.get("type"), str)}
    known_blocks = set(block_types)
    visible = _stable_ids(raw.get("visibleBlockIds"), field=f"{path}.visibleBlockIds", known=known_blocks)
    enabled = _stable_ids(raw.get("enabledBlockIds"), field=f"{path}.enabledBlockIds", known=known_blocks)
    if not set(enabled).issubset(visible):
        raise VisualReportError("enabled-content-hidden", "enabled Blocks must also be visible", path=f"{path}.enabledBlockIds")
    current_step, replay_visible, replay_enabled, replay_focus, trace = _replay_workflow_trace(slice_data, raw.get("workflowTrace"), path=f"{path}.workflowTrace")
    if raw.get("currentStepId") != current_step or current_step not in spec["allowedCurrentStepIds"]:
        raise VisualReportError("unreachable-visual-state", "currentStepId is not reachable for this required visual state", path=f"{path}.currentStepId")
    if visible != sorted(replay_visible) or enabled != sorted(replay_enabled):
        raise VisualReportError("runtime-state-mismatch", "visible/enabled Blocks contradict deterministic Workflow replay", path=path)
    effective_states, workflow_issues = _effective_step_states(slice_data, course_root=root)
    if workflow_issues or current_step not in effective_states or not any(set(v) == replay_visible and set(e) == replay_enabled for v, e in effective_states[current_step]):
        raise VisualReportError("unreachable-visual-state", "visual state is absent from Task4 Workflow reachability evidence", path=f"{path}.workflowTrace")
    if spec["eventObserved"] and not _trace_contains_action(trace, action):
        raise VisualReportError("unreachable-visual-state", "workflow trace does not contain the event required by this visual state", path=f"{path}.workflowTrace")
    if spec["kind"].startswith("video-modal"):
        shown_action = {
            "eventType": "video.interaction.shown",
            "sourceId": spec["blockId"],
            "interactionId": action["interactionId"],
        }
        started_action = {"eventType": "video.started", "sourceId": spec["blockId"], "interactionId": None}
        shown_index = next((index for index, edge in enumerate(trace) if _trace_contains_action([edge], shown_action)), None)
        started_index = next((index for index, edge in enumerate(trace) if _trace_contains_action([edge], started_action)), None)
        if started_index is None or shown_index is None or started_index >= shown_index:
            raise VisualReportError("unreachable-visual-state", "video cue evidence must follow a reachable started-video state", path=f"{path}.workflowTrace")
        if spec["kind"].startswith("video-modal-"):
            answer_index = next((index for index, edge in enumerate(trace) if _trace_contains_action([edge], action)), None)
            if answer_index is None or shown_index >= answer_index:
                raise VisualReportError("unreachable-visual-state", "video cue answer evidence must follow the matching reachable cue modal", path=f"{path}.workflowTrace")
    markers = _stable_ids(raw.get("stateMarkers"), field=f"{path}.stateMarkers")
    if markers != list(spec["markers"]):
        raise VisualReportError("state-marker-mismatch", "stateMarkers must exactly identify the required runtime state", path=f"{path}.stateMarkers")
    protocol_status = _validate_protocol_status(raw.get("protocolStatus"), spec["protocolStage"], path=f"{path}.protocolStatus")
    subject = spec.get("blockId")
    if isinstance(subject, str):
        if subject not in visible:
            raise VisualReportError("missing-content", f"required subject Block is not visible: {subject}", path=f"{path}.visibleBlockIds")
        if spec["requiresEnabled"] and subject not in enabled:
            raise VisualReportError("unreachable-content", f"required subject Block is disabled: {subject}", path=f"{path}.enabledBlockIds")
    rects = _validate_rects(raw.get("domRects"), block_types=block_types, path=f"{path}.domRects")
    rect_by_id = {rect["blockId"]: rect for rect in rects}
    for block_id, rect in rect_by_id.items():
        should_be_visible = block_id in visible
        if rect["visible"] is not should_be_visible:
            raise VisualReportError("runtime-state-mismatch", f"DOM visibility contradicts Workflow state: {block_id}", path=f"{path}.domRects")
        if not should_be_visible and (rect["clickable"] or rect["occluded"] or float(rect["intersectionRatio"]) != 0):
            raise VisualReportError("runtime-state-mismatch", f"hidden Block has visible/clickable geometry: {block_id}", path=f"{path}.domRects")
    required = {subject} if isinstance(subject, str) else set(visible)
    content_rect = viewport["contentRect"]
    for block_id in visible:
        rect = rect_by_id[block_id]
        if not rect["visible"] or float(rect["width"]) <= 0 or float(rect["height"]) <= 0:
            raise VisualReportError("zero-size-content", f"visible Block has zero rendered size: {block_id}", path=f"{path}.domRects")
        x, y = float(rect["x"]), float(rect["y"])
        width, height = float(rect["width"]), float(rect["height"])
        content_left, content_top = float(content_rect["x"]), float(content_rect["y"])
        content_right = content_left + float(content_rect["width"])
        content_bottom = content_top + float(content_rect["height"])
        intersection_width = max(0.0, min(x + width, content_right) - max(x, content_left))
        intersection_height = max(0.0, min(y + height, content_bottom) - max(y, content_top))
        calculated_intersection = (intersection_width * intersection_height) / (width * height)
        if abs(calculated_intersection - float(rect["intersectionRatio"])) > 0.02:
            raise VisualReportError("invalid-dom-rect", f"intersectionRatio contradicts Block geometry: {block_id}", path=f"{path}.domRects")
        if float(rect["intersectionRatio"]) <= 0:
            raise VisualReportError("offscreen-content", f"visible Block is outside the student content viewport: {block_id}", path=f"{path}.domRects")
        if block_id in required and float(rect["intersectionRatio"]) < 0.99:
            raise VisualReportError("offscreen-content", f"required Block is partly outside the student content viewport: {block_id}", path=f"{path}.domRects")
        if rect["occluded"]:
            raise VisualReportError("occluded-content", f"visible Block is occluded: {block_id}", path=f"{path}.domRects")
        if block_id in enabled and spec["requiresClickable"] and block_id == subject and not rect["clickable"]:
            raise VisualReportError("unclickable-content", f"enabled Block cannot be clicked: {block_id}", path=f"{path}.domRects")
        if block_types[block_id] in {"text", "singleChoice", "fillBlank"}:
            if "fontSizePx" not in rect or float(rect["fontSizePx"]) < 14:
                raise VisualReportError("unreadable-content", f"learner-visible text lacks a readable measured font size: {block_id}", path=f"{path}.domRects")

    media_measurements = _validate_media_measurements(raw.get("mediaMeasurements"), slice_data=slice_data, visible=set(visible), path=f"{path}.mediaMeasurements")

    observations = _validate_observations(raw, has_co_visibility=any(item.startswith("co-visible:") for item in plan_bindings.get((spec["partId"], spec["sliceId"]), [])), path=path)
    if observations["overflow"]["horizontal"] or observations["overflow"]["clippedBlockIds"]:
        raise VisualReportError("offscreen-content", "core visual content overflows or is clipped", path=f"{path}.overflow")
    if observations["occlusion"]["occludedBlockIds"]:
        raise VisualReportError("occluded-content", "visual observation contains occluded Blocks", path=f"{path}.occlusion")
    if observations["scroll"]["coreTaskRequiresUnexpectedScroll"]:
        raise VisualReportError("unexpected-core-scroll", "core task is discoverable only through unexpected scrolling", path=f"{path}.scroll")
    focus = observations["focus"]
    expected_focus = replay_focus
    if focus["expectedTargetId"] != expected_focus or focus["actualTargetId"] != expected_focus or focus["visible"] != (expected_focus is None or expected_focus in visible):
        raise VisualReportError("focus-state-mismatch", "focus observation contradicts deterministic Workflow replay", path=f"{path}.focus")
    if spec["requiresFocused"] and replay_focus != subject:
        raise VisualReportError("unreachable-content", "required learner action Block is not focused", path=f"{path}.focus")
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
    screenshot_bytes, screenshot_dimensions = _safe_screenshot_bytes(root, screenshot_path)
    if hashlib.sha256(screenshot_bytes).hexdigest() != screenshot_sha:
        raise VisualReportError("screenshot-sha-mismatch", "screenshot bytes do not match screenshotSha256", path=f"{path}.screenshotSha256")
    expected_dimensions = (
        viewport["viewport"]["width"] * viewport["deviceScaleFactor"],
        viewport["viewport"]["height"] * viewport["deviceScaleFactor"],
    )
    if screenshot_dimensions != expected_dimensions:
        raise VisualReportError("screenshot-dimension-mismatch", "decoded screenshot dimensions do not match the bound capture surface", path=f"{path}.screenshotPath")
    return {
        "stateId": state_id,
        "partId": spec["partId"],
        "sliceId": spec["sliceId"],
        "subjectBlockId": subject,
        "action": action,
        "currentStepId": current_step,
        "workflowTrace": trace,
        "stateMarkers": markers,
        "protocolStatus": protocol_status,
        "viewportProfile": profile,
        "viewport": viewport,
        "annotationPanelCollapsed": True,
        "rectCoordinateSpace": "viewport-css-pixels",
        "screenshotPath": screenshot_path,
        "screenshotSha256": screenshot_sha,
        "visibleBlockIds": visible,
        "enabledBlockIds": enabled,
        "domRects": rects,
        "mediaMeasurements": media_measurements,
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


def _scan_credentials(value: object, *, path: str = "$report") -> None:
    if isinstance(value, str):
        if _SECRET_TEXT.search(value):
            raise VisualReportError("credential-leak", "visual reports may not contain credentials", path=path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _scan_credentials(item, path=f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            _scan_credentials(key, path=f"{path}.<key>")
            _scan_credentials(item, path=f"{path}.{key}")


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
    specs_list = _root_expected_state_specs(root, course)
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
        if standard != {key: item for key, item in VIEWPORT_PROFILE_MANIFEST["desktop"].items() if key != "annotationPanelCollapsed"} or constrained != {key: item for key, item in VIEWPORT_PROFILE_MANIFEST["desktop-sidebar"].items() if key != "annotationPanelCollapsed"}:
            raise VisualReportError("viewport-profile-mismatch", f"sidebar profile must prove a narrower student content width: {state_id}", path="states")
    blockers = [finding for state in normalized for finding in state["findings"] if finding["severity"] == "blocker"]
    blocker_count = payload.get("blockerCount")
    if isinstance(blocker_count, bool) or not isinstance(blocker_count, int) or blocker_count != len(blockers):
        raise VisualReportError("blocker-count-mismatch", "blockerCount must exactly match visual findings", path="blockerCount")
    if blocker_count:
        raise VisualReportError("visual-check-blocked", "visual report contains one or more unresolved blockers", path="blockerCount")
    report = {
        "schemaVersion": VISUAL_REPORT_VERSION,
        "artifactHashes": dict(hashes),
        "captureAvailable": True,
        "repairRound": repair_round,
        "capturedAt": payload["capturedAt"].strip(),
        "states": normalized,
        "blockerCount": 0,
    }
    _scan_credentials(report)
    return report


def _commit_document(report: Mapping[str, object]) -> dict:
    return {**dict(report), "reportHash": canonical_json_hash(report)}


def _visual_context_hash(hashes: Mapping[str, str]) -> str:
    """Identify one immutable artifact + renderer + viewport inspection context."""
    return canonical_json_hash({"artifactHashes": {field: hashes[field] for field in _HASH_FIELDS}})


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


def _empty_attempt_ledger() -> dict:
    return {"schemaVersion": VISUAL_REPORT_VERSION, "contexts": {}}


def _validate_attempt_ledger(document: object) -> dict:
    if not isinstance(document, dict) or set(document) != _LEDGER_FIELDS:
        raise VisualReportError("invalid-attempt-ledger", "visual repair attempt ledger has an unsupported shape", path=VISUAL_ATTEMPT_LEDGER_RELATIVE_PATH)
    body = {"schemaVersion": document.get("schemaVersion"), "contexts": document.get("contexts")}
    if body["schemaVersion"] != VISUAL_REPORT_VERSION or not isinstance(body["contexts"], dict):
        raise VisualReportError("invalid-attempt-ledger", "visual repair attempt ledger must use schemaVersion 1.0", path=VISUAL_ATTEMPT_LEDGER_RELATIVE_PATH)
    if not isinstance(document.get("ledgerHash"), str) or document["ledgerHash"] != canonical_json_hash(body):
        raise VisualReportError("attempt-ledger-mismatch", "visual repair attempt ledger changed outside its atomic commit", path=VISUAL_ATTEMPT_LEDGER_RELATIVE_PATH)
    contexts: Dict[str, dict] = {}
    for context_hash, raw in body["contexts"].items():
        context_path = f"{VISUAL_ATTEMPT_LEDGER_RELATIVE_PATH}.contexts.{context_hash}"
        if not isinstance(context_hash, str) or not _SHA256.fullmatch(context_hash) or not isinstance(raw, dict) or set(raw) != _LEDGER_CONTEXT_FIELDS:
            raise VisualReportError("invalid-attempt-ledger", "visual repair context is malformed", path=context_path)
        next_round = raw.get("nextRepairRound")
        failed = raw.get("failedAttempts")
        success_hash = raw.get("successfulReportHash")
        if (
            isinstance(next_round, bool)
            or not isinstance(next_round, int)
            or not 0 <= next_round <= MAX_AUTONOMOUS_REPAIR_ROUNDS + 1
            or not isinstance(failed, list)
            or len(failed) > MAX_AUTONOMOUS_REPAIR_ROUNDS + 1
            or (success_hash is not None and (not isinstance(success_hash, str) or not _SHA256.fullmatch(success_hash)))
        ):
            raise VisualReportError("invalid-attempt-ledger", "visual repair context counters are invalid", path=context_path)
        normalized_failed: List[dict] = []
        for index, attempt in enumerate(failed):
            attempt_path = f"{context_path}.failedAttempts[{index}]"
            if not isinstance(attempt, dict) or set(attempt) != _FAILED_ATTEMPT_FIELDS:
                raise VisualReportError("invalid-attempt-ledger", "visual repair failure entry is malformed", path=attempt_path)
            if (
                attempt.get("repairRound") != index
                or not isinstance(attempt.get("payloadHash"), str)
                or not _SHA256.fullmatch(attempt["payloadHash"])
                or not _nonempty(attempt.get("errorCode"), maximum=160)
                or not _nonempty(attempt.get("errorPath"), maximum=800)
                or not isinstance(attempt.get("blockerCodes"), list)
                or not all(isinstance(code, str) for code in attempt["blockerCodes"])
                or attempt["blockerCodes"] != sorted(set(attempt["blockerCodes"]))
                or any(code not in VISUAL_BLOCKER_CODES for code in attempt["blockerCodes"])
                or not _nonempty(attempt.get("capturedAt"), maximum=100)
            ):
                raise VisualReportError("invalid-attempt-ledger", "visual repair failure sequence is invalid", path=attempt_path)
            normalized_failed.append(dict(attempt))
        expected_next = len(normalized_failed) + (1 if success_hash is not None else 0)
        if next_round != expected_next:
            raise VisualReportError("invalid-attempt-ledger", "visual repair attempt counter is not monotonic", path=context_path)
        contexts[context_hash] = {
            "nextRepairRound": next_round,
            "failedAttempts": normalized_failed,
            "successfulReportHash": success_hash,
        }
    normalized = {"schemaVersion": VISUAL_REPORT_VERSION, "contexts": contexts}
    _scan_credentials(normalized, path="$attemptLedger")
    return normalized


def _read_attempt_ledger(root: Path) -> dict:
    document = _safe_json(root, VISUAL_ATTEMPT_LEDGER_RELATIVE_PATH, required=False)
    return _empty_attempt_ledger() if document is None else _validate_attempt_ledger(document)


def _commit_attempt_ledger(ledger: Mapping[str, object]) -> dict:
    body = {"schemaVersion": ledger["schemaVersion"], "contexts": ledger["contexts"]}
    _scan_credentials(body, path="$attemptLedger")
    return {**body, "ledgerHash": canonical_json_hash(body)}


def _write_all(descriptor: int, content: bytes) -> None:
    offset = 0
    while offset < len(content):
        written = os.write(descriptor, content[offset:])
        if not isinstance(written, int) or written <= 0:
            raise OSError("short visual report write")
        offset += written


def _write_course_work_document(root: Path, relative: str, document: Mapping[str, object]) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    directory_flags = flags | getattr(os, "O_DIRECTORY", 0)
    root_fd = os.open(root, directory_flags)
    work_fd = None
    temporary = None
    try:
        work_fd = os.open(".course-work", directory_flags, dir_fd=root_fd)
        name = Path(relative).name
        try:
            existing = os.stat(name, dir_fd=work_fd, follow_symlinks=False)
            if stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode):
                raise VisualReportError("symlink-evidence", "visual evidence destination must be a regular file", path=relative)
            mode = stat.S_IMODE(existing.st_mode)
        except FileNotFoundError:
            mode = 0o644
        temporary = f".{name}.{secrets.token_hex(16)}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), mode, dir_fd=work_fd)
        try:
            _write_all(descriptor, dump_json(document).encode("utf-8"))
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


def _write_report(root: Path, report: Mapping[str, object]) -> None:
    _write_course_work_document(root, VISUAL_REPORT_RELATIVE_PATH, _commit_document(report))


def _write_attempt_ledger(root: Path, ledger: Mapping[str, object]) -> None:
    _write_course_work_document(root, VISUAL_ATTEMPT_LEDGER_RELATIVE_PATH, _commit_attempt_ledger(ledger))


def _candidate_round(payload: object) -> int:
    value = payload.get("repairRound") if isinstance(payload, dict) else None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise VisualReportError("invalid-repair-round", "repairRound must be a nonnegative integer", path="repairRound")
    if value > MAX_AUTONOMOUS_REPAIR_ROUNDS:
        raise VisualReportError("repair-limit-exceeded", "a fourth autonomous visual repair attempt is forbidden", path="repairRound")
    return value


def _candidate_hash(payload: object) -> str | None:
    try:
        return canonical_json_hash(payload)
    except (TypeError, ValueError):
        return None


def _failure_timestamp(payload: object) -> str:
    value = payload.get("capturedAt") if isinstance(payload, dict) else None
    if _nonempty(value, maximum=100) and not _SECRET_TEXT.search(value):
        return value.strip()
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _failure_path(value: object) -> str:
    if not _nonempty(value, maximum=800) or _SECRET_TEXT.search(value):
        return "$candidate"
    return value.strip()


def _failed_blocker_codes(payload: object, error_code: str) -> List[str]:
    result = {error_code} if error_code in VISUAL_BLOCKER_CODES else set()
    states = payload.get("states") if isinstance(payload, dict) else None
    for state in states if isinstance(states, list) else []:
        findings = state.get("findings") if isinstance(state, dict) else None
        for finding in findings if isinstance(findings, list) else []:
            code = finding.get("code") if isinstance(finding, dict) else None
            if isinstance(code, str) and code.strip().lower() in VISUAL_BLOCKER_CODES:
                result.add(code.strip().lower())
    return sorted(result)


def _validate_normalized_report(report: dict, *, hashes: Mapping[str, str], plan: Mapping[str, object], course: Mapping[str, object], root: Path) -> None:
    """Prove normalization is closed and does not create a looser commit shape."""
    repeated = _validate_payload(report, hashes=hashes, plan=plan, course=course, root=root)
    if repeated != report:
        raise VisualReportError("noncanonical-report", "normalized visual report is not stable under revalidation")


def record_visual_report(root: Path, payload: dict) -> dict:
    """Validate and atomically commit current renderer-backed visual evidence."""
    root = _safe_root(root)
    try:
        with _plan_guard(root, timeout_seconds=30):
            hashes, plan, course = _current_context_at(root)
            context_hash = _visual_context_hash(hashes)
            ledger = _read_attempt_ledger(root)
            context = ledger["contexts"].setdefault(
                context_hash,
                {"nextRepairRound": 0, "failedAttempts": [], "successfulReportHash": None},
            )
            repair_round = _candidate_round(payload)
            payload_hash = _candidate_hash(payload)
            if context["successfulReportHash"] is not None:
                report = _validate_payload(payload, hashes=hashes, plan=plan, course=course, root=root)
                _validate_normalized_report(report, hashes=hashes, plan=plan, course=course, root=root)
                if canonical_json_hash(report) != context["successfulReportHash"]:
                    raise VisualReportError("visual-context-complete", "this artifact/profile context already has successful visual evidence", path="repairRound")
                _write_report(root, report)
                return report
            if context["nextRepairRound"] > MAX_AUTONOMOUS_REPAIR_ROUNDS:
                raise VisualReportError("repair-limit-exceeded", "a fourth autonomous visual repair attempt is forbidden", path="repairRound")
            if repair_round != context["nextRepairRound"]:
                repeated = next(
                    (
                        item
                        for item in context["failedAttempts"]
                        if item["repairRound"] == repair_round and payload_hash is not None and item["payloadHash"] == payload_hash
                    ),
                    None,
                )
                if repeated is not None:
                    raise VisualReportError("repeat-failed-attempt", "this failed visual candidate was already counted", path="repairRound")
                raise VisualReportError("repair-round-mismatch", "repairRound must match the tool-owned monotonic attempt counter", path="repairRound")
            try:
                report = _validate_payload(payload, hashes=hashes, plan=plan, course=course, root=root)
                _validate_normalized_report(report, hashes=hashes, plan=plan, course=course, root=root)
            except VisualReportError as exc:
                if payload_hash is not None:
                    context["failedAttempts"].append(
                        {
                            "repairRound": repair_round,
                            "payloadHash": payload_hash,
                            "errorCode": exc.code,
                            "errorPath": _failure_path(exc.path),
                            "blockerCodes": _failed_blocker_codes(payload, exc.code),
                            "capturedAt": _failure_timestamp(payload),
                        }
                    )
                    context["nextRepairRound"] = repair_round + 1
                    _write_attempt_ledger(root, ledger)
                raise
            _write_report(root, report)
            context["successfulReportHash"] = canonical_json_hash(report)
            context["nextRepairRound"] = repair_round + 1
            _write_attempt_ledger(root, ledger)
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
    _validate_normalized_report(report, hashes=hashes, plan=plan, course=course, root=root)
    ledger = _read_attempt_ledger(root)
    context = ledger["contexts"].get(_visual_context_hash(hashes))
    if not isinstance(context, dict) or context.get("successfulReportHash") != canonical_json_hash(report):
        raise VisualReportError("visual-attempt-ledger-stale", "visual report is not bound to a successful tool-owned repair attempt", path=VISUAL_ATTEMPT_LEDGER_RELATIVE_PATH)
    return {"prepreviewVisualHash": canonical_json_hash(report), **hashes}
