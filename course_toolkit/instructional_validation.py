"""Deterministic checks that bind a compiled course to its approved page plan.

This module intentionally checks identities, placement, and runtime mechanics
only.  Whether an image *semantically* supports a claim is recorded by the
separate instructional audit, rather than guessed from text here.
"""

from __future__ import annotations

import re
from collections import deque
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Set, Tuple

from .course_asset_index import iter_asset_references
from .errors import ValidationIssue
from .instructional_bindings import (
    _course_destination_pointers,
    _g5_issue,
    _source_map_matches,
    collect_course_destinations,
)
from .instructional_plan import validate_instructional_plan
from .jsonio import load_json


REFERENCE_TEXT = re.compile(
    r"参考(?:上面|上述|前面)?的?(?:原文|材料|资料|图表|图片|证据)|"
    r"(?:原文|材料|图表|图片|证据)(?:如上|如下|见上)|"
    r"\b(?:the\s+)?(?:original|source|material|figure|chart|image)\s+(?:above|below)\b",
    re.IGNORECASE,
)
ASSESSMENT_TYPES = frozenset({"singleChoice", "fillBlank"})
COMPLETION_EVENT_TYPES = {
    "video": frozenset({"block.completed"}),
    "interactiveHtml": frozenset({"interaction.completed", "block.completed"}),
    "singleChoice": frozenset(
        {"answer.correct", "answer.attemptsExhausted", "answer.submitted", "block.completed"}
    ),
    "fillBlank": frozenset(
        {"answer.correct", "answer.attemptsExhausted", "answer.submitted", "block.completed"}
    ),
}

# Mirrors packages/course-contract/src/validate/workflow.ts's EVENT_PRODUCERS,
# with the renderer-only exception for ``pdf.pageChanged``: the pinned PDF
# renderer cannot observe changes inside its native iframe.  This is purposely
# a capability table, not a learner-answer simulation.  A transition is
# explored only when a renderer could emit its event in the current state.
EVENT_PRODUCERS = {
    "narration.ended": "narration",
    "video.started": "block",
    "video.paused": "block",
    "video.ended": "block",
    "video.interaction.shown": "block",
    "video.interaction.completed": "block",
    "pdf.opened": "block",
    "pdf.pageChanged": "unsupported",
    "interaction.completed": "block",
    "answer.submitted": "block",
    "answer.correct": "block",
    "answer.incorrect": "block",
    "answer.attemptsExhausted": "block",
    "block.completed": "block",
    "student.continue": "none",
    "timer.elapsed": "timer",
}
ONE_SHOT_BLOCK_EVENTS = frozenset(
    {
        "answer.submitted",
        "answer.correct",
        "answer.incorrect",
        "answer.attemptsExhausted",
        "block.completed",
        "interaction.completed",
        "video.interaction.completed",
    }
)


