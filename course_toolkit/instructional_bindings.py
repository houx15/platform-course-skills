"""Source-coverage v2 loading, migration, and CourseDefinition bindings."""

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .course_compiler import (
    CompilationEvidenceError,
    CompilationToolError,
    verify_compilation_evidence,
)
from .course_package_validation import iter_asset_references
from .errors import ValidationIssue
from .jsonio import load_json


DISPOSITIONS = frozenset(
    {
        "required-core",
        "required-evidence",
        "optional-support",
        "authoring-only",
        "exclude-proposed",
        "exclude-approved",
    }
)
REQUIRED_DISPOSITIONS = frozenset({"required-core", "required-evidence"})
Destination = Tuple[str, str, str]


@dataclass(frozen=True)
class BindingAudit:
    blockers: Tuple[ValidationIssue, ...]
    warnings: Tuple[ValidationIssue, ...]


def _course_payload(course: dict) -> dict:
    payload = course.get("course") if isinstance(course, dict) else None
    return payload if isinstance(payload, dict) else {}


def _list_field(value: object, field: str) -> list:
    if not isinstance(value, dict):
        return []
    items = value.get(field)
    return items if isinstance(items, list) else []


def collect_course_destinations(course: dict) -> Dict[Destination, dict]:
    """Collect only real CourseDefinition 2.0 Part/Slice/Block targets."""
    destinations: Dict[Destination, dict] = {}
    for part in _list_field(_course_payload(course), "parts"):
        if not isinstance(part, dict) or not isinstance(part.get("id"), str):
            continue
        for slice_data in _list_field(part, "slices"):
            if not isinstance(slice_data, dict) or not isinstance(
                slice_data.get("id"), str
            ):
                continue
            for block in _list_field(slice_data, "blocks"):
                if not isinstance(block, dict) or not isinstance(block.get("id"), str):
                    continue
                destinations[(part["id"], slice_data["id"], block["id"])] = block
    return destinations


def _course_destination_pointers(course: dict) -> Dict[Destination, str]:
    pointers: Dict[Destination, str] = {}
    for part_index, part in enumerate(_list_field(_course_payload(course), "parts")):
        if not isinstance(part, dict) or not isinstance(part.get("id"), str):
            continue
        for slice_index, slice_data in enumerate(_list_field(part, "slices")):
            if not isinstance(slice_data, dict) or not isinstance(
                slice_data.get("id"), str
            ):
                continue
            for block_index, block in enumerate(_list_field(slice_data, "blocks")):
                if not isinstance(block, dict) or not isinstance(block.get("id"), str):
                    continue
                destination = (part["id"], slice_data["id"], block["id"])
                pointers[destination] = (
                    f"/course/parts/{part_index}/slices/{slice_index}/blocks/{block_index}"
                )
    return pointers


def _course_document_path(root: Path) -> Path:
    return root / "course" / "course.json"


def _coverage_path(root: Path) -> Path:
    return root / ".course-work" / "source-coverage.json"


def _source_map_path(root: Path) -> Path:
    return root / ".course-work" / "course-runtime-source-map.json"


def _safe_json_load(
    root: Path,
    relative: str,
    *,
    required: bool,
) -> Tuple[Optional[object], Optional[ValidationIssue]]:
    current = root.absolute()
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            return None, _issue(relative, "symlink-file", "JSON evidence may not be a symlink")
    if not current.is_file():
        if required:
            return None, _issue(relative, "missing-file", "required JSON evidence is missing")
        return None, None
    try:
        return load_json(current), None
    except ValueError as exc:
        return None, _issue(relative, "invalid-json", str(exc))


def _course_shape_issue(document: object) -> Optional[ValidationIssue]:
    if not isinstance(document, dict):
        return _issue("course/course.json", "invalid-shape", "course document must be an object")
    if document.get("schemaVersion") != "2.0":
        return _issue("course/course.json", "invalid-shape", "course schemaVersion must be 2.0")
    course = document.get("course")
    if not isinstance(course, dict) or not isinstance(course.get("parts"), list):
        return _issue(
            "course/course.json",
            "invalid-shape",
            "course document must contain a course.parts list",
        )
    return None


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _v1_binding(
    destination: object,
    destinations: Dict[Destination, dict],
) -> Optional[dict]:
    if not isinstance(destination, str):
        return None
    pieces = destination.split("/")
    if len(pieces) != 3 or not all(pieces):
        return None
    part_id, legacy_piece_id, block_id = pieces
    target = (part_id, legacy_piece_id, block_id)
    if target not in destinations:
        return None
    return {
        "partId": part_id,
        "sliceId": legacy_piece_id,
        "blockId": block_id,
        "role": "migrated-legacy-destination",
    }


