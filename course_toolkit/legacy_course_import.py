import copy
import hashlib
import json
import math
from typing import Dict, List, Optional, Sequence, Tuple

from course_toolkit.blueprint import BlueprintValidationError, validate_blueprint_authoring


IMPORT_HEURISTIC_VERSION = "1.0"


class LegacyImportError(ValueError):
    pass


def _canonical_hash(data: object) -> str:
    encoded = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _completion(block: dict) -> Optional[dict]:
    block_type = block["type"]
    legacy = block.get("completion") or {}
    rule = legacy.get("rule")
    attempts = legacy.get("maxAttempts")
    if block_type == "video":
        if block.get("interaction") and block.get("blocking"):
            return {"rule": "video-ended-and-interactions-completed"}
        if rule == "video-ended" or block.get("blocking"):
            return {"rule": "video-ended"}
        return None
    if block_type == "interactiveHtml":
        if rule == "interaction-complete" or block.get("blocking"):
            return {"rule": "interaction-complete"}
        return None
    if block_type not in {"fillBlank", "singleChoice"}:
        return None
    if rule == "submit-any":
        return {"rule": "submit-any"}
    if rule == "submit-correct":
        if isinstance(attempts, int) and not isinstance(attempts, bool) and attempts > 0:
            return {
                "rule": "submit-correct-or-exhausted",
                "maxAttempts": attempts,
            }
        return {"rule": "submit-correct"}
    assessment_mode = (block.get("assessment") or {}).get("mode")
    if assessment_mode in {"reflection", "survey"}:
        return {"rule": "submit-any"}
    return {"rule": "submit-correct-or-exhausted", "maxAttempts": 3}


def _copy_assessment(block: dict) -> dict:
    assessment = block.get("assessment")
    if not isinstance(assessment, dict):
        raise LegacyImportError(f"Block {block.get('id')} has no assessment")
    mode = assessment.get("mode")
    if block["type"] == "fillBlank":
        allowed = {
            "graded": (
                "mode",
                "acceptedAnswers",
                "caseSensitive",
                "correctFeedback",
                "incorrectFeedback",
            ),
            "reflection": ("mode", "rubric"),
        }
    else:
        allowed = {
            "graded": (
                "mode",
                "correctOptionId",
                "correctFeedback",
                "incorrectFeedback",
            ),
            "survey": ("mode",),
        }
    if mode not in allowed:
        raise LegacyImportError(
            f"Block {block.get('id')} has unsupported assessment mode: {mode}"
        )
    return {
        field: copy.deepcopy(assessment[field])
        for field in allowed[mode]
        if field in assessment
    }


def _convert_block(block: dict) -> Tuple[dict, bool]:
    block_id = block.get("id")
    block_type = block.get("type")
    if not isinstance(block_id, str) or not isinstance(block_type, str):
        raise LegacyImportError("Every legacy block needs id and type")
    converted = {"id": block_id, "type": block_type}
    omitted_video_document = False
    if block_type == "text":
        converted["content"] = block.get("content")
    elif block_type == "images":
        items = block.get("items")
        if not isinstance(items, list) or not items:
            raise LegacyImportError(f"Images block {block_id} has no items")
        converted["presentation"] = (
            "single" if len(items) == 1 else "side-by-side" if len(items) == 2 else "gallery"
        )
        converted["items"] = []
        for index, item in enumerate(items):
            converted_item = {
                "id": f"{block_id}-item-{index + 1}",
                "source": item.get("source"),
                "alt": item.get("alt"),
            }
            if isinstance(item.get("caption"), str):
                converted_item["caption"] = item["caption"]
            converted["items"].append(converted_item)
    elif block_type == "pdf":
        converted["title"] = block.get("title")
        converted["source"] = block.get("source")
        if isinstance(block.get("initialPage"), int):
            converted["initialPage"] = block["initialPage"]
    elif block_type == "video":
        converted["source"] = block.get("source")
        for field in ("poster", "captions", "durationSeconds"):
            if field in block:
                converted[field] = copy.deepcopy(block[field])
        interaction = block.get("interaction")
        if isinstance(interaction, dict) and isinstance(interaction.get("data"), str):
            converted["interaction"] = {"source": interaction["data"]}
            omitted_video_document = isinstance(interaction.get("document"), str)
        completion = _completion(block)
        if completion is not None:
            converted["completion"] = completion
    elif block_type == "interactiveHtml":
        converted["source"] = block.get("source")
        converted["protocolVersion"] = "1.0"
        converted["aspectRatio"] = "4:3"
        completion = _completion(block)
        if completion is not None:
            converted["completion"] = completion
    elif block_type == "fillBlank":
        converted["prompt"] = block.get("prompt")
        if isinstance(block.get("placeholder"), str):
            converted["placeholder"] = block["placeholder"]
        converted["assessment"] = _copy_assessment(block)
        converted["completion"] = _completion(block)
    elif block_type == "singleChoice":
        converted["prompt"] = block.get("prompt")
        converted["options"] = copy.deepcopy(block.get("options"))
        converted["assessment"] = _copy_assessment(block)
        converted["completion"] = _completion(block)
    else:
        raise LegacyImportError(f"Unsupported legacy block type: {block_type}")
    return converted, omitted_video_document


