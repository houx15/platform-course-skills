"""Source-coverage v2 loading, migration, and CourseDefinition bindings."""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .course_compiler import canonical_json_hash
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


def collect_course_destinations(course: dict) -> Dict[Destination, dict]:
    """Collect only real CourseDefinition 2.0 Part/Slice/Block targets."""
    destinations: Dict[Destination, dict] = {}
    for part in _course_payload(course).get("parts", []):
        if not isinstance(part, dict) or not isinstance(part.get("id"), str):
            continue
        for slice_data in part.get("slices", []):
            if not isinstance(slice_data, dict) or not isinstance(
                slice_data.get("id"), str
            ):
                continue
            for block in slice_data.get("blocks", []):
                if not isinstance(block, dict) or not isinstance(block.get("id"), str):
                    continue
                destinations[(part["id"], slice_data["id"], block["id"])] = block
    return destinations


def _course_destination_pointers(course: dict) -> Dict[Destination, str]:
    pointers: Dict[Destination, str] = {}
    for part_index, part in enumerate(_course_payload(course).get("parts", [])):
        if not isinstance(part, dict) or not isinstance(part.get("id"), str):
            continue
        for slice_index, slice_data in enumerate(part.get("slices", [])):
            if not isinstance(slice_data, dict) or not isinstance(
                slice_data.get("id"), str
            ):
                continue
            for block_index, block in enumerate(slice_data.get("blocks", [])):
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
    destinations = collect_course_destinations(course)
    migrated_items = []
    for item in document.get("items", []):
        if not isinstance(item, dict):
            migrated_items.append(item)
            continue
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
        migrated = {
            key: item[key]
            for key in ("sourceId", "sourceFile", "location", "summary")
            if key in item
        }
        migrated["disposition"] = disposition
        if isinstance(status, str):
            migrated["legacyStatus"] = status
        if disposition == "required-core":
            bindings = [
                binding
                for destination in item.get("destinations", [])
                if (binding := _v1_binding(destination, destinations)) is not None
            ]
            migrated["bindings"] = bindings
        for key in ("reason", "decisionId", "teacherConfirmed"):
            if key in item:
                migrated[key] = item[key]
        if disposition == "exclude-proposed":
            migration_reason = (
                "Legacy source-coverage status needs resolution before publication: "
                f"{status if isinstance(status, str) else 'missing-status'}"
            )
            if not _nonempty_string(migrated.get("reason")):
                migrated["reason"] = migration_reason
            migrated["migrationReason"] = migration_reason
        migrated_items.append(migrated)
    return {"schemaVersion": "2.0", "items": migrated_items}


def load_instructional_coverage(root: Path) -> dict:
    root = root.resolve()
    coverage = load_json(_coverage_path(root))
    if not isinstance(coverage, dict):
        raise ValueError("source coverage must be an object")
    version = coverage.get("schemaVersion")
    if version == "2.0":
        return coverage
    if version != "1.0":
        raise ValueError(f"unsupported source coverage schemaVersion: {version}")
    course = load_json(_course_document_path(root))
    if not isinstance(course, dict):
        raise ValueError("course document must be an object")
    return migrate_coverage_v1(coverage, course)


def _walk_strings(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_strings(child)


def _source_map_matches(
    source_map: object,
    source_id: object,
    block_id: str,
    expected_pointer: str,
    expected_hash: str,
) -> Tuple[bool, bool]:
    if not isinstance(source_map, dict) or not isinstance(source_id, str):
        return False, False
    if source_map.get("courseDefinitionHash") != expected_hash:
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
    block: dict,
    source_map: object,
    expected_pointer: str,
    expected_hash: str,
) -> Tuple[bool, bool]:
    source_file = item.get("sourceFile")
    if isinstance(source_file, str) and source_file in set(_walk_strings(block)):
        return True, False
    source_id = item.get("sourceId")
    if isinstance(source_id, str) and source_id in set(_walk_strings(block)):
        return True, False
    return _source_map_matches(
        source_map,
        source_id,
        block.get("id", ""),
        expected_pointer,
        expected_hash,
    )


def _issue(path: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(path, code, message)


def _load_optional_json(path: Path, blockers: List[ValidationIssue], code: str) -> object:
    if not path.is_file():
        return None
    try:
        return load_json(path)
    except ValueError as exc:
        blockers.append(_issue(str(path), code, str(exc)))
        return None


def audit_instructional_bindings(root: Path) -> BindingAudit:
    root = root.resolve()
    blockers: List[ValidationIssue] = []
    warnings: List[ValidationIssue] = []
    try:
        coverage = load_instructional_coverage(root)
    except ValueError as exc:
        return BindingAudit(
            blockers=(_issue("source-coverage.json", "coverage-unavailable", str(exc)),),
            warnings=(),
        )
    course = _load_optional_json(
        _course_document_path(root), blockers, "course-document-unavailable"
    )
    source_map = _load_optional_json(
        _source_map_path(root), blockers, "source-map-invalid"
    )
    destinations = collect_course_destinations(course) if isinstance(course, dict) else {}
    destination_pointers = (
        _course_destination_pointers(course) if isinstance(course, dict) else {}
    )
    expected_hash = canonical_json_hash(course) if isinstance(course, dict) else ""
    if source_map is not None and (
        not isinstance(source_map, dict)
        or source_map.get("courseDefinitionHash") != expected_hash
    ):
        blockers.append(
            _issue(
                "course-runtime-source-map.json",
                "source-map-stale",
                "source map does not match the current CourseDefinition hash",
            )
        )
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
                block,
                source_map,
                destination_pointers[identity],  # type: ignore[index]
                expected_hash,
            )
            if pointer_mismatch:
                blockers.append(
                    _issue(
                        binding_path,
                        "source-map-pointer-mismatch",
                        "source-map runtimePointer does not identify the bound Block",
                    )
                )
            if not source_referenced:
                blockers.append(_issue(binding_path, "binding-source-unreferenced", "target Block does not contain or reference the declared source"))
    return BindingAudit(tuple(blockers), tuple(warnings))