def migrate_coverage_v1(document: dict, course: dict) -> dict:
    """Return a v2 coverage document without discarding source locators."""
    if not isinstance(document, dict):
        raise ValueError("source coverage must be an object")
    if document.get("schemaVersion") == "2.0":
        return deepcopy(document)
    if document.get("schemaVersion") != "1.0":
        raise ValueError("source coverage schemaVersion must be 1.0 or 2.0")
    if not isinstance(document.get("items"), list):
        raise ValueError("source coverage v1 items must be a list")
    destinations = collect_course_destinations(course)
    migrated_items = []
    for item in document.get("items", []):
        if not isinstance(item, dict):
            migrated_items.append(deepcopy(item))
            continue
        migrated = deepcopy(item)
        status = item.get("status")
        approval_complete = (
            status == "discard-approved"
            and _nonempty_string(item.get("reason"))
            and _nonempty_string(item.get("decisionId"))
            and item.get("teacherConfirmed") is True
        )
        if status in {"mapped", "merged"}:
            disposition = "required-core"
        elif approval_complete:
            disposition = "exclude-approved"
        else:
            # A legacy unresolved/discard-proposed item remains an auditable,
            # unresolved proposal instead of being silently treated as excluded.
            disposition = "exclude-proposed"
        migrated.pop("status", None)
        migrated["disposition"] = disposition
        if isinstance(status, str):
            migrated["legacyStatus"] = status
        if disposition == "required-core":
            raw_destinations = item.get("destinations")
            legacy_destinations = (
                deepcopy(raw_destinations) if isinstance(raw_destinations, list) else []
            )
            bindings = []
            unmatched = []
            for destination in legacy_destinations:
                binding = _v1_binding(destination, destinations)
                if binding is None:
                    unmatched.append(destination)
                else:
                    bindings.append(binding)
            migrated["bindings"] = bindings
            if unmatched:
                migrated["migrationIssues"] = [
                    {"code": "unmatched-legacy-destination", "destination": value}
                    for value in unmatched
                ]
        if disposition == "exclude-proposed":
            migration_reason = (
                "Legacy source-coverage status needs resolution before publication: "
                f"{status if isinstance(status, str) else 'missing-status'}"
            )
            if not _nonempty_string(migrated.get("reason")):
                migrated["reason"] = migration_reason
            migrated["migrationReason"] = migration_reason
        migrated_items.append(migrated)
    migrated_document = deepcopy(document)
    migrated_document["schemaVersion"] = "2.0"
    migrated_document["items"] = migrated_items
    return migrated_document


def load_instructional_coverage(root: Path) -> dict:
    root = Path(root).absolute()
    coverage, issue = _safe_json_load(root, ".course-work/source-coverage.json", required=True)
    if issue is not None:
        raise ValueError(f"{issue.code}: {issue.path}")
    if not isinstance(coverage, dict):
        raise ValueError("source coverage must be an object")
    version = coverage.get("schemaVersion")
    if version == "2.0":
        return coverage
    if version != "1.0":
        raise ValueError(f"unsupported source coverage schemaVersion: {version}")
    course, course_issue = _safe_json_load(root, "course/course.json", required=True)
    if course_issue is not None:
        raise ValueError(f"{course_issue.code}: {course_issue.path}")
    if not isinstance(course, dict):
        raise ValueError("course document must be an object")
    return migrate_coverage_v1(coverage, course)


def _asset_sources_by_destination(course: dict) -> Dict[Destination, Set[str]]:
    indexed: Dict[Destination, Set[str]] = {}
    for reference in iter_asset_references(course):
        if not all(
            isinstance(value, str) and value
            for value in (reference.part_id, reference.slice_id, reference.block_id)
        ):
            continue
        destination = (
            reference.part_id,
            reference.slice_id,
            reference.block_id,
        )
        indexed.setdefault(destination, set()).add(reference.source)
    return indexed