def _block_seconds(block: dict) -> int:
    block_type = block["type"]
    if block_type == "text":
        characters = len(block.get("content") or "")
        return max(30, math.ceil(characters / 250 * 60))
    if block_type == "images":
        return max(45, 20 * len(block.get("items") or []))
    if block_type == "pdf":
        return 90
    if block_type == "video":
        duration = block.get("durationSeconds")
        return math.ceil(duration) if isinstance(duration, (int, float)) and duration > 0 else 120
    if block_type == "interactiveHtml":
        return 120
    if block_type == "fillBlank":
        return 60
    if block_type == "singleChoice":
        return 45
    raise LegacyImportError(f"Cannot estimate block type: {block_type}")


def _workflow(blocks: Sequence[dict], legacy_blocks: Sequence[dict]) -> dict:
    block_ids = [block["id"] for block in blocks]
    blocking = [
        block for block in legacy_blocks if block.get("blocking") is True
    ]
    initial_state = {
        "visibleBlockIds": block_ids,
        "enabledBlockIds": block_ids,
    }
    if not blocking:
        return {
            "version": "1.0",
            "initialStepId": "wait-for-continue",
            "initialState": initial_state,
            "steps": [
                {
                    "id": "wait-for-continue",
                    "enterActions": [],
                    "transitions": [
                        {"on": {"type": "student.continue"}, "to": "finish"}
                    ],
                },
                {
                    "id": "finish",
                    "enterActions": [{"type": "completeSlice"}],
                    "transitions": [],
                },
            ],
        }
    steps = []
    for index, block in enumerate(blocking):
        block_id = block["id"]
        if block["type"] == "interactiveHtml":
            event_type = "interaction.completed"
        else:
            event_type = "block.completed"
        next_step = (
            f"wait-{blocking[index + 1]['id']}"
            if index + 1 < len(blocking)
            else "finish"
        )
        steps.append(
            {
                "id": f"wait-{block_id}",
                "enterActions": [{"type": "focus", "target": {"blockId": block_id}}],
                "transitions": [
                    {
                        "on": {"type": event_type, "sourceId": block_id},
                        "to": next_step,
                    }
                ],
            }
        )
    steps.append(
        {
            "id": "finish",
            "enterActions": [{"type": "clearFocus"}, {"type": "completeSlice"}],
            "transitions": [],
        }
    )
    return {
        "version": "1.0",
        "initialStepId": steps[0]["id"],
        "initialState": initial_state,
        "steps": steps,
    }


def _storyboard_pieces(storyboard: dict) -> Dict[str, dict]:
    pieces = {}
    for part in storyboard.get("parts", []):
        for piece in part.get("pieces", []):
            if isinstance(piece, dict) and isinstance(piece.get("id"), str):
                pieces[piece["id"]] = piece
    return pieces


