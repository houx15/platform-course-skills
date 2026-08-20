"""Teacher-readable Part/Slice plans that precede CourseDefinition production."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import tempfile
from typing import Dict, Iterable, List, Mapping, Sequence, Set, Tuple

from .blueprint import ID_RE
from .course_compiler import canonical_json_hash
from .coverage import validate_coverage_inventory
from .errors import ValidationIssue
from .hashing import hash_path
from .instructional_bindings import load_instructional_coverage, validate_instructional_coverage
from .jsonio import load_json, write_json_atomic
from .materials import validate_material_inventory


PLAN_RELATIVE_PATH = ".course-work/course-storyboard.json"
PLAN_MARKDOWN_RELATIVE_PATH = ".course-work/course-storyboard.md"
COVERAGE_RELATIVE_PATH = ".course-work/source-coverage.json"
INVENTORY_RELATIVE_PATH = ".course-work/materials-extracted.json"
CATALOG_PATH = Path(__file__).with_name("runtime_authoring_catalog.json")
REQUIRED_SLICE_FIELDS = (
    "partId",
    "sliceId",
    "title",
    "teachingPurpose",
    "sourceUses",
    "learnerSees",
    "learnerAction",
    "completionEvidence",
    "layoutIntent",
    "coVisibleRequirements",
    "imageRelationships",
    "unresolvedBlockers",
    "proposedExclusions",
)
ACTION_KINDS_REQUIRING_EVIDENCE = frozenset({"answer", "interaction"})
STABLE_TARGET = re.compile(r"^(?:question|claim):" + ID_RE.pattern[1:-1] + r"$")
BACKTRACKING = re.compile(r"backtrack|go back|previous (?:page|slice)|回看|回退|返回上一", re.IGNORECASE)
REFERENCE_LANGUAGE = re.compile(r"consult|reference|read|look at|compare|source|material|图表|材料|参考|查看|阅读|对照|比对|依据|引用", re.IGNORECASE)
REFERENCE_POLICIES = frozenset({"none", "co-visible", "justified-dependency"})


class PlanValidationError(ValueError):
    """The page plan or its required local evidence is invalid."""

    def __init__(self, issues: Sequence[ValidationIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__("; ".join(f"{issue.code}: {issue.path}" for issue in self.issues))


class PlanApprovalError(ValueError):
    """Approval is absent, malformed, or no longer bound to current evidence."""

    def __init__(self, code: str, path: str, message: str, *, evidence: Mapping[str, str] | None = None) -> None:
        self.code = code
        self.path = path
        self.evidence = dict(evidence or {})
        super().__init__(message)


def _issue(path: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(path, code, message)


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _safe_root(root: Path) -> Tuple[Path | None, List[ValidationIssue]]:
    candidate = Path(root).absolute()
    if candidate.is_symlink():
        return None, [_issue(".", "symlink-root", "course root may not be a symlink")]
    if not candidate.is_dir():
        return None, [_issue(".", "invalid-root", "course root must be an existing directory")]
    return candidate, []


def _safe_json(root: Path, relative: str) -> Tuple[object | None, List[ValidationIssue]]:
    current = root
    for component in Path(relative).parts:
        current = current / component
        if current.is_symlink():
            return None, [_issue(relative, "symlink-file", "required evidence may not be a symlink")]
    if not current.is_file():
        return None, [_issue(relative, "missing-file", "required evidence is missing")]
    try:
        return load_json(current), []
    except ValueError:
        return None, [_issue(relative, "invalid-json", "required evidence is invalid JSON")]


def _layout_catalog() -> dict:
    try:
        catalog = load_json(CATALOG_PATH)
    except ValueError as exc:  # A pinned repository contract missing is a tool failure.
        raise RuntimeError("runtime authoring catalog is unavailable") from exc
    layout = catalog.get("layout") if isinstance(catalog, dict) else None
    if not isinstance(layout, dict):
        raise RuntimeError("runtime authoring catalog has no layout contract")
    return layout


def _coverage_index(coverage: object) -> Tuple[Dict[str, dict], List[ValidationIssue]]:
    issues: List[ValidationIssue] = []
    items = coverage.get("items") if isinstance(coverage, dict) else None
    if not isinstance(items, list):
        return {}, issues
    indexed: Dict[str, dict] = {}
    for index, item in enumerate(items):
        path = f"{COVERAGE_RELATIVE_PATH}.items[{index}]"
        if not isinstance(item, dict):
            continue
        source_id = item.get("sourceId")
        if not _nonempty(source_id):
            continue
        if source_id in indexed:
            continue
        indexed[source_id] = item
    return indexed, issues


def _action_description(action: object) -> str:
    if isinstance(action, str):
        return action.strip()
    if isinstance(action, dict) and _nonempty(action.get("description")):
        return action["description"].strip()
    return ""


def _concrete_evidence(value: object) -> bool:
    if _nonempty(value):
        return True
    if not isinstance(value, dict):
        return False
    return any(_nonempty(value.get(field)) for field in ("description", "rule", "artifact", "event"))


def _validate_layout(value: object, path: str, issues: List[ValidationIssue]) -> None:
    if not isinstance(value, dict):
        issues.append(_issue(path, "required", "layoutIntent is required"))
        return
    layout = _layout_catalog()
    presets = set(layout.get("presets", []))
    ratios = set(layout.get("splitRatios", []))
    ratio_required = set(layout.get("ratioRequiredFor", []))
    preset = value.get("preset")
    if preset not in presets:
        issues.append(_issue(f"{path}.preset", "invalid-layout-preset", "layout preset is not in the pinned CourseDefinition catalog"))
    ratio = value.get("ratio")
    if preset in ratio_required:
        if ratio not in ratios:
            issues.append(_issue(f"{path}.ratio", "invalid-layout-ratio", "split layout requires a pinned ratio"))
    elif ratio is not None:
        issues.append(_issue(f"{path}.ratio", "invalid-layout-ratio", "this layout preset may not declare a ratio"))


def _validate_source_use(value: object, path: str, sources: Mapping[str, dict], issues: List[ValidationIssue]) -> None:
    if not isinstance(value, dict):
        issues.append(_issue(path, "invalid-shape", "source use must be an object"))
        return
    source_id = value.get("sourceId")
    if not _nonempty(source_id):
        issues.append(_issue(f"{path}.sourceId", "required", "source use needs a sourceId"))
    elif source_id not in sources:
        issues.append(_issue(f"{path}.sourceId", "unknown-source", "source use must reference current source coverage"))
    for field in ("locator", "materialRole"):
        if not _nonempty(value.get(field)):
            issues.append(_issue(f"{path}.{field}", "required", f"source use needs {field}"))
    if _nonempty(source_id) and source_id in sources and _nonempty(value.get("locator")):
        if value["locator"] != sources[source_id].get("location"):
            issues.append(_issue(f"{path}.locator", "source-locator-mismatch", "source locator must preserve the current coverage locator"))


def _validate_slice(slice_data: object, path: str, expected_part_id: str, sources: Mapping[str, dict], issues: List[ValidationIssue]) -> str | None:
    if not isinstance(slice_data, dict):
        issues.append(_issue(path, "invalid-shape", "slice must be an object"))
        return None
    for field in REQUIRED_SLICE_FIELDS:
        if field not in slice_data:
            issues.append(_issue(f"{path}.{field}", "required", f"slice requires {field}"))
    part_id = slice_data.get("partId")
    if not _nonempty(part_id):
        issues.append(_issue(f"{path}.partId", "required", "slice partId is required"))
    elif not ID_RE.fullmatch(part_id):
        issues.append(_issue(f"{path}.partId", "invalid-stable-id", "partId must use the pinned lowercase hyphenated ID grammar"))
    elif part_id != expected_part_id:
        issues.append(_issue(f"{path}.partId", "part-id-mismatch", "slice partId must match its containing Part"))
    slice_id = slice_data.get("sliceId")
    if not _nonempty(slice_id):
        issues.append(_issue(f"{path}.sliceId", "required", "sliceId is required"))
        slice_id = None
    elif not ID_RE.fullmatch(slice_id):
        issues.append(_issue(f"{path}.sliceId", "invalid-stable-id", "sliceId must use the pinned lowercase hyphenated ID grammar"))
        slice_id = None
    for field in ("title", "teachingPurpose", "learnerSees"):
        if not _nonempty(slice_data.get(field)):
            issues.append(_issue(f"{path}.{field}", "required", f"{field} is required"))

    source_uses = slice_data.get("sourceUses")
    if not isinstance(source_uses, list):
        issues.append(_issue(f"{path}.sourceUses", "required", "sourceUses must be a list"))
    else:
        for index, source_use in enumerate(source_uses):
            _validate_source_use(source_use, f"{path}.sourceUses[{index}]", sources, issues)

    action = slice_data.get("learnerAction")
    if not isinstance(action, dict):
        issues.append(_issue(f"{path}.learnerAction", "required", "learnerAction must describe a learner action"))
        action = {}
    kind = action.get("kind")
    if not _nonempty(kind):
        issues.append(_issue(f"{path}.learnerAction.kind", "required", "learner action kind is required"))
    if not _action_description(action):
        issues.append(_issue(f"{path}.learnerAction.description", "required", "learner action description is required"))
    if kind in ACTION_KINDS_REQUIRING_EVIDENCE and not _concrete_evidence(slice_data.get("completionEvidence")):
        issues.append(_issue(f"{path}.completionEvidence", "completion-evidence-required", "answer or interaction needs concrete completion evidence"))
    elif "completionEvidence" in slice_data and not _concrete_evidence(slice_data.get("completionEvidence")):
        issues.append(_issue(f"{path}.completionEvidence", "required", "completionEvidence is required"))

    _validate_layout(slice_data.get("layoutIntent"), f"{path}.layoutIntent", issues)
    covisible = slice_data.get("coVisibleRequirements")
    covisible_by_source: Dict[str, List[str]] = {}
    covisible_targets: List[Tuple[str, object]] = []
    if not isinstance(covisible, list):
        issues.append(_issue(f"{path}.coVisibleRequirements", "required", "coVisibleRequirements must be a list"))
    else:
        for index, requirement in enumerate(covisible):
            requirement_path = f"{path}.coVisibleRequirements[{index}]"
            if not isinstance(requirement, dict):
                issues.append(_issue(requirement_path, "invalid-shape", "co-visible requirement must be an object"))
                continue
            source_id = requirement.get("sourceId")
            if not _nonempty(source_id):
                issues.append(_issue(f"{requirement_path}.sourceId", "required", "co-visible requirement needs a sourceId"))
            elif source_id not in sources:
                issues.append(_issue(f"{requirement_path}.sourceId", "unknown-source", "co-visible requirement references an unknown source"))
            else:
                covisible_by_source.setdefault(source_id, []).append(requirement.get("targetId"))
                covisible_targets.append((requirement_path, requirement.get("targetId")))
            if not STABLE_TARGET.match(requirement.get("targetId", "")):
                issues.append(_issue(f"{requirement_path}.targetId", "stable-target-required", "co-visible target must be a stable question: or claim: ID"))
            if not _nonempty(requirement.get("reason")):
                issues.append(_issue(f"{requirement_path}.reason", "required", "co-visible requirement needs a reason"))

    policy = action.get("referencePolicy")
    if policy not in REFERENCE_POLICIES:
        issues.append(_issue(f"{path}.learnerAction.referencePolicy", "reference-policy-required", "learner action needs an explicit reference policy"))
    reference_ids = action.get("referenceSourceIds", [])
    if not isinstance(reference_ids, list) or not all(_nonempty(source_id) for source_id in reference_ids):
        issues.append(_issue(f"{path}.learnerAction.referenceSourceIds", "invalid-shape", "referenceSourceIds must be a string list"))
        reference_ids = []
    elif len(set(reference_ids)) != len(reference_ids):
        issues.append(_issue(f"{path}.learnerAction.referenceSourceIds", "duplicate-source", "referenceSourceIds must be unique"))
    target_id = action.get("targetId")
    dependency = action.get("dependencyJustification")
    if policy == "none":
        if reference_ids or target_id is not None or dependency is not None or REFERENCE_LANGUAGE.search(_action_description(action)):
            issues.append(_issue(f"{path}.learnerAction", "reference-policy-inconsistent", "reference-dependent wording needs an explicit co-visible or justified-dependency policy"))
    elif policy in {"co-visible", "justified-dependency"}:
        if not reference_ids:
            issues.append(_issue(f"{path}.learnerAction.referenceSourceIds", "reference-sources-required", "reference-dependent action needs explicit source IDs"))
        if not isinstance(target_id, str) or not STABLE_TARGET.match(target_id):
            issues.append(_issue(f"{path}.learnerAction.targetId", "stable-target-required", "reference-dependent action needs a stable question or claim target"))
        if policy == "co-visible" and dependency is not None:
            issues.append(_issue(f"{path}.learnerAction.dependencyJustification", "reference-policy-inconsistent", "co-visible references may not use a dependency justification"))
        if policy == "justified-dependency" and (not _nonempty(dependency) or BACKTRACKING.search(dependency)):
            issues.append(_issue(f"{path}.learnerAction.dependencyJustification", "invalid-dependency", "dependency must be concrete and may not be ordinary assessment backtracking"))
        for index, source_id in enumerate(reference_ids):
            reference_path = f"{path}.learnerAction.referenceSourceIds[{index}]"
            if source_id not in sources:
                issues.append(_issue(reference_path, "unknown-source", "reference-dependent action needs a known source"))
                continue
            targets = covisible_by_source.get(source_id, [])
            if policy == "co-visible" and target_id not in targets:
                issues.append(_issue(reference_path, "reference-not-covisible", "each reference source must be co-visible at the action's question or claim target"))
            if targets and any(value != target_id for value in targets):
                issues.append(_issue(reference_path, "covisible-target-mismatch", "co-visible source must point to the same target as the learner action"))
        if isinstance(target_id, str):
            for requirement_path, requirement_target in covisible_targets:
                if requirement_target != target_id:
                    issues.append(_issue(f"{requirement_path}.targetId", "covisible-target-mismatch", "co-visible requirement must point to the learner action target"))

    images = slice_data.get("imageRelationships")
    if not isinstance(images, list):
        issues.append(_issue(f"{path}.imageRelationships", "required", "imageRelationships must be a list"))
    else:
        for index, relationship in enumerate(images):
            relation_path = f"{path}.imageRelationships[{index}]"
            if not isinstance(relationship, dict):
                issues.append(_issue(relation_path, "invalid-shape", "image relationship must be an object"))
                continue
            source_id = relationship.get("sourceId")
            if not _nonempty(source_id) or source_id not in sources:
                issues.append(_issue(f"{relation_path}.sourceId", "unknown-source", "image relationship needs a known source"))
            target_type = relationship.get("targetType")
            target_id = relationship.get("targetId")
            if target_type not in {"question", "claim"} or not isinstance(target_id, str) or not target_id.startswith(f"{target_type}:") or not STABLE_TARGET.match(target_id):
                issues.append(_issue(f"{relation_path}.targetId", "stable-target-required", "image relationship needs a stable intended question or claim target"))
            if not _nonempty(relationship.get("relationship")):
                issues.append(_issue(f"{relation_path}.relationship", "required", "image relationship needs its instructional role"))

    for field in ("unresolvedBlockers", "proposedExclusions"):
        if not isinstance(slice_data.get(field), list):
            issues.append(_issue(f"{path}.{field}", "required", f"{field} must be a list"))
    blockers = slice_data.get("unresolvedBlockers")
    if isinstance(blockers, list):
        for index, blocker in enumerate(blockers):
            blocker_path = f"{path}.unresolvedBlockers[{index}]"
            if _nonempty(blocker):
                continue
            if not isinstance(blocker, dict) or not _nonempty(blocker.get("reason")):
                issues.append(_issue(blocker_path, "invalid-blocker", "unresolved blocker needs a concrete reason"))
    exclusions = slice_data.get("proposedExclusions")
    if isinstance(exclusions, list):
        for index, exclusion in enumerate(exclusions):
            exclusion_path = f"{path}.proposedExclusions[{index}]"
            source_id = exclusion if isinstance(exclusion, str) else exclusion.get("sourceId") if isinstance(exclusion, dict) else None
            if not _nonempty(source_id) or source_id not in sources or sources[source_id].get("disposition") != "exclude-proposed":
                issues.append(_issue(exclusion_path, "invalid-proposed-exclusion", "proposed exclusion must reference a current exclude-proposed source"))
    return slice_id


def validate_instructional_plan(document: object, coverage: object) -> List[ValidationIssue]:
    """Validate the v2 teacher-facing plan without requiring an approval record."""
    issues = list(validate_instructional_coverage(coverage))
    sources, index_issues = _coverage_index(coverage)
    issues.extend(index_issues)
    if not isinstance(document, dict):
        return issues + [_issue(PLAN_RELATIVE_PATH, "invalid-shape", "page plan must be an object")]
    if document.get("schemaVersion") != "2.0":
        issues.append(_issue(f"{PLAN_RELATIVE_PATH}.schemaVersion", "invalid-version", "page plan schemaVersion must be 2.0"))
    parts = document.get("parts")
    if not isinstance(parts, list) or not parts:
        issues.append(_issue(f"{PLAN_RELATIVE_PATH}.parts", "parts-required", "page plan needs at least one Part"))
        return issues
    part_ids: Set[str] = set()
    slice_ids: Set[str] = set()
    for part_index, part in enumerate(parts):
        part_path = f"{PLAN_RELATIVE_PATH}.parts[{part_index}]"
        if not isinstance(part, dict):
            issues.append(_issue(part_path, "invalid-shape", "Part must be an object"))
            continue
        part_id = part.get("partId")
        if not _nonempty(part_id):
            issues.append(_issue(f"{part_path}.partId", "required", "Part needs a stable partId"))
            continue
        if not ID_RE.fullmatch(part_id):
            issues.append(_issue(f"{part_path}.partId", "invalid-stable-id", "partId must use the pinned lowercase hyphenated ID grammar"))
            continue
        if part_id in part_ids:
            issues.append(_issue(f"{part_path}.partId", "duplicate-part-id", "partId must be unique"))
        part_ids.add(part_id)
        slices = part.get("slices")
        if not isinstance(slices, list) or not slices:
            issues.append(_issue(f"{part_path}.slices", "part-slices-required", "Part needs at least one Slice"))
            continue
        for slice_index, slice_data in enumerate(slices):
            slice_id = _validate_slice(slice_data, f"{part_path}.slices[{slice_index}]", part_id, sources, issues)
            if slice_id is not None:
                if slice_id in slice_ids:
                    issues.append(_issue(f"{part_path}.slices[{slice_index}].sliceId", "duplicate-slice-id", "sliceId must be unique"))
                slice_ids.add(slice_id)
    return issues


def _prefix_inventory_issues(issues: Iterable[ValidationIssue]) -> List[ValidationIssue]:
    prefixed = []
    for issue in issues:
        path = issue.path
        if not path.startswith(".course-work/"):
            path = f".course-work/{path}"
        prefixed.append(_issue(path, issue.code, issue.message))
    return prefixed


def _load_plan_evidence(root: Path) -> Tuple[dict | None, dict | None, dict | None, List[ValidationIssue]]:
    plan, plan_issues = _safe_json(root, PLAN_RELATIVE_PATH)
    raw_coverage, coverage_issues = _safe_json(root, COVERAGE_RELATIVE_PATH)
    extracted, inventory_issues = _safe_json(root, INVENTORY_RELATIVE_PATH)
    issues = [*plan_issues, *coverage_issues, *inventory_issues]
    if issues:
        return None, None, None, issues
    if not isinstance(plan, dict):
        return None, None, None, [_issue(PLAN_RELATIVE_PATH, "invalid-shape", "page plan must be an object")]
    if not isinstance(raw_coverage, dict):
        return None, None, None, [_issue(COVERAGE_RELATIVE_PATH, "invalid-shape", "source coverage must be an object")]
    if not isinstance(extracted, dict):
        return None, None, None, [_issue(INVENTORY_RELATIVE_PATH, "invalid-shape", "materials inventory must be an object")]
    try:
        coverage = load_instructional_coverage(root)
    except ValueError:
        return None, None, None, [_issue(COVERAGE_RELATIVE_PATH, "invalid-shape", "source coverage cannot be loaded")]
    if not isinstance(coverage, dict):
        return None, None, None, [_issue(COVERAGE_RELATIVE_PATH, "invalid-shape", "source coverage must be an object")]
    issues.extend(_prefix_inventory_issues(validate_instructional_coverage(coverage)))
    issues.extend(_prefix_inventory_issues(validate_material_inventory(extracted)))
    issues.extend(_prefix_inventory_issues(validate_coverage_inventory(extracted, coverage)))
    return plan, coverage, extracted, issues


def validate_plan_at_root(root: Path) -> List[ValidationIssue]:
    safe_root, root_issues = _safe_root(root)
    if safe_root is None:
        return root_issues
    plan, coverage, _, evidence_issues = _load_plan_evidence(safe_root)
    if evidence_issues:
        return evidence_issues
    assert plan is not None and coverage is not None
    return validate_instructional_plan(plan, coverage)


def plan_content_hash(document: object) -> str:
    """Hash teacher-approved plan content without self-referential approval data."""
    if not isinstance(document, dict):
        return canonical_json_hash(document)
    content = deepcopy(document)
    content.pop("approval", None)
    return canonical_json_hash(content)


def _evidence_hashes(root: Path) -> Dict[str, str]:
    return {
        "materialsExtractedHash": hash_path(root / INVENTORY_RELATIVE_PATH),
        "sourceCoverageHash": hash_path(root / COVERAGE_RELATIVE_PATH),
    }


def _validated_current(root: Path) -> Tuple[Path, dict, dict, Dict[str, str]]:
    safe_root, root_issues = _safe_root(root)
    if safe_root is None:
        raise PlanValidationError(root_issues)
    plan, coverage, _, evidence_issues = _load_plan_evidence(safe_root)
    if evidence_issues:
        raise PlanValidationError(evidence_issues)
    assert plan is not None and coverage is not None
    plan_issues = validate_instructional_plan(plan, coverage)
    if plan_issues:
        raise PlanValidationError(plan_issues)
    try:
        hashes = _evidence_hashes(safe_root)
    except ValueError:
        raise PlanValidationError([_issue(".course-work", "invalid-evidence-hash", "required evidence cannot be hashed")]) from None
    return safe_root, plan, coverage, hashes


def approve_plan(root: Path, *, decision_id: str, approved_at: str) -> dict:
    """Record an explicit teacher decision after validating the plan and evidence."""
    if not _nonempty(decision_id):
        raise PlanApprovalError("decision-id-required", PLAN_RELATIVE_PATH, "approval needs an explicit decision ID")
    if not _nonempty(approved_at):
        raise PlanApprovalError("approved-at-required", PLAN_RELATIVE_PATH, "approval needs an approval timestamp")
    safe_root, plan, _, hashes = _validated_current(root)
    approval = {
        "teacherConfirmed": True,
        "decisionId": decision_id.strip(),
        "approvedAt": approved_at.strip(),
        "planContentHash": plan_content_hash(plan),
        **hashes,
    }
    updated = deepcopy(plan)
    updated["approval"] = approval
    write_json_atomic(safe_root / PLAN_RELATIVE_PATH, updated)
    return approval


def verify_plan_approval(root: Path) -> Dict[str, str]:
    """Verify that approval still names the exact current plan and source evidence."""
    safe_root, plan, _, hashes = _validated_current(root)
    approval = plan.get("approval")
    if not isinstance(approval, dict):
        raise PlanApprovalError("approval-missing", PLAN_RELATIVE_PATH, "teacher approval is missing")
    required = ("teacherConfirmed", "decisionId", "approvedAt", "planContentHash", "materialsExtractedHash", "sourceCoverageHash")
    if approval.get("teacherConfirmed") is not True or any(not _nonempty(approval.get(field)) for field in required[1:]):
        raise PlanApprovalError("approval-invalid", f"{PLAN_RELATIVE_PATH}.approval", "teacher approval is incomplete")
    current = {"planContentHash": plan_content_hash(plan), **hashes}
    stale = {key: value for key, value in current.items() if approval.get(key) != value}
    if stale:
        raise PlanApprovalError("approval-stale", f"{PLAN_RELATIVE_PATH}.approval", "teacher approval is stale; approve the current page plan again", evidence=stale)
    return {
        "decisionId": approval["decisionId"],
        "approvedAt": approval["approvedAt"],
        "planContentHash": current["planContentHash"],
        **hashes,
    }


def _markdown_safe(value: object) -> str:
    """Render text as CommonMark text, never as HTML/table/heading syntax."""
    text = str(value)
    text = text.replace("\\", "\\\\")
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return text.replace("|", "\\|")


def _slice_rows(plan: dict) -> Iterable[dict]:
    for part in plan.get("parts", []):
        if not isinstance(part, dict):
            continue
        for slice_data in part.get("slices", []):
            if isinstance(slice_data, dict):
                yield slice_data


def _source_text(source_uses: object) -> str:
    if not isinstance(source_uses, list):
        return "—"
    values = []
    for source_use in source_uses:
        if isinstance(source_use, dict):
            values.append(f"{source_use.get('sourceId', '—')}（{source_use.get('materialRole', '—')}；{source_use.get('locator', '—')}）")
    return "；".join(values) or "—"


def _layout_text(layout: object) -> str:
    if not isinstance(layout, dict):
        return "—"
    preset = layout.get("preset", "—")
    ratio = layout.get("ratio")
    return f"{preset}（{ratio}）" if ratio else str(preset)


def _dependency_text(slice_data: dict) -> str:
    requirements = slice_data.get("coVisibleRequirements")
    if not isinstance(requirements, list) or not requirements:
        justification = slice_data.get("learnerAction", {}).get("dependencyJustification") if isinstance(slice_data.get("learnerAction"), dict) else None
        return str(justification) if _nonempty(justification) else "—"
    return "；".join(
        f"{item.get('sourceId', '—')}：{item.get('reason', '—')}"
        for item in requirements if isinstance(item, dict)
    ) or "—"


def render_teacher_plan(plan: dict, coverage: dict) -> str:
    """Generate the teacher view; this Markdown is deliberately never approval evidence."""
    title = plan.get("title") if _nonempty(plan.get("title")) else "课程页计划"
    lines = [f"# {_markdown_safe(title)}", "", "## 页面计划", "", "| Part / Slice | 教学目的 | 素材 | 学生行动 | 排版 | 同页参考/依赖 |", "| --- | --- | --- | --- | --- | --- |"]
    for slice_data in _slice_rows(plan):
        source_uses = slice_data.get("sourceUses")
        identity = f"{slice_data.get('partId', '—')} / {slice_data.get('sliceId', '—')}"
        lines.append("| " + " | ".join(_markdown_safe(value) for value in (
            identity,
            slice_data.get("teachingPurpose", "—"),
            _source_text(source_uses),
            _action_description(slice_data.get("learnerAction")) or "—",
            _layout_text(slice_data.get("layoutIntent")),
            _dependency_text(slice_data),
        )) + " |")
    lines.extend(["", "## 未使用或仅用于备课", "", "| 素材 | 处置 | 定位 | 原因 |", "| --- | --- | --- | --- |"])
    rows = []
    for item in coverage.get("items", []) if isinstance(coverage, dict) else []:
        if not isinstance(item, dict):
            continue
        disposition = item.get("disposition")
        source_id = item.get("sourceId")
        bindings = item.get("bindings", [])
        relevant = disposition in {"authoring-only", "exclude-proposed", "exclude-approved"} or (disposition == "optional-support" and (not isinstance(bindings, list) or not bindings))
        if relevant:
            rows.append((source_id or "—", disposition or "—", item.get("location") or "—", item.get("reason") or item.get("summary") or "—"))
    if rows:
        lines.extend("| " + " | ".join(_markdown_safe(value) for value in row) + " |" for row in rows)
    else:
        lines.append("| 无 | — | — | — |")
    return "\n".join(lines) + "\n"


def render_plan_at_root(root: Path) -> Path:
    safe_root, plan, coverage, _ = _validated_current(root)
    output = safe_root / PLAN_MARKDOWN_RELATIVE_PATH
    content = render_teacher_plan(plan, coverage)
    if output.parent.is_symlink():
        raise PlanValidationError([_issue(".course-work", "symlink-file", "output directory may not be a symlink")])
    if output.is_symlink():
        raise PlanValidationError([_issue(PLAN_MARKDOWN_RELATIVE_PATH, "symlink-file", "output may not be a symlink")])
    if not output.parent.is_dir():
        raise PlanValidationError([_issue(".course-work", "missing-file", "output directory is missing")])
    descriptor, temporary_name = tempfile.mkstemp(prefix=".course-storyboard-", suffix=".tmp", dir=str(output.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(output)
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_fd = os.open(output.parent, directory_flags)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()
    return output


def current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