def _source_map_matches(
    source_map: object,
    source_id: object,
    block_id: str,
    expected_pointer: str,
) -> Tuple[bool, bool]:
    if not isinstance(source_map, dict) or not isinstance(source_id, str):
        return False, False
    mappings = source_map.get("mappings")
    if not isinstance(mappings, list):
        return False, False
    pointer_mismatch = False
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        if mapping.get("targetId") != f"block:{block_id}":
            continue
        source_ids = mapping.get("sourceIds")
        if isinstance(source_ids, list) and source_id in source_ids:
            if mapping.get("runtimePointer") == expected_pointer:
                return True, False
            pointer_mismatch = True
    return False, pointer_mismatch


def _binding_references_source(
    item: dict,
    identity: Destination,
    block_id: str,
    asset_sources: Dict[Destination, Set[str]],
    source_map: object,
    expected_pointer: str,
) -> Tuple[bool, bool]:
    source_file = item.get("sourceFile")
    if isinstance(source_file, str) and source_file in asset_sources.get(identity, set()):
        return True, False
    source_id = item.get("sourceId")
    return _source_map_matches(
        source_map,
        source_id,
        block_id,
        expected_pointer,
    )


def _issue(path: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(path, code, message)


def _g5_issue(
    root: Path,
    course: dict,
    source_map: object,
) -> Optional[ValidationIssue]:
    blueprint, blueprint_issue = _safe_json_load(
        root, ".course-work/course-blueprint.json", required=True
    )
    if blueprint_issue is not None:
        return blueprint_issue
    report, report_issue = _safe_json_load(
        root, ".course-work/compilation-report.json", required=True
    )
    if report_issue is not None:
        return report_issue
    try:
        verify_compilation_evidence(blueprint, course, source_map, report)
    except CompilationEvidenceError as exc:
        if exc.code.startswith("source-map"):
            path = ".course-work/course-runtime-source-map.json"
        elif exc.code.startswith("compilation-report"):
            path = ".course-work/compilation-report.json"
        elif exc.code == "compilation-evidence-invalid":
            path = ".course-work/compilation-report.json"
        else:
            path = "course/course.json"
        return _issue(path, exc.code, str(exc))
    except CompilationToolError as exc:
        return _issue(
            ".course-work/compilation-report.json",
            "g5-evidence-unverifiable",
            str(exc),
        )
    return None


def audit_instructional_bindings(root: Path) -> BindingAudit:
    root = Path(root).absolute()
    blockers: List[ValidationIssue] = []
    warnings: List[ValidationIssue] = []
    coverage, coverage_issue = _safe_json_load(
        root, ".course-work/source-coverage.json", required=True
    )
    if coverage_issue is not None:
        return BindingAudit((coverage_issue,), ())
    if not isinstance(coverage, dict):
        return BindingAudit(
            (_issue(".course-work/source-coverage.json", "invalid-shape", "coverage must be an object"),),
            (),
        )
    version = coverage.get("schemaVersion")
    if version not in {"1.0", "2.0"}:
        return BindingAudit(
            (_issue(".course-work/source-coverage.json", "invalid-version", "coverage schemaVersion must be 1.0 or 2.0"),),
            (),
        )
    course, course_issue = _safe_json_load(root, "course/course.json", required=True)
    if course_issue is not None:
        return BindingAudit((course_issue,), ())
    course_shape_issue = _course_shape_issue(course)
    if course_shape_issue is not None:
        return BindingAudit((course_shape_issue,), ())
    assert isinstance(course, dict)
    if version == "1.0":
        try:
            coverage = migrate_coverage_v1(coverage, course)
        except ValueError as exc:
            return BindingAudit(
                (_issue(".course-work/source-coverage.json", "invalid-shape", str(exc)),),
                (),
            )
    source_map, source_map_issue = _safe_json_load(
        root, ".course-work/course-runtime-source-map.json", required=False
    )
    if source_map_issue is not None:
        blockers.append(source_map_issue)
    destinations = collect_course_destinations(course)
    destination_pointers = _course_destination_pointers(course)
    asset_sources = _asset_sources_by_destination(course)
    g5_checked = False
    g5_issue: Optional[ValidationIssue] = None

    def ensure_g5() -> Optional[ValidationIssue]:
        nonlocal g5_checked, g5_issue
        if not g5_checked:
            g5_checked = True
            g5_issue = _g5_issue(root, course, source_map)
        return g5_issue

    items = coverage.get("items") if isinstance(coverage, dict) else None
    if not isinstance(items, list):
        blockers.append(
            _issue("source-coverage.json.items", "coverage-items-required", "coverage items are required")
        )
        return BindingAudit(tuple(blockers), tuple(warnings))

    for index, item in enumerate(items):
        path = f"source-coverage.json.items[{index}]"
        if not isinstance(item, dict):
            blockers.append(_issue(path, "coverage-item-invalid", "coverage item must be an object"))
            continue
        for field in ("sourceId", "sourceFile", "location", "summary"):
            if not _nonempty_string(item.get(field)):
                blockers.append(
                    _issue(
                        f"{path}.{field}",
                        "source-field-required",
                        f"{field} is required for source traceability",
                    )
                )
        disposition = item.get("disposition")
        if disposition not in DISPOSITIONS:
            blockers.append(
                _issue(f"{path}.disposition", "invalid-disposition", "unsupported instructional disposition")
            )
            continue
        bindings = item.get("bindings")
        if bindings is None:
            bindings = []
        if not isinstance(bindings, list):
            blockers.append(_issue(f"{path}.bindings", "bindings-invalid", "bindings must be a list"))
            bindings = []
        if disposition in REQUIRED_DISPOSITIONS and not bindings:
            blockers.append(
                _issue(f"{path}.bindings", "required-binding-missing", "required material needs a learner binding")
            )
        if disposition == "optional-support" and not bindings and not _nonempty_string(item.get("reason")):
            blockers.append(
                _issue(f"{path}.reason", "optional-support-reason-missing", "unbound optional support needs a concrete non-use reason")
            )
        if disposition == "exclude-proposed":
            if not _nonempty_string(item.get("reason")):
                blockers.append(
                    _issue(f"{path}.reason", "exclude-proposed-reason-missing", "proposed exclusion needs a concrete reason")
                )
            warnings.append(
                _issue(path, "exclude-proposed", "proposed exclusion remains unresolved for publication")
            )
        if disposition == "exclude-approved":
            if not _nonempty_string(item.get("reason")):
                blockers.append(_issue(f"{path}.reason", "exclude-approved-reason-missing", "approved exclusion needs a concrete reason"))
            if not _nonempty_string(item.get("decisionId")):
                blockers.append(_issue(f"{path}.decisionId", "exclude-approved-decision-missing", "approved exclusion needs a decision ID"))
            if item.get("teacherConfirmed") is not True:
                blockers.append(_issue(f"{path}.teacherConfirmed", "exclude-approved-teacher-confirmation-missing", "approved exclusion needs explicit teacher confirmation"))

        for binding_index, binding in enumerate(bindings):
            binding_path = f"{path}.bindings[{binding_index}]"
            if not isinstance(binding, dict):
                blockers.append(_issue(binding_path, "binding-target-missing", "binding must name a Part, Slice, and Block"))
                continue
            identity = tuple(binding.get(field) for field in ("partId", "sliceId", "blockId"))
            if not all(isinstance(value, str) and value for value in identity):
                blockers.append(_issue(binding_path, "binding-target-missing", "binding must name a Part, Slice, and Block"))
                continue
            block = destinations.get(identity)  # type: ignore[arg-type]
            if block is None:
                blockers.append(_issue(binding_path, "binding-target-missing", "binding target does not exist in CourseDefinition 2.0"))
                continue
            source_referenced, pointer_mismatch = _binding_references_source(
                item,
                identity,  # type: ignore[arg-type]
                block["id"],
                asset_sources,
                source_map,
                destination_pointers[identity],  # type: ignore[index]
            )
            if pointer_mismatch:
                blockers.append(
                    _issue(
                        binding_path,
                        "source-map-pointer-mismatch",
                        "source-map runtimePointer does not identify the bound Block",
                    )
                )
            if source_referenced and (
                item.get("sourceFile") not in asset_sources.get(identity, set())
            ):
                evidence_issue = ensure_g5()
                if evidence_issue is not None:
                    blockers.append(evidence_issue)
                    source_referenced = False
            if not source_referenced:
                blockers.append(_issue(binding_path, "binding-source-unreferenced", "target Block does not contain or reference the declared source"))
    return BindingAudit(tuple(blockers), tuple(warnings))