def _alignment(storyboard: dict, objective_ids: Sequence[str]) -> Dict[str, dict]:
    values = storyboard.get("courseFrame", {}).get("objectiveAlignment")
    if not isinstance(values, list):
        raise LegacyImportError("Storyboard courseFrame.objectiveAlignment is required")
    mapping = {
        item.get("objectiveId"): item
        for item in values
        if isinstance(item, dict) and isinstance(item.get("objectiveId"), str)
    }
    missing = [objective_id for objective_id in objective_ids if objective_id not in mapping]
    if missing:
        raise LegacyImportError(
            "Storyboard objectiveAlignment is missing: " + ", ".join(missing)
        )
    for objective_id in objective_ids:
        item = mapping[objective_id]
        if not item.get("partIds") or not item.get("evidenceBlockIds"):
            raise LegacyImportError(
                f"Storyboard objectiveAlignment for {objective_id} needs partIds and evidenceBlockIds"
            )
    return mapping


def _provenance_record(
    target_id: str,
    source_ids: Sequence[str],
    *,
    status: str = "source-backed",
) -> dict:
    return {
        "targetId": target_id,
        "sourceIds": list(dict.fromkeys(source_ids)),
        "decisionIds": [],
        "status": status,
    }


def import_legacy_course(legacy: dict, storyboard: dict) -> dict:
    if legacy.get("schemaVersion") != "1.1":
        raise LegacyImportError("Only schemaVersion 1.1 can be imported")
    course = legacy.get("course")
    if not isinstance(course, dict):
        raise LegacyImportError("Legacy course object is required")
    introduction = course.get("introduction") or {}
    conclusion = course.get("conclusion") or {}
    legacy_objectives = introduction.get("objectives") or []
    objective_ids = [objective.get("id") for objective in legacy_objectives]
    alignments = _alignment(storyboard, objective_ids)
    piece_records = _storyboard_pieces(storyboard)
    all_legacy_block_ids = {
        block.get("id")
        for part in course.get("parts", [])
        for piece in part.get("pieces", [])
        for block in piece.get("blocks", [])
        if isinstance(block, dict)
    }
    for objective_id in objective_ids:
        missing_evidence = [
            block_id
            for block_id in alignments[objective_id]["evidenceBlockIds"]
            if block_id not in all_legacy_block_ids
        ]
        if missing_evidence:
            raise LegacyImportError(
                f"objectiveAlignment for {objective_id} references missing evidence: "
                + ", ".join(missing_evidence)
            )

    blueprint_course = {
        "id": course.get("id"),
        "title": course.get("title"),
        "language": course.get("language"),
        "estimatedMinutes": 1,
        "objectives": [
            {
                "id": objective.get("id"),
                "text": objective.get("text"),
                "evidenceBlockIds": copy.deepcopy(
                    alignments[objective.get("id")]["evidenceBlockIds"]
                ),
            }
            for objective in legacy_objectives
        ],
        "opening": {
            "learningPreview": copy.deepcopy(introduction.get("keyPoints") or []),
            "personalization": {"enabled": False, "allowedSignals": []},
            "fallback": {"text": introduction.get("overview")},
        },
        "parts": [],
        "closing": {
            "preparedSummary": conclusion.get("summary"),
            "takeaways": copy.deepcopy(conclusion.get("takeaways") or []),
            "transferApplications": copy.deepcopy(
                conclusion.get("transferApplications") or []
            ),
            "personalization": {"enabled": False, "allowedSignals": []},
            "fallback": {"text": conclusion.get("summary")},
        },
    }
    provenance = []
    course_sources = storyboard.get("courseFrame", {}).get("sourceIds") or []
    for target_id in ("course", "opening", "closing"):
        provenance.append(_provenance_record(target_id, course_sources))
    for objective_id in objective_ids:
        provenance.append(_provenance_record(f"objective:{objective_id}", course_sources))

    slice_target_ids = []
    part_target_ids = []
    video_omission_targets = []
    total_seconds = 0
    for legacy_part in course.get("parts", []):
        part_id = legacy_part.get("id")
        part_objectives = [
            objective_id
            for objective_id in objective_ids
            if part_id in alignments[objective_id]["partIds"]
        ]
        converted_part = {
            "id": part_id,
            "title": legacy_part.get("title"),
            "objectiveIds": part_objectives,
            "slices": [],
        }
        part_target_ids.append(f"part:{part_id}")
        part_sources = []
        for legacy_piece in legacy_part.get("pieces", []):
            piece_id = legacy_piece.get("id")
            piece_record = piece_records.get(piece_id)
            if piece_record is None:
                raise LegacyImportError(f"Storyboard is missing Piece: {piece_id}")
            source_ids = piece_record.get("sourceIds") or []
            part_sources.extend(source_ids)
            legacy_blocks = legacy_piece.get("blocks") or []
            converted_blocks = []
            for legacy_block in legacy_blocks:
                converted_block, omitted_document = _convert_block(legacy_block)
                converted_blocks.append(converted_block)
                target_id = f"block:{converted_block['id']}"
                provenance.append(_provenance_record(target_id, source_ids))
                if omitted_document:
                    video_omission_targets.append(target_id)
            estimated_seconds = max(
                30,
                sum(_block_seconds(block) for block in converted_blocks),
            )
            total_seconds += estimated_seconds
            converted_slice = {
                "id": piece_id,
                "title": legacy_piece.get("title"),
                "objectiveIds": part_objectives,
                "estimatedSeconds": estimated_seconds,
                "blocks": converted_blocks,
                "layout": {
                    "preset": "full",
                    "slots": [
                        {
                            "id": "main",
                            "blockIds": [block["id"] for block in converted_blocks],
                        }
                    ],
                },
                "narrations": [],
                "workflow": _workflow(converted_blocks, legacy_blocks),
                "navigation": {
                    "previous": "allowed",
                    "manualNext": "after-completion",
                    "autoNext": False,
                    "revisit": "restore-completed-state",
                },
            }
            converted_part["slices"].append(converted_slice)
            slice_target_id = f"slice:{piece_id}"
            slice_target_ids.append(slice_target_id)
            provenance.append(_provenance_record(slice_target_id, source_ids))
        blueprint_course["parts"].append(converted_part)
        provenance.append(
            _provenance_record(f"part:{part_id}", list(dict.fromkeys(part_sources)))
        )
    blueprint_course["estimatedMinutes"] = max(1, math.ceil(total_seconds / 60))

    assumptions = [
        {
            "id": "layout-default",
            "description": "Each legacy Piece uses a full/main layout until the teacher reviews one-screen composition.",
            "targetIds": slice_target_ids,
        },
        {
            "id": "workflow-from-blocking",
            "description": "Legacy blocking flags become a source-order Slice workflow.",
            "targetIds": slice_target_ids,
        },
        {
            "id": "estimated-time",
            "description": f"Estimated seconds use migration heuristic {IMPORT_HEURISTIC_VERSION}.",
            "targetIds": ["course", *slice_target_ids],
        },
        {
            "id": "personalization-disabled",
            "description": "Opening and closing personalization remain disabled until explicitly designed.",
            "targetIds": ["opening", "closing"],
        },
        {
            "id": "objective-slice-mapping",
            "description": "Each Slice inherits the objective IDs aligned to its legacy Part.",
            "targetIds": [*part_target_ids, *slice_target_ids],
        },
    ]
    if video_omission_targets:
        assumptions.append(
            {
                "id": "video-authoring-document-omitted",
                "description": "Legacy video authoring Markdown remains in authoring records and is not a runtime asset.",
                "targetIds": video_omission_targets,
            }
        )
    blueprint = {
        "schemaVersion": "1.0",
        "targetContractVersion": "2.0",
        "approval": {"teacherConfirmed": False, "decisionIds": []},
        "course": blueprint_course,
        "provenance": provenance,
        "migration": {
            "sourceSchemaVersion": "1.1",
            "sourceHash": _canonical_hash(legacy),
            "assumptions": assumptions,
        },
    }
    issues = validate_blueprint_authoring(blueprint, require_approval=False)
    if issues:
        raise LegacyImportError(
            "Imported Blueprint is invalid: "
            + "; ".join(f"{issue.path} {issue.message}" for issue in issues)
        )
    return blueprint
