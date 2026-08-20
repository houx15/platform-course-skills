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
from .instructional_bindings import collect_course_destinations
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


def _source_map_has(source_map: object, source_id: str, block_id: str) -> bool:
    if not isinstance(source_map, dict):
        return False
    for mapping in _items(source_map.get("mappings")):
        if not isinstance(mapping, dict) or mapping.get("targetId") != f"block:{block_id}":
            continue
        if source_id in _items(mapping.get("sourceIds")):
            return True
    return False


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
    blocks = _block_index(course)
    source_assets = _asset_sources(course)
    sources = _coverage_index(coverage)
    course_slices = {(part_id, slice_id): data for part_id, slice_id, data in _slice_entries(course)}
    planned_slice_keys = {(part_id, slice_id) for part_id, slice_id, _ in _plan_slices(plan)}

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
                materialized = item.get("sourceFile") in source_assets.get(destination, set()) or _source_map_has(source_map, source_id, block_id)
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
            states = _step_states(actual_slice)
            if not any(
                source_block_ids.issubset(visible) and resolved_id in enabled
                for visible, enabled in states.values()
            ):
                issues.append(_issue(_target_path(part_id, slice_id, resolved_id), "workflow-covisibility-unavailable", "required reference Blocks are not visible when the answer target is enabled"))

        # A deictic reference such as “参考上面的原文” must have a real source
        # surface in this Slice.  This is lexical/identity checking, not an
        # attempt to decide whether that source makes the answer pedagogically good.
        reference_sources = [
            source_id for source_id in {
                item.get("sourceId") for item in _items(plan_slice.get("coVisibleRequirements")) if isinstance(item, dict)
            } if isinstance(source_id, str)
        ]
        visible_source_files = [sources[source_id].get("sourceFile") for source_id in reference_sources if source_id in sources]
        learner_text = []
        for block in _items(actual_slice.get("blocks")):
            if not isinstance(block, dict):
                continue
            for field in ("content", "prompt"):
                value = block.get(field)
                if isinstance(value, str):
                    learner_text.append(value)
        if any(REFERENCE_TEXT.search(value) for value in learner_text) and (
            not visible_source_files
            or not all(_has_reference_surface(actual_slice, source_file) for source_file in visible_source_files)
        ):
            issues.append(_issue(_target_path(part_id, slice_id), "deictic-reference-source-absent", "learner-facing reference language has no required source surface in the same Slice"))

    return _ordered(issues)


def validate_layout_assignment(course: dict) -> List[ValidationIssue]:
    """Validate every Block's deterministic Slot placement without CSS judgments."""
    issues: List[ValidationIssue] = []
    for part_id, slice_id, slice_data in _slice_entries(course):
        blocks = [block for block in _items(slice_data.get("blocks")) if isinstance(block, dict) and isinstance(block.get("id"), str)]
        layout = slice_data.get("layout") if isinstance(slice_data.get("layout"), dict) else {}
        slots = _items(layout.get("slots"))
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
        if layout.get("preset") not in {"split-horizontal", "split-vertical"}:
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


def _step_states(slice_data: dict) -> Dict[str, Tuple[Set[str], Set[str]]]:
    workflow = slice_data.get("workflow") if isinstance(slice_data.get("workflow"), dict) else {}
    steps = {step.get("id"): step for step in _items(workflow.get("steps")) if isinstance(step, dict) and isinstance(step.get("id"), str)}
    initial_id = workflow.get("initialStepId")
    if initial_id not in steps:
        return {}
    visible, enabled = _initial_state(slice_data)
    states: Dict[str, Tuple[Set[str], Set[str]]] = {initial_id: (visible, enabled)}
    queue = deque([initial_id])
    while queue:
        step_id = queue.popleft()
        step = steps[step_id]
        current_visible, current_enabled = states[step_id]
        visible, enabled = set(current_visible), set(current_enabled)
        for action in _items(step.get("enterActions")):
            if not isinstance(action, dict) or not isinstance(action.get("targetId"), str):
                continue
            target = action["targetId"]
            if action.get("type") == "show": visible.add(target)
            elif action.get("type") == "hide": visible.discard(target)
            elif action.get("type") == "enable": enabled.add(target)
            elif action.get("type") == "disable": enabled.discard(target)
        for transition in _items(step.get("transitions")):
            destination = transition.get("to") if isinstance(transition, dict) else None
            if destination not in steps:
                continue
            candidate = (set(visible), set(enabled))
            existing = states.get(destination)
            # A finite union represents every monotonic reveal/enable state;
            # hidden/disabled paths are diagnosed at the action that creates them.
            if existing is None:
                states[destination] = candidate
                queue.append(destination)
            else:
                merged = (existing[0].union(candidate[0]), existing[1].union(candidate[1]))
                if merged != existing:
                    states[destination] = merged
                    queue.append(destination)
    return states


def validate_workflow_availability(course: dict) -> List[ValidationIssue]:
    """Check reachable answer/completion availability and reveal-enable ordering."""
    issues: List[ValidationIssue] = []
    for part_id, slice_id, slice_data in _slice_entries(course):
        workflow = slice_data.get("workflow") if isinstance(slice_data.get("workflow"), dict) else {}
        steps = [step for step in _items(workflow.get("steps")) if isinstance(step, dict) and isinstance(step.get("id"), str)]
        states = _step_states(slice_data)
        block_by_id = {block["id"]: block for block in _items(slice_data.get("blocks")) if isinstance(block, dict) and isinstance(block.get("id"), str)}
        for step in steps:
            visible, _ = states.get(step["id"], _initial_state(slice_data))
            for action_index, action in enumerate(_items(step.get("enterActions"))):
                if not isinstance(action, dict) or action.get("type") != "enable" or not isinstance(action.get("targetId"), str):
                    continue
                if action["targetId"] not in visible:
                    issues.append(_issue(_target_path(part_id, slice_id, action["targetId"]), "workflow-enable-before-reveal", "Workflow enables a Block before it is visible"))
                visible.add(action["targetId"])

        reachable_visible_enabled = {
            block_id
            for visible, enabled in states.values()
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
                transition for step in steps for transition in _items(step.get("transitions"))
                if isinstance(transition, dict) and isinstance(transition.get("on"), dict)
                and transition["on"].get("sourceId") == block_id and transition["on"].get("type") in completion_events
            ]
            if not transitions:
                issues.append(_issue(_target_path(part_id, slice_id, block_id), "workflow-completion-unreachable", "required completion Block has no reachable completion event transition"))
    return _ordered(issues)


def _ordered(issues: Sequence[ValidationIssue]) -> List[ValidationIssue]:
    return sorted(issues, key=lambda issue: (issue.path, issue.code, issue.message))