def _issue(path: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(path, code, message)


def _course_payload(document: object) -> dict:
    if isinstance(document, dict) and isinstance(document.get("course"), dict):
        return document["course"]
    return {}


def _items(value: object) -> list:
    return value if isinstance(value, list) else []


def _target_path(part_id: str, slice_id: str, block_id: str | None = None) -> str:
    path = f"part:{part_id}/slice:{slice_id}"
    return f"{path}/block:{block_id}" if block_id else path


def _slice_entries(course: dict) -> Iterable[Tuple[str, str, dict]]:
    for part in _items(_course_payload(course).get("parts")):
        if not isinstance(part, dict) or not isinstance(part.get("id"), str):
            continue
        for slice_data in _items(part.get("slices")):
            if isinstance(slice_data, dict) and isinstance(slice_data.get("id"), str):
                yield part["id"], slice_data["id"], slice_data


def _block_index(course: dict) -> Dict[str, Tuple[str, str, dict]]:
    indexed: Dict[str, Tuple[str, str, dict]] = {}
    for part_id, slice_id, slice_data in _slice_entries(course):
        for block in _items(slice_data.get("blocks")):
            if isinstance(block, dict) and isinstance(block.get("id"), str):
                indexed.setdefault(block["id"], (part_id, slice_id, block))
    return indexed


def _safe_load(root: Path, relative: str) -> Tuple[object | None, ValidationIssue | None]:
    path = root / relative
    if not path.is_file() or path.is_symlink():
        return None, _issue(relative, "plan-evidence-missing", "required instructional evidence is missing")
    try:
        return load_json(path), None
    except ValueError:
        return None, _issue(relative, "plan-evidence-invalid", "instructional evidence is not valid JSON")


def _coverage_index(coverage: object) -> Dict[str, dict]:
    if not isinstance(coverage, dict):
        return {}
    return {
        item["sourceId"]: item
        for item in _items(coverage.get("items"))
        if isinstance(item, dict) and isinstance(item.get("sourceId"), str)
    }


def _plan_slices(plan: object) -> Iterable[Tuple[str, str, dict]]:
    if not isinstance(plan, dict):
        return
    for part in _items(plan.get("parts")):
        if not isinstance(part, dict) or not isinstance(part.get("partId"), str):
            continue
        for slice_data in _items(part.get("slices")):
            if isinstance(slice_data, dict) and isinstance(slice_data.get("sliceId"), str):
                yield part["partId"], slice_data["sliceId"], slice_data


def _asset_sources(course: dict) -> Dict[Tuple[str, str, str], Set[str]]:
    result: Dict[Tuple[str, str, str], Set[str]] = {}
    for reference in iter_asset_references(course):
        if all(isinstance(value, str) and value for value in (reference.part_id, reference.slice_id, reference.block_id)):
            result.setdefault((reference.part_id, reference.slice_id, reference.block_id), set()).add(reference.source)
    return result


def _binding_supports(binding: dict, target_id: str) -> bool:
    supports = binding.get("supportsIds", [])
    return isinstance(supports, list) and target_id in supports


def _resolve_target(
    target: object,
    *,
    part_id: str,
    slice_id: str,
    blocks: Mapping[str, Tuple[str, str, dict]],
) -> Tuple[str | None, ValidationIssue | None]:
    if not isinstance(target, str) or ":" not in target:
        return None, _issue(_target_path(part_id, slice_id), "plan-target-invalid", "plan target must use question:<blockId> or claim:<blockId>")
    target_kind, block_id = target.split(":", 1)
    entry = blocks.get(block_id)
    if target_kind not in {"question", "claim"} or entry is None:
        return None, _issue(_target_path(part_id, slice_id, block_id), "plan-target-unresolved", "plan target does not resolve to a CourseDefinition Block")
    actual_part, actual_slice, block = entry
    if (actual_part, actual_slice) != (part_id, slice_id):
        return None, _issue(_target_path(part_id, slice_id, block_id), "plan-target-wrong-slice", "plan target must resolve inside the planned Slice")
    if target_kind == "question" and block.get("type") not in ASSESSMENT_TYPES:
        return None, _issue(_target_path(part_id, slice_id, block_id), "plan-target-kind-mismatch", "question target must resolve to an answerable Block")
    if target_kind == "claim" and block.get("type") != "text":
        return None, _issue(_target_path(part_id, slice_id, block_id), "plan-target-kind-mismatch", "claim target must resolve to a text Block")
    return block_id, None


def _has_reference_surface(slice_data: dict, source_file: object) -> bool:
    if not isinstance(source_file, str):
        return False
    for block in _items(slice_data.get("blocks")):
        if not isinstance(block, dict):
            continue
        if block.get("source") == source_file and block.get("type") in {"pdf", "images", "video", "interactiveHtml"}:
            return True
        if block.get("type") == "images":
            if any(isinstance(item, dict) and item.get("source") == source_file for item in _items(block.get("items"))):
                return True
    return False


def _block_can_emit_event(block: dict, event_type: object, visible: Set[str], enabled: Set[str]) -> bool:
    """Whether the pinned renderer can emit ``event_type`` for this Block now."""
    block_id = block.get("id")
    if not isinstance(block_id, str) or block_id not in visible:
        return False
    block_type = block.get("type")
    if block_type in ASSESSMENT_TYPES:
        if block_id not in enabled:
            return False
        assessment = block.get("assessment") if isinstance(block.get("assessment"), dict) else {}
        mode = assessment.get("mode")
        if event_type == "answer.submitted":
            return mode in {"graded", "survey", "reflection"}
        if event_type in {"answer.correct", "answer.incorrect"}:
            return mode == "graded"
        if event_type == "answer.attemptsExhausted":
            completion = block.get("completion") if isinstance(block.get("completion"), dict) else {}
            return mode == "graded" and completion.get("rule") == "submit-correct-or-exhausted"
        return event_type == "block.completed" and isinstance(block.get("completion"), dict)
    if block_type == "interactiveHtml":
        if block_id not in enabled:
            return False
        completion = block.get("completion") if isinstance(block.get("completion"), dict) else {}
        if event_type == "interaction.completed":
            return True
        return event_type == "block.completed" and completion.get("rule") == "interaction-complete"
    if block_type == "video":
        if event_type in {"video.started", "video.paused", "video.ended"}:
            return True
        if event_type in {"video.interaction.shown", "video.interaction.completed"}:
            return isinstance(block.get("interaction"), dict)
        return event_type == "block.completed" and isinstance(block.get("completion"), dict)
    return block_type == "pdf" and event_type == "pdf.opened"


def _matcher_matches(on: object, event: Tuple[str, str]) -> bool:
    return isinstance(on, dict) and on.get("type") == event[1] and (on.get("sourceId") is None or on.get("sourceId") == event[0])


def _assessment_cascades(block: dict, attempt: int) -> List[Tuple[Tuple[Tuple[str, str], ...], bool]]:
    """Renderer event tails after one accepted assessment submission."""
    block_id = block["id"]
    assessment = block.get("assessment") if isinstance(block.get("assessment"), dict) else {}
    mode = assessment.get("mode")
    if mode in {"survey", "reflection"}:
        return [(((block_id, "block.completed"),), True)]
    if mode != "graded":
        return []
    completion = block.get("completion") if isinstance(block.get("completion"), dict) else {}
    rule = completion.get("rule")
    # Correctness is learner-controlled, so preserve both renderer-real paths.
    cascades = [(((block_id, "answer.correct"), (block_id, "block.completed")), True)]
    if rule == "submit-any":
        cascades.append((((block_id, "answer.incorrect"), (block_id, "block.completed")), True))
    elif rule == "submit-correct":
        cascades.append((((block_id, "answer.incorrect"),), False))
    elif rule == "submit-correct-or-exhausted":
        maximum = completion.get("maxAttempts")
        if isinstance(maximum, int) and attempt >= maximum:
            cascades.append((((block_id, "answer.attemptsExhausted"), (block_id, "block.completed")), True))
        else:
            cascades.append((((block_id, "answer.incorrect"),), False))
    return cascades


def _external_event_updates(
    transition: object,
    *,
    blocks: Mapping[str, dict],
    visible: Set[str],
    enabled: Set[str],
    active_narrations: Set[str],
    active_timers: Mapping[str, Tuple[int, bool, bool]],
    consumed_events: Set[Tuple[str, str]],
    attempts: Mapping[str, int],
    locked_assessments: Set[str],
    playing_videos: Set[str],
) -> List[Tuple[Set[str], Dict[str, Tuple[int, bool, bool]], Set[Tuple[str, str]], Dict[str, int], Set[str], Set[str], Tuple[Tuple[str, str], ...]]]:
    """Return successor runtime facts for one externally produced event."""
    on = transition.get("on") if isinstance(transition, dict) else None
    if not isinstance(on, dict):
        return []
    event_type = on.get("type")
    if not isinstance(event_type, str):
        return []
    producer = EVENT_PRODUCERS.get(event_type)
    if producer == "none":
        return [(set(active_narrations), dict(active_timers), set(consumed_events), dict(attempts), set(locked_assessments), set(playing_videos), ())]
    if producer == "unsupported" or producer is None:
        return []
    if producer == "narration":
        source_id = on.get("sourceId")
        candidates = [source_id] if isinstance(source_id, str) else sorted(active_narrations)
        return [
            (set(), dict(active_timers), set(consumed_events), dict(attempts), set(locked_assessments), set(playing_videos), ())
            for narration_id in candidates
            if narration_id in active_narrations
        ]
    if producer == "timer":
        selected_ids = {value for value in (on.get("sourceId"), on.get("timerId")) if isinstance(value, str)}
        if len(selected_ids) > 1:
            return []
        candidates = selected_ids if selected_ids else set(active_timers)
        updates = []
        for timer_id in sorted(candidates):
            total, has_latest, latest_pending = active_timers.get(timer_id, (0, False, False))
            if total <= 0:
                continue
            # The current map points only at the latest handle.  Its callback
            # can fire while that stale map entry remains; older callbacks are
            # still live but no longer cancelable by this id.
            choices = []
            if latest_pending:
                choices.append((total - 1, has_latest, False))
            if total - int(latest_pending) > 0:
                choices.append((total - 1, has_latest, latest_pending))
            for next_state in choices:
                next_timers = dict(active_timers)
                if next_state[0] == 0:
                    # Preserve a fired latest handle ref even with no pending
                    # callback; cancelTimer still clears that ref later.
                    if next_state[1]:
                        next_timers[timer_id] = next_state
                    else:
                        next_timers.pop(timer_id, None)
                else:
                    next_timers[timer_id] = next_state
                updates.append((set(active_narrations), next_timers, set(consumed_events), dict(attempts), set(locked_assessments), set(playing_videos), ()))
        return updates
    source_id = on.get("sourceId")
    candidates = [(source_id, blocks.get(source_id))] if isinstance(source_id, str) else sorted(blocks.items())
    updates = []
    for block_id, block in candidates:
        event_fact = (block_id, event_type)
        if not isinstance(block, dict):
            continue
        if block.get("type") in ASSESSMENT_TYPES:
            if block_id in locked_assessments or not _block_can_emit_event(block, "answer.submitted", visible, enabled):
                continue
            next_attempts = dict(attempts)
            raw_attempt = next_attempts.get(block_id, 0) + 1
            completion = block.get("completion") if isinstance(block.get("completion"), dict) else {}
            maximum = completion.get("maxAttempts")
            if isinstance(maximum, int) and raw_attempt > maximum:
                continue
            # Unlimited submit-correct retries have identical future event
            # semantics after the first wrong attempt.  Abstract their count
            # to one so a retry loop cannot exhaust the state-space cap.
            attempt = raw_attempt if isinstance(maximum, int) else min(raw_attempt, 1)
            if event_type == "answer.submitted":
                for pending, locks in _assessment_cascades(block, attempt):
                    updates.append((set(active_narrations), dict(active_timers), set(consumed_events), {**next_attempts, block_id: attempt}, set(locked_assessments).union({block_id} if locks else set()), set(playing_videos), pending))
                continue
            # A workflow may ignore answer.submitted and match the later event
            # directly; model that same submission and schedule its remaining
            # synchronous renderer tail.
            for pending, locks in _assessment_cascades(block, attempt):
                if pending and pending[0] == event_fact:
                    updates.append((set(active_narrations), dict(active_timers), set(consumed_events), {**next_attempts, block_id: attempt}, set(locked_assessments).union({block_id} if locks else set()), set(playing_videos), pending[1:]))
                elif event_type == "block.completed" and pending and pending[-1] == event_fact:
                    updates.append((set(active_narrations), dict(active_timers), set(consumed_events), {**next_attempts, block_id: attempt}, set(locked_assessments).union({block_id}), set(playing_videos), ()))
            continue
        if block.get("type") == "video":
            if block_id not in visible or block_id not in enabled:
                continue
            if event_type == "video.started":
                updates.append((set(active_narrations), dict(active_timers), set(consumed_events), dict(attempts), set(locked_assessments), set(playing_videos).union({block_id}), ()))
            elif event_type == "video.ended" and block_id in playing_videos:
                tail = ((block_id, "block.completed"),) if isinstance(block.get("completion"), dict) else ()
                updates.append((set(active_narrations), dict(active_timers), set(consumed_events), dict(attempts), set(locked_assessments), set(playing_videos).difference({block_id}), tail))
            continue
        if not _block_can_emit_event(block, event_type, visible, enabled):
            continue
        if event_type in ONE_SHOT_BLOCK_EVENTS and event_fact in consumed_events:
            continue
        next_consumed = set(consumed_events)
        if event_type in ONE_SHOT_BLOCK_EVENTS:
            next_consumed.add(event_fact)
        updates.append((set(active_narrations), dict(active_timers), next_consumed, dict(attempts), set(locked_assessments), set(playing_videos), ()))
    return updates


def validate_plan_correspondence(root: Path, course: dict) -> List[ValidationIssue]:
    """Compare current plan/coverage records with compiled Part/Slice/Block identities."""
    root = Path(root).absolute()
    plan, plan_issue = _safe_load(root, ".course-work/course-storyboard.json")
    coverage, coverage_issue = _safe_load(root, ".course-work/source-coverage.json")
    issues: List[ValidationIssue] = []
    if plan_issue is not None:
        return [plan_issue]
    if coverage_issue is not None:
        return [coverage_issue]
    assert plan is not None and coverage is not None
    issues.extend(validate_instructional_plan(plan, coverage))

    source_map, _ = _safe_load(root, ".course-work/course-runtime-source-map.json")
    destinations = collect_course_destinations(course)
    destination_pointers = _course_destination_pointers(course)
    blocks = _block_index(course)
    source_assets = _asset_sources(course)
    sources = _coverage_index(coverage)
    course_slices = {(part_id, slice_id): data for part_id, slice_id, data in _slice_entries(course)}
    planned_slice_keys = {(part_id, slice_id) for part_id, slice_id, _ in _plan_slices(plan)}
    source_map_verified: bool | None = None

    def current_source_map() -> bool:
        nonlocal source_map_verified
        if source_map_verified is None:
            source_map_verified = _g5_issue(root, course, source_map) is None
        return source_map_verified

    for part_id, slice_id in sorted(set(course_slices).difference(planned_slice_keys)):
        issues.append(_issue(_target_path(part_id, slice_id), "course-slice-unplanned", "CourseDefinition Slice is absent from the approved page plan"))

    for part_id, slice_id, plan_slice in _plan_slices(plan):
        actual_slice = course_slices.get((part_id, slice_id))
        if actual_slice is None:
            issues.append(_issue(_target_path(part_id, slice_id), "plan-slice-omitted", "planned Slice is absent from CourseDefinition"))
            continue
        planned_layout = plan_slice.get("layoutIntent") if isinstance(plan_slice.get("layoutIntent"), dict) else {}
        actual_layout = actual_slice.get("layout") if isinstance(actual_slice.get("layout"), dict) else {}
        if any(planned_layout.get(field) != actual_layout.get(field) for field in ("preset", "ratio")):
            issues.append(_issue(_target_path(part_id, slice_id), "plan-layout-mismatch", "CourseDefinition layout does not match the approved layout intent"))
        source_uses = _items(plan_slice.get("sourceUses"))
        for source_use in source_uses:
            if not isinstance(source_use, dict) or not isinstance(source_use.get("sourceId"), str):
                continue
            source_id = source_use["sourceId"]
            item = sources.get(source_id)
            if item is None:
                continue  # schema validation above reports the authoritative error.
            same_slice_bindings = [
                binding for binding in _items(item.get("bindings"))
                if isinstance(binding, dict) and (binding.get("partId"), binding.get("sliceId")) == (part_id, slice_id)
            ]
            if not same_slice_bindings:
                issues.append(_issue(_target_path(part_id, slice_id), "plan-source-binding-missing", "planned source use has no binding in the same Part and Slice"))
            for binding in same_slice_bindings:
                block_id = binding.get("blockId")
                path = _target_path(part_id, slice_id, block_id if isinstance(block_id, str) else "unknown")
                destination = (part_id, slice_id, block_id)
                if not isinstance(block_id, str) or destination not in destinations:
                    issues.append(_issue(path, "plan-required-source-omitted", "planned source binding targets a Block omitted from CourseDefinition"))
                    continue
                direct_asset = item.get("sourceFile") in source_assets.get(destination, set())
                source_referenced, pointer_mismatch = _source_map_matches(
                    source_map,
                    source_id,
                    block_id,
                    destination_pointers[destination],
                )
                if pointer_mismatch:
                    issues.append(_issue(path, "source-map-pointer-mismatch", "source-map runtimePointer does not identify the bound Block"))
                source_map_current = current_source_map() if (source_referenced or pointer_mismatch) else False
                if source_referenced and not source_map_current:
                    issues.append(_issue(path, "source-map-identity-invalid", "source-map cannot certify the current compiled CourseDefinition"))
                materialized = direct_asset or (source_referenced and source_map_current and not pointer_mismatch)
                if not materialized:
                    issues.append(_issue(path, "plan-source-unmaterialized", "bound Block does not retain the planned source path or current source-map identity"))

        for relationship in _items(plan_slice.get("imageRelationships")):
            if not isinstance(relationship, dict):
                continue
            source_id = relationship.get("sourceId")
            target_id = relationship.get("targetId")
            if not isinstance(source_id, str):
                continue
            resolved_id, target_issue = _resolve_target(target_id, part_id=part_id, slice_id=slice_id, blocks=blocks)
            if target_issue is not None:
                issues.append(target_issue)
                continue
            item = sources.get(source_id)
            bindings = _items(item.get("bindings")) if isinstance(item, dict) else []
            if not any(
                isinstance(binding, dict)
                and binding.get("partId") == part_id
                and binding.get("sliceId") == slice_id
                and _binding_supports(binding, resolved_id)
                for binding in bindings
            ):
                issues.append(_issue(_target_path(part_id, slice_id, resolved_id), "image-support-target-mismatch", "image relationship is not backed by the bound source support ID"))

        for requirement in _items(plan_slice.get("coVisibleRequirements")):
            if not isinstance(requirement, dict):
                continue
            source_id = requirement.get("sourceId")
            target_id = requirement.get("targetId")
            resolved_id, target_issue = _resolve_target(target_id, part_id=part_id, slice_id=slice_id, blocks=blocks)
            if target_issue is not None:
                issues.append(target_issue)
                continue
            item = sources.get(source_id) if isinstance(source_id, str) else None
            bindings = _items(item.get("bindings")) if isinstance(item, dict) else []
            if not any(isinstance(binding, dict) and (binding.get("partId"), binding.get("sliceId")) == (part_id, slice_id) for binding in bindings):
                issues.append(_issue(_target_path(part_id, slice_id, resolved_id), "covisible-source-omitted", "required co-visible source has no real binding in this Slice"))
                continue
            source_block_ids = {
                binding.get("blockId") for binding in bindings
                if isinstance(binding, dict)
                and (binding.get("partId"), binding.get("sliceId")) == (part_id, slice_id)
                and isinstance(binding.get("blockId"), str)
            }
            states, _ = _effective_step_states(actual_slice)
            answerable_states = [
                visible
                for state_list in states.values()
                for visible, enabled in state_list
                if resolved_id in visible and resolved_id in enabled
            ]
            # Availability (whether an answer target is ever enabled) is
            # reported by validate_workflow_availability.  Once it can be
            # answered, every reachable answerable path must retain every
            # required reference; an existential good branch is insufficient.
            if answerable_states and not all(source_block_ids.issubset(visible) for visible in answerable_states):
                issues.append(_issue(_target_path(part_id, slice_id, resolved_id), "workflow-covisibility-unavailable", "required reference Blocks are not visible when the answer target is enabled"))

        action = plan_slice.get("learnerAction") if isinstance(plan_slice.get("learnerAction"), dict) else {}
        action_target, _ = _resolve_target(action.get("targetId"), part_id=part_id, slice_id=slice_id, blocks=blocks)
        completion = plan_slice.get("completionEvidence")
        declared_event = completion.get("event") if isinstance(completion, dict) else None
        if action_target is not None and isinstance(declared_event, str):
            effective, _ = _effective_step_states(actual_slice)
            steps = {
                step.get("id"): step
                for step in _items(actual_slice.get("workflow", {}).get("steps") if isinstance(actual_slice.get("workflow"), dict) else [])
                if isinstance(step, dict) and isinstance(step.get("id"), str)
            }
            has_event = any(
                isinstance(transition, dict)
                and isinstance(transition.get("on"), dict)
                and transition["on"].get("sourceId") == action_target
                and transition["on"].get("type") == declared_event
                for step_id in effective
                for visible, enabled in effective[step_id]
                if _block_can_emit_event(blocks[action_target][2], declared_event, visible, enabled)
                for transition in _items(steps[step_id].get("transitions"))
            )
            if not has_event:
                issues.append(_issue(_target_path(part_id, slice_id, action_target), "plan-completion-event-unreachable", "approved completionEvidence event is not reachable from the learner action Block"))

        # A deictic reference such as “参考上面的原文” must have a real source
        # surface in this Slice.  This is lexical/identity checking, not an
        # attempt to decide whether that source makes the answer pedagogically good.
        reference_sources = [
            source_id for source_id in {
                item.get("sourceId") for item in _items(plan_slice.get("coVisibleRequirements")) if isinstance(item, dict)
            } if isinstance(source_id, str)
        ]
        visible_source_files = [sources[source_id].get("sourceFile") for source_id in reference_sources if source_id in sources]
        learner_text: List[Tuple[str, str]] = []
        for block in _items(actual_slice.get("blocks")):
            if not isinstance(block, dict) or not isinstance(block.get("id"), str):
                continue
            for field in ("content", "prompt"):
                value = block.get(field)
                if isinstance(value, str):
                    learner_text.append((block["id"], value))
        if any(REFERENCE_TEXT.search(value) for _, value in learner_text) and (
            not visible_source_files
            or not all(_has_reference_surface(actual_slice, source_file) for source_file in visible_source_files)
        ):
            for block_id, value in learner_text:
                if REFERENCE_TEXT.search(value):
                    issues.append(_issue(_target_path(part_id, slice_id, block_id), "deictic-reference-source-absent", "learner-facing reference language has no required source surface in the same Slice"))

    return _ordered(issues)


def validate_layout_assignment(course: dict) -> List[ValidationIssue]:
    """Validate every Block's deterministic Slot placement without CSS judgments."""
    issues: List[ValidationIssue] = []
    for part_id, slice_id, slice_data in _slice_entries(course):
        blocks = [block for block in _items(slice_data.get("blocks")) if isinstance(block, dict) and isinstance(block.get("id"), str)]
        layout = slice_data.get("layout") if isinstance(slice_data.get("layout"), dict) else {}
        slots = _items(layout.get("slots"))
        preset = layout.get("preset")
        slot_ids = [slot.get("id") if isinstance(slot, dict) else None for slot in slots]
        canonical_slots = {
            "full": ["main"],
            "split-horizontal": ["left", "right"],
            "split-vertical": ["top", "bottom"],
            "grid": ["cell-1", "cell-2", "cell-3", "cell-4"],
        }
        slice_path = _target_path(part_id, slice_id)
        if preset not in canonical_slots:
            issues.append(_issue(slice_path, "layout-preset-invalid", "layout preset is not part of the pinned CourseDefinition contract"))
        else:
            expected = canonical_slots[preset]
            valid_slots = (
                slot_ids == expected[:len(slot_ids)] and 2 <= len(slot_ids) <= 4
                if preset == "grid"
                else slot_ids == expected
            )
            if not valid_slots:
                issues.append(_issue(slice_path, "layout-slot-ids-invalid", "layout Slot IDs do not match the canonical preset shape"))
            if preset in {"split-horizontal", "split-vertical"} and layout.get("ratio") not in {"1:1", "3:2", "2:3", "2:1", "1:2", "3:1", "1:3"}:
                issues.append(_issue(slice_path, "layout-ratio-invalid", "split layout requires a pinned ratio"))
            if preset in {"full", "grid"} and layout.get("ratio") is not None:
                issues.append(_issue(slice_path, "layout-ratio-invalid", "full and grid layouts may not declare a ratio"))
        assigned: Dict[str, List[int]] = {block["id"]: [] for block in blocks}
        for slot_index, slot in enumerate(slots):
            for block_id in _items(slot.get("blockIds") if isinstance(slot, dict) else None):
                if isinstance(block_id, str) and block_id in assigned:
                    assigned[block_id].append(slot_index)
        for block in blocks:
            locations = assigned[block["id"]]
            path = _target_path(part_id, slice_id, block["id"])
            if not locations:
                issues.append(_issue(path, "layout-block-unassigned", "Block is not assigned to a layout Slot"))
            elif len(locations) > 1:
                issues.append(_issue(path, "layout-block-duplicated", "Block is assigned to more than one layout Slot"))
        if preset not in {"split-horizontal", "split-vertical"}:
            continue
        empty_slots = [index for index, slot in enumerate(slots) if not _items(slot.get("blockIds") if isinstance(slot, dict) else None)]
        for slot_index in empty_slots:
            issues.append(_issue(f"{_target_path(part_id, slice_id)}/layout-slot:{slot_index}", "layout-empty-slot", "split layout Slot must not be empty"))
        if empty_slots:
            for slot in slots:
                if not isinstance(slot, dict):
                    continue
                slot_blocks = [next((block for block in blocks if block["id"] == block_id), None) for block_id in _items(slot.get("blockIds"))]
                types = {block.get("type") for block in slot_blocks if isinstance(block, dict)}
                if "text" in types and types.intersection(ASSESSMENT_TYPES):
                    text_block = next(block for block in slot_blocks if isinstance(block, dict) and block.get("type") == "text")
                    issues.append(_issue(_target_path(part_id, slice_id, text_block["id"]), "layout-split-stack-empty-side", "text and answerable Blocks are stacked in one split side while the other side is empty"))
    return _ordered(issues)


def _initial_state(slice_data: dict) -> Tuple[Set[str], Set[str]]:
    block_ids = {block["id"] for block in _items(slice_data.get("blocks")) if isinstance(block, dict) and isinstance(block.get("id"), str)}
    initial = slice_data.get("workflow", {}).get("initialState", {}) if isinstance(slice_data.get("workflow"), dict) else {}
    visible = set(_items(initial.get("visibleBlockIds"))) if isinstance(initial, dict) and "visibleBlockIds" in initial else set(block_ids)
    enabled = set(_items(initial.get("enabledBlockIds"))) if isinstance(initial, dict) and "enabledBlockIds" in initial else set(block_ids)
    return visible.intersection(block_ids), enabled.intersection(block_ids)


def _effective_step_states(
    slice_data: dict,
) -> Tuple[Dict[str, List[Tuple[Set[str], Set[str]]]], List[ValidationIssue]]:
    """Explore effective post-enter-action states without merging branches.

    States are finite combinations of the Slice Block IDs.  Recording a state
    only once per step both preserves path facts and terminates cycles safely.
    """
    workflow = slice_data.get("workflow") if isinstance(slice_data.get("workflow"), dict) else {}
    steps = {step.get("id"): step for step in _items(workflow.get("steps")) if isinstance(step, dict) and isinstance(step.get("id"), str)}
    blocks = {
        block["id"]: block
        for block in _items(slice_data.get("blocks"))
        if isinstance(block, dict) and isinstance(block.get("id"), str)
    }
    narration_ids = {
        narration["id"]
        for narration in _items(slice_data.get("narrations"))
        if isinstance(narration, dict) and isinstance(narration.get("id"), str)
    }
    initial_id = workflow.get("initialStepId")
    if initial_id not in steps:
        return {}, []
    visible, enabled = _initial_state(slice_data)
    # The final flag means "apply this step's enter actions".  Synchronous
    # renderer event tails can continue in the same step after an ignored
    # event; they must not replay enter actions while doing so.
    pending = deque([(initial_id, frozenset(visible), frozenset(enabled), frozenset(), (), frozenset(), (), frozenset(), frozenset(), (), True)])
    seen = set()
    effective: Dict[str, List[Tuple[Set[str], Set[str]]]] = {}
    issues: List[ValidationIssue] = []
    max_states = 4096
    while pending:
        step_id, visible_state, enabled_state, narrations_state, timers_state, consumed_state, attempts_state, locked_state, playing_state, pending_events_state, apply_enter_actions = pending.popleft()
        state_key = (step_id, visible_state, enabled_state, narrations_state, timers_state, consumed_state, attempts_state, locked_state, playing_state, pending_events_state, apply_enter_actions)
        if state_key in seen:
            continue
        seen.add(state_key)
        if len(seen) > max_states:
            issues.append(_issue("workflow", "workflow-state-space-exceeded", "workflow has too many reachable visibility/enabled states to validate deterministically"))
            break
        step = steps[step_id]
        visible, enabled = set(visible_state), set(enabled_state)
        active_narrations = set(narrations_state)
        active_timers = dict(timers_state)
        consumed_events, attempts = set(consumed_state), dict(attempts_state)
        locked_assessments, playing_videos = set(locked_state), set(playing_state)
        pending_events = tuple(pending_events_state)
        for action in _items(step.get("enterActions")) if apply_enter_actions else []:
            if not isinstance(action, dict):
                continue
            action_type = action.get("type")
            target = action.get("targetId")
            if action_type == "playNarration" and isinstance(action.get("narrationId"), str) and action["narrationId"] in narration_ids:
                # NarrationController is single-track: playing a new narration
                # replaces the previous active track, whose ended event can no
                # longer arrive.
                active_narrations = {action["narrationId"]}
                continue
            if action_type in {"pauseNarration", "stopNarration"} and isinstance(action.get("narrationId"), str):
                active_narrations.discard(action["narrationId"])
                continue
            if action_type == "startTimer" and isinstance(action.get("timerId"), str):
                timer_id = action["timerId"]
                total, _has_latest, _latest_pending = active_timers.get(timer_id, (0, False, False))
                # timers.current keeps only the newest handle.  An older
                # overwritten callback remains live but is no longer owned.
                active_timers[timer_id] = (min(total + 1, 8), True, True)
                continue
            if action_type == "cancelTimer" and isinstance(action.get("timerId"), str):
                timer_id = action["timerId"]
                total, has_latest, latest_pending = active_timers.get(timer_id, (0, False, False))
                # cancelTimer clears only the stored latest handle.  If that
                # handle fired already, clearing it must not cancel an older
                # pending callback.
                if has_latest:
                    if latest_pending:
                        total -= 1
                    if total > 0:
                        active_timers[timer_id] = (total, False, False)
                    else:
                        active_timers.pop(timer_id, None)
                continue
            if action_type == "resetBlock":
                if isinstance(target, str) and blocks.get(target, {}).get("type") == "video":
                    playing_videos.discard(target)
                    consumed_events = {fact for fact in consumed_events if fact[0] != target}
                    pending_events = tuple(event for event in pending_events if event[0] != target)
                continue
            if action_type == "playBlock" and isinstance(target, str):
                block = blocks.get(target)
                if isinstance(block, dict) and block.get("type") == "video" and target in visible and target in enabled:
                    playing_videos.add(target)
                    pending_events = (*pending_events, (target, "video.started"))
                continue
            if not isinstance(target, str):
                continue
            if action_type == "show": visible.add(target)
            elif action_type == "hide": visible.discard(target)
            elif action_type == "enable":
                if target not in visible:
                    issues.append(_issue(f"block:{target}", "workflow-enable-before-reveal", "Workflow enables a Block before it is visible"))
                enabled.add(target)
            elif action_type == "disable": enabled.discard(target)
        effective.setdefault(step_id, []).append((set(visible), set(enabled).difference(locked_assessments)))
        # Renderer emissions from a submitted answer/video-ended callback are
        # synchronous.  Later emissions remain live even when handling an
        # earlier one changes the workflow step or disables the source Block.
        while pending_events:
            emitted = pending_events[0]
            matched = next((transition for transition in _items(step.get("transitions")) if _matcher_matches(transition.get("on") if isinstance(transition, dict) else None, emitted)), None)
            pending_events = pending_events[1:]
            if matched is not None and matched.get("to") in steps:
                pending.append((matched["to"], frozenset(visible), frozenset(enabled), frozenset(active_narrations), tuple(sorted(active_timers.items())), frozenset(consumed_events), tuple(sorted(attempts.items())), frozenset(locked_assessments), frozenset(playing_videos), pending_events, True))
                break
        else:
            matched = None
        if matched is not None:
            continue
        for transition in _items(step.get("transitions")):
            destination = transition.get("to") if isinstance(transition, dict) else None
            if destination not in steps:
                continue
            for next_narrations, next_timers, next_consumed, next_attempts, next_locked, next_playing, next_events in _external_event_updates(
                transition,
                blocks=blocks,
                visible=visible,
                enabled=enabled,
                active_narrations=active_narrations,
                active_timers=active_timers,
                consumed_events=consumed_events,
                attempts=attempts,
                locked_assessments=locked_assessments,
                playing_videos=playing_videos,
            ):
                pending.append((destination, frozenset(visible), frozenset(enabled), frozenset(next_narrations), tuple(sorted(next_timers.items())), frozenset(next_consumed), tuple(sorted(next_attempts.items())), frozenset(next_locked), frozenset(next_playing), next_events, True))

        # A learner can submit any visible/enabled assessment or play/end any
        # visible/enabled video even when no transition consumes the first
        # emitted event.  The renderer nevertheless produces the rest of its
        # synchronous cascade, which may match a later authored transition.
        # Keep this continuation in the same step without replaying its enter
        # actions (which could otherwise start duplicate timers or narration).
        for block_id, block in sorted(blocks.items()):
            if block.get("type") in ASSESSMENT_TYPES:
                synthetic = {"on": {"type": "answer.submitted", "sourceId": block_id}}
            elif block.get("type") == "video":
                event_type = "video.ended" if block_id in playing_videos else "video.started"
                synthetic = {"on": {"type": event_type, "sourceId": block_id}}
            else:
                continue
            for next_narrations, next_timers, next_consumed, next_attempts, next_locked, next_playing, next_events in _external_event_updates(
                synthetic,
                blocks=blocks,
                visible=visible,
                enabled=enabled,
                active_narrations=active_narrations,
                active_timers=active_timers,
                consumed_events=consumed_events,
                attempts=attempts,
                locked_assessments=locked_assessments,
                playing_videos=playing_videos,
            ):
                pending.append((step_id, frozenset(visible), frozenset(enabled), frozenset(next_narrations), tuple(sorted(next_timers.items())), frozenset(next_consumed), tuple(sorted(next_attempts.items())), frozenset(next_locked), frozenset(next_playing), next_events, False))
    return effective, issues


def validate_workflow_availability(course: dict) -> List[ValidationIssue]:
    """Check reachable answer/completion availability and reveal-enable ordering."""
    issues: List[ValidationIssue] = []
    for part_id, slice_id, slice_data in _slice_entries(course):
        workflow = slice_data.get("workflow") if isinstance(slice_data.get("workflow"), dict) else {}
        steps = [step for step in _items(workflow.get("steps")) if isinstance(step, dict) and isinstance(step.get("id"), str)]
        states, state_issues = _effective_step_states(slice_data)
        block_by_id = {block["id"]: block for block in _items(slice_data.get("blocks")) if isinstance(block, dict) and isinstance(block.get("id"), str)}
        for issue in state_issues:
            if issue.path.startswith("block:"):
                issues.append(_issue(_target_path(part_id, slice_id, issue.path.split(":", 1)[1]), issue.code, issue.message))
            else:
                issues.append(_issue(_target_path(part_id, slice_id), issue.code, issue.message))

        reachable_visible_enabled = {
            block_id
            for state_list in states.values()
            for visible, enabled in state_list
            for block_id in visible.intersection(enabled)
        }
        for block_id, block in block_by_id.items():
            if block.get("type") in ASSESSMENT_TYPES and block_id not in reachable_visible_enabled:
                issues.append(_issue(_target_path(part_id, slice_id, block_id), "workflow-answer-unavailable", "answerable Block is never both visible and enabled on a reachable path"))
            # Video completion can be a progress affordance without being the
            # planned learner action.  Assessment and HTML interaction events
            # are the completion surfaces whose availability this deterministic
            # layer can establish from the CourseDefinition alone.
            if block.get("completion") is None or block.get("type") not in {"interactiveHtml", "singleChoice", "fillBlank"}:
                continue
            completion_events = COMPLETION_EVENT_TYPES[block["type"]]
            transitions = [
                transition
                for step in steps
                if step["id"] in states
                for visible, enabled in states[step["id"]]
                for transition in _items(step.get("transitions"))
                if isinstance(transition, dict) and isinstance(transition.get("on"), dict)
                and transition["on"].get("sourceId") == block_id and transition["on"].get("type") in completion_events
                and _block_can_emit_event(block, transition["on"].get("type"), visible, enabled)
            ]
            if not transitions:
                issues.append(_issue(_target_path(part_id, slice_id, block_id), "workflow-completion-unreachable", "required completion Block has no reachable completion event transition"))
    return _ordered(issues)


def _ordered(issues: Sequence[ValidationIssue]) -> List[ValidationIssue]:
    return sorted(issues, key=lambda issue: (issue.path, issue.code, issue.message))
