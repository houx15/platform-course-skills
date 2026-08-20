"""Hash-bound, source-grounded semantic audit records.

This module deliberately does not attempt to infer whether a course is
pedagogically sound.  It validates the *record* made by the Agent after a
source-grounded inspection, and binds that record to the exact approved page
plan, compiled CourseDefinition, source map, delivered asset set, and (where
needed) teacher decision record that it inspected.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import stat
from typing import Dict, List, Mapping, Set, Tuple

from .course_package_validation import (
    VALIDATION_REPORT_RELATIVE_PATH,
    build_course_validation_report,
)
from .decisions import DECISION_STORE_SCHEMA_VERSION
from .hashing import canonical_json_hash
from .instructional_plan import _plan_guard, verify_plan_approval
from .jsonio import dump_json
from .workflow import verify_g5_compilation


INSTRUCTIONAL_AUDIT_VERSION = "1.0"
INSTRUCTIONAL_AUDIT_RELATIVE_PATH = ".course-work/instructional-audit.json"
INSTRUCTIONAL_AUDIT_ANCHOR_RELATIVE_PATH = ".course-work/instructional-audit-anchor.json"
SEMANTIC_CHECKS = (
    "image-supports-assigned-claim",
    "question-answerable-from-declared-evidence",
    "deictic-reference-resolves",
    "required-reference-co-visible",
    "teacher-correctness-preserved",
    "source-claim-not-over-reduced",
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
)
_PAYLOAD_FIELDS = frozenset({"schemaVersion", "artifactHashes", "entries"})
_ENTRY_FIELDS = frozenset(
    {
        "partId",
        "sliceId",
        "check",
        "status",
        "sourceIds",
        "targetIds",
        "evidence",
        "plausibleArrangements",
        "decisionId",
        "reviewContextHash",
        "decisionRecordHash",
        "applicability",
        "notApplicableReason",
    }
)
_STATUS = frozenset({"pass", "blocker", "review"})
_MAX_EVIDENCE_CHARS = 1200
_MAX_ARRANGEMENT_CHARS = 800


class InstructionalAuditError(ValueError):
    """A semantic audit cannot be recorded or used as current evidence."""

    def __init__(self, code: str, message: str, *, path: str = INSTRUCTIONAL_AUDIT_RELATIVE_PATH) -> None:
        self.code = code
        self.path = path
        super().__init__(message)


def _nonempty(value: object, *, maximum: int = _MAX_EVIDENCE_CHARS) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _safe_root(root: Path) -> Path:
    requested = Path(root).absolute()
    # Keep the direct-root policy explicit, while resolving a symlink in an
    # *ancestor* before any evidence or candidate path is derived.  Otherwise
    # lexical containment below ``requested`` can be redirected after a check.
    if requested.is_symlink():
        raise InstructionalAuditError("symlink-root", "course root may not be a symlink", path=".")
    if not requested.is_dir():
        raise InstructionalAuditError("invalid-root", "course root must be an existing directory", path=".")
    root = requested.resolve()
    if not root.is_dir():  # Defensive: the ancestor chain may have changed.
        raise InstructionalAuditError("invalid-root", "course root must be an existing directory", path=".")
    return root


def _safe_json(root: Path, relative: str, *, required: bool = True) -> object | None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    directory_flags = flags | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(root, directory_flags)
    except OSError as exc:
        raise InstructionalAuditError("unsafe-evidence-root", "audit evidence root cannot be opened safely", path=relative) from exc
    try:
        for index, component in enumerate(Path(relative).parts):
            child_flags = flags if index == len(Path(relative).parts) - 1 else directory_flags
            try:
                child = os.open(component, child_flags, dir_fd=descriptor)
            except FileNotFoundError:
                if required:
                    raise InstructionalAuditError("missing-evidence", "required audit evidence is missing", path=relative)
                return None
            except OSError as exc:
                raise InstructionalAuditError("symlink-evidence", "audit evidence may not traverse a symlink", path=relative) from exc
            os.close(descriptor)
            descriptor = child
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise InstructionalAuditError("invalid-evidence", "audit evidence must be a regular file", path=relative)
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InstructionalAuditError("invalid-json", "audit evidence is not valid JSON", path=relative) from exc
    finally:
        os.close(descriptor)


def _decision_store_hash(root: Path) -> str:
    document = _safe_json(root, ".course-work/decisions.json", required=False)
    if document is None:
        # An audit with no review resolution may legitimately precede the
        # first decision record.  Hash the canonical empty store instead of
        # treating absence as an unbound special case.
        return canonical_json_hash({"schemaVersion": DECISION_STORE_SCHEMA_VERSION, "decisions": []})
    if not isinstance(document, dict) or document.get("schemaVersion") != DECISION_STORE_SCHEMA_VERSION or not isinstance(document.get("decisions"), list):
        raise InstructionalAuditError("invalid-decisions", "teacher decision record is invalid", path=".course-work/decisions.json")
    return canonical_json_hash(document)


def _current_artifact_hashes_at(root: Path) -> Tuple[Dict[str, str], dict, dict, dict, dict]:
    """Return trusted current evidence and its canonical identity hashes."""
    try:
        plan_evidence = verify_plan_approval(root)
    except Exception as exc:
        code = getattr(exc, "code", "plan-not-current")
        raise InstructionalAuditError(code, "approved page plan is missing, invalid, or stale", path=".course-work/course-storyboard.json") from exc

    try:
        verify_g5_compilation(root)
    except Exception as exc:
        raise InstructionalAuditError("compilation-not-current", "compiled course evidence is missing, invalid, or stale", path=".course-work/compilation-report.json") from exc

    plan = _safe_json(root, ".course-work/course-storyboard.json")
    coverage = _safe_json(root, ".course-work/source-coverage.json")
    blueprint = _safe_json(root, ".course-work/course-blueprint.json")
    course = _safe_json(root, "course/course.json")
    source_map = _safe_json(root, ".course-work/course-runtime-source-map.json")
    report = _safe_json(root, str(VALIDATION_REPORT_RELATIVE_PATH))
    if not all(isinstance(value, dict) for value in (plan, coverage, blueprint, course, source_map, report)):
        raise InstructionalAuditError("invalid-evidence-shape", "audit evidence documents must be JSON objects")

    # Task 4's report is the existing canonical owner of the byte-level asset
    # set.  Rebuild it before accepting its asset hash, so a changed image or
    # PDF cannot reuse a previous semantic observation.
    try:
        # G5 was verified immediately above; rebuilding the package report
        # with that fact avoids a duplicate compilation traversal.
        rebuilt = build_course_validation_report(root, verify_compilation=False)
    except Exception as exc:
        raise InstructionalAuditError("asset-evidence-invalid", "current asset evidence cannot be rebuilt", path=str(VALIDATION_REPORT_RELATIVE_PATH)) from exc
    if canonical_json_hash(report) != canonical_json_hash(rebuilt):
        raise InstructionalAuditError("asset-evidence-stale", "asset validation report is stale", path=str(VALIDATION_REPORT_RELATIVE_PATH))
    asset_set_hash = report.get("assetSetHash")
    if not isinstance(asset_set_hash, str) or not asset_set_hash:
        raise InstructionalAuditError("asset-evidence-invalid", "asset validation report has no asset set hash", path=str(VALIDATION_REPORT_RELATIVE_PATH))

    hashes = {
        "planContentHash": plan_evidence["planContentHash"],
        "materialsExtractedHash": plan_evidence["materialsExtractedHash"],
        "sourceCoverageHash": plan_evidence["sourceCoverageHash"],
        "blueprintHash": canonical_json_hash(blueprint),
        "courseDefinitionHash": canonical_json_hash(course),
        "sourceMapHash": canonical_json_hash(source_map),
        "assetSetHash": asset_set_hash,
        "decisionStoreHash": _decision_store_hash(root),
    }
    return hashes, plan, coverage, blueprint, course


def _current_artifact_hashes(root: Path) -> Tuple[Dict[str, str], dict, dict, dict, dict]:
    """Canonicalize once for public/private callers that do not already have it."""
    return _current_artifact_hashes_at(_safe_root(root))


def _slice_keys(plan: Mapping[str, object]) -> List[Tuple[str, str]]:
    keys: List[Tuple[str, str]] = []
    parts = plan.get("parts")
    if not isinstance(parts, list):
        return keys
    for part in parts:
        if not isinstance(part, dict) or not isinstance(part.get("partId"), str):
            continue
        slices = part.get("slices")
        if not isinstance(slices, list):
            continue
        for slice_data in slices:
            if isinstance(slice_data, dict) and isinstance(slice_data.get("sliceId"), str):
                keys.append((part["partId"], slice_data["sliceId"]))
    return keys


def _declared_plan_targets(plan: Mapping[str, object]) -> Dict[Tuple[str, str], Set[str]]:
    targets: Dict[Tuple[str, str], Set[str]] = {}
    for part in plan.get("parts", []) if isinstance(plan.get("parts"), list) else []:
        if not isinstance(part, dict) or not isinstance(part.get("partId"), str):
            continue
        for slice_data in part.get("slices", []) if isinstance(part.get("slices"), list) else []:
            if not isinstance(slice_data, dict) or not isinstance(slice_data.get("sliceId"), str):
                continue
            slice_targets = targets.setdefault((part["partId"], slice_data["sliceId"]), set())
            action = slice_data.get("learnerAction")
            if isinstance(action, dict) and isinstance(action.get("targetId"), str):
                slice_targets.add(action["targetId"])
            for field in ("coVisibleRequirements", "imageRelationships"):
                values = slice_data.get(field)
                if isinstance(values, list):
                    for value in values:
                        if isinstance(value, dict) and isinstance(value.get("targetId"), str):
                            slice_targets.add(value["targetId"])
    return targets


def _slice_known_ids(
    coverage: Mapping[str, object],
    plan: Mapping[str, object],
    course: Mapping[str, object],
) -> Dict[Tuple[str, str], Tuple[Set[str], Set[str]]]:
    """Return only sources and targets that actually belong to each Slice."""
    source_bindings: Dict[Tuple[str, str], Set[str]] = {}
    for item in coverage.get("items", []) if isinstance(coverage.get("items"), list) else []:
        if isinstance(item, dict) and isinstance(item.get("sourceId"), str):
            for binding in item.get("bindings", []) if isinstance(item.get("bindings"), list) else []:
                if isinstance(binding, dict) and isinstance(binding.get("partId"), str) and isinstance(binding.get("sliceId"), str):
                    source_bindings.setdefault((binding["partId"], binding["sliceId"]), set()).add(item["sourceId"])

    planned_sources: Dict[Tuple[str, str], Set[str]] = {}
    for part in plan.get("parts", []) if isinstance(plan.get("parts"), list) else []:
        if not isinstance(part, dict) or not isinstance(part.get("partId"), str):
            continue
        for slice_data in part.get("slices", []) if isinstance(part.get("slices"), list) else []:
            if not isinstance(slice_data, dict) or not isinstance(slice_data.get("sliceId"), str):
                continue
            key = (part["partId"], slice_data["sliceId"])
            planned_sources[key] = {
                source_use["sourceId"]
                for source_use in slice_data.get("sourceUses", []) if isinstance(slice_data.get("sourceUses"), list)
                if isinstance(source_use, dict) and isinstance(source_use.get("sourceId"), str)
            }

    targets = _declared_plan_targets(plan)
    course_data = course.get("course") if isinstance(course.get("course"), dict) else {}
    for part in course_data.get("parts", []) if isinstance(course_data.get("parts"), list) else []:
        if not isinstance(part, dict) or not isinstance(part.get("id"), str):
            continue
        for slice_data in part.get("slices", []) if isinstance(part.get("slices"), list) else []:
            if not isinstance(slice_data, dict) or not isinstance(slice_data.get("id"), str):
                continue
            key = (part["id"], slice_data["id"])
            slice_targets = targets.setdefault(key, set())
            for block in slice_data.get("blocks", []) if isinstance(slice_data.get("blocks"), list) else []:
                if isinstance(block, dict) and isinstance(block.get("id"), str):
                    slice_targets.add(f"block:{block['id']}")
    return {
        key: (planned_sources.get(key, set()).intersection(source_bindings.get(key, set())), targets.get(key, set()))
        for key in set(planned_sources).union(targets)
    }


def _review_context_hash(entry: Mapping[str, object], artifact_hashes: Mapping[str, str]) -> str:
    """Stable decision context, intentionally excluding mutable decision bytes."""
    relevant_hashes = {key: value for key, value in artifact_hashes.items() if key != "decisionStoreHash"}
    return canonical_json_hash(
        {
            "artifactHashes": relevant_hashes,
            "partId": entry["partId"],
            "sliceId": entry["sliceId"],
            "check": entry["check"],
            "sourceIds": entry["sourceIds"],
            "targetIds": entry["targetIds"],
            "evidence": entry["evidence"],
            "plausibleArrangements": entry["plausibleArrangements"],
        }
    )


def _validate_entry(
    value: object,
    *,
    index: int,
    slice_keys: Set[Tuple[str, str]],
    slice_ids: Mapping[Tuple[str, str], Tuple[Set[str], Set[str]]],
    allow_pending_resolution: bool,
) -> dict:
    path = f"entries[{index}]"
    if not isinstance(value, dict):
        raise InstructionalAuditError("entry-invalid", "audit entry must be an object", path=path)
    unknown = sorted(set(value).difference(_ENTRY_FIELDS))
    if unknown:
        raise InstructionalAuditError("unknown-field", f"unsupported audit entry field: {unknown[0]}", path=path)
    required = {"partId", "sliceId", "check", "status", "sourceIds", "targetIds", "evidence", "applicability"}
    missing = sorted(required.difference(value))
    if missing:
        raise InstructionalAuditError("entry-field-required", f"audit entry is missing {missing[0]}", path=path)
    part_id, slice_id = value.get("partId"), value.get("sliceId")
    if not isinstance(part_id, str) or not isinstance(slice_id, str) or (part_id, slice_id) not in slice_keys:
        raise InstructionalAuditError("unknown-slice", "audit entry must name a planned Part/Slice", path=path)
    check = value.get("check")
    if check not in SEMANTIC_CHECKS:
        raise InstructionalAuditError("unknown-check", "audit entry uses an unsupported semantic check", path=f"{path}.check")
    status = value.get("status")
    if status not in _STATUS:
        raise InstructionalAuditError("unsupported-status", "audit status must be pass, blocker, or review", path=f"{path}.status")
    evidence = value.get("evidence")
    if not _nonempty(evidence):
        raise InstructionalAuditError("evidence-required", "audit evidence must be concise nonempty source/course-grounded text", path=f"{path}.evidence")

    applicability = value.get("applicability")
    if applicability not in {"applicable", "not-applicable"}:
        raise InstructionalAuditError("applicability-required", "audit entry must explicitly state whether the check applies", path=f"{path}.applicability")
    normalized: dict = {
        "partId": part_id,
        "sliceId": slice_id,
        "check": check,
        "status": status,
        "applicability": applicability,
    }
    known_source_ids, known_target_ids = slice_ids.get((part_id, slice_id), (set(), set()))
    for field, known, code in (("sourceIds", known_source_ids, "source-not-in-slice"), ("targetIds", known_target_ids, "target-not-in-slice")):
        ids = value.get(field)
        if not isinstance(ids, list) or not all(isinstance(item, str) and item for item in ids):
            raise InstructionalAuditError("stable-ids-required", f"{field} must be a list of stable IDs", path=f"{path}.{field}")
        if applicability == "applicable" and not ids:
            raise InstructionalAuditError("stable-ids-required", f"{field} must be nonempty when the check applies", path=f"{path}.{field}")
        if applicability == "not-applicable" and ids:
            raise InstructionalAuditError("not-applicable-ids", f"{field} must be empty only for a genuinely non-applicable check", path=f"{path}.{field}")
        if len(ids) != len(set(ids)):
            raise InstructionalAuditError("duplicate-id", f"{field} must not contain duplicate IDs", path=f"{path}.{field}")
        unknown_id = next((item for item in ids if item not in known), None)
        if unknown_id is not None:
            raise InstructionalAuditError(code, f"{field} contains an unknown current ID", path=f"{path}.{field}")
        normalized[field] = sorted(ids)
    normalized["evidence"] = evidence.strip()

    reason = value.get("notApplicableReason")
    if applicability == "not-applicable":
        if status != "pass" or not _nonempty(reason):
            raise InstructionalAuditError("not-applicable-reason-required", "a non-applicable check needs a concise reason and pass status", path=path)
        if any(value.get(field) is not None for field in ("plausibleArrangements", "decisionId", "reviewContextHash", "decisionRecordHash")):
            raise InstructionalAuditError("status-field-invalid", "a non-applicable check may not carry review fields", path=path)
        normalized["notApplicableReason"] = reason.strip()
        return normalized
    if reason is not None:
        raise InstructionalAuditError("status-field-invalid", "notApplicableReason is allowed only for non-applicable checks", path=path)

    arrangements = value.get("plausibleArrangements")
    decision_id = value.get("decisionId")
    review_context_hash = value.get("reviewContextHash")
    decision_record_hash = value.get("decisionRecordHash")
    if status == "review":
        if not isinstance(arrangements, list) or len(arrangements) != 2 or not all(_nonempty(item, maximum=_MAX_ARRANGEMENT_CHARS) for item in arrangements):
            raise InstructionalAuditError("review-arrangements-required", "a review needs exactly two concrete plausible arrangements", path=f"{path}.plausibleArrangements")
        normalized_arrangements = [item.strip() for item in arrangements]
        if normalized_arrangements[0] == normalized_arrangements[1]:
            raise InstructionalAuditError("review-arrangements-required", "review arrangements must be genuinely distinct", path=f"{path}.plausibleArrangements")
        if decision_id is not None or review_context_hash is not None or decision_record_hash is not None:
            raise InstructionalAuditError("review-unresolved", "a review remains unresolved until a later teacher decision records pass", path=f"{path}.decisionId")
        normalized["plausibleArrangements"] = normalized_arrangements
    elif status == "pass":
        resolution_fields = (arrangements, decision_id, review_context_hash, decision_record_hash)
        if all(value is None for value in resolution_fields):
            return normalized
        if (
            isinstance(decision_id, str)
            and decision_id.strip()
            and arrangements is None
            and review_context_hash is None
            and decision_record_hash is None
            and allow_pending_resolution
        ):
            normalized["decisionId"] = decision_id.strip()
            return normalized
        if (
            not isinstance(arrangements, list)
            or len(arrangements) != 2
            or not all(_nonempty(item, maximum=_MAX_ARRANGEMENT_CHARS) for item in arrangements)
            or not isinstance(decision_id, str)
            or not decision_id.strip()
            or not isinstance(review_context_hash, str)
            or not review_context_hash
            or not isinstance(decision_record_hash, str)
            or not decision_record_hash
        ):
            raise InstructionalAuditError("resolution-provenance-required", "a resolved review pass must retain its arrangements and decision provenance", path=path)
        normalized_arrangements = [item.strip() for item in arrangements]
        if normalized_arrangements[0] == normalized_arrangements[1]:
            raise InstructionalAuditError("review-arrangements-required", "review arrangements must be genuinely distinct", path=f"{path}.plausibleArrangements")
        normalized.update(
            {
                "plausibleArrangements": normalized_arrangements,
                "decisionId": decision_id.strip(),
                "reviewContextHash": review_context_hash,
                "decisionRecordHash": decision_record_hash,
            }
        )
    else:
        if any(value is not None for value in (arrangements, decision_id, review_context_hash, decision_record_hash)):
            raise InstructionalAuditError("status-field-invalid", "blocker entries may not carry review resolution fields", path=path)
    return normalized


def _validate_payload(
    payload: object,
    *,
    hashes: Mapping[str, str],
    plan: Mapping[str, object],
    coverage: Mapping[str, object],
    blueprint: Mapping[str, object],
    course: Mapping[str, object],
    allow_pending_resolution: bool = False,
) -> dict:
    if not isinstance(payload, dict):
        raise InstructionalAuditError("invalid-payload", "audit payload must be an object")
    unknown = sorted(set(payload).difference(_PAYLOAD_FIELDS))
    if unknown:
        raise InstructionalAuditError("unknown-field", f"unsupported audit field: {unknown[0]}")
    if set(payload) != _PAYLOAD_FIELDS or payload.get("schemaVersion") != INSTRUCTIONAL_AUDIT_VERSION:
        raise InstructionalAuditError("invalid-version", "audit payload must use the closed 1.0 schema")
    reported_hashes = payload.get("artifactHashes")
    if not isinstance(reported_hashes, dict) or set(reported_hashes) != set(_HASH_FIELDS):
        raise InstructionalAuditError("hashes-required", "audit payload must bind every current artifact hash", path="artifactHashes")
    if any(not isinstance(reported_hashes.get(field), str) for field in _HASH_FIELDS):
        raise InstructionalAuditError("hashes-invalid", "audit artifact hashes must be strings", path="artifactHashes")
    if dict(reported_hashes) != dict(hashes):
        raise InstructionalAuditError("audit-stale", "audit payload hashes do not match current course evidence", path="artifactHashes")

    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise InstructionalAuditError("entries-required", "audit payload entries must be a list", path="entries")
    ordered_slices = _slice_keys(plan)
    slice_set = set(ordered_slices)
    slice_ids = _slice_known_ids(coverage, plan, course)
    normalized = [
        _validate_entry(
            entry,
            index=index,
            slice_keys=slice_set,
            slice_ids=slice_ids,
            allow_pending_resolution=allow_pending_resolution,
        )
        for index, entry in enumerate(entries)
    ]
    # N/A is deliberately narrow: it is only a representation for a Slice
    # that has no source evidence or no stable course/plan target at all.  It
    # cannot be used to waive a check that has both sides available for audit.
    for entry in normalized:
        if entry["applicability"] != "not-applicable":
            continue
        sources, targets = slice_ids.get((entry["partId"], entry["sliceId"]), (set(), set()))
        if sources and targets:
            raise InstructionalAuditError("not-applicable-not-justified", "a check with current sources and targets must be audited", path="entries")
    expected = {(part_id, slice_id, check) for part_id, slice_id in ordered_slices for check in SEMANTIC_CHECKS}
    actual = [(entry["partId"], entry["sliceId"], entry["check"]) for entry in normalized]
    if len(actual) != len(set(actual)):
        raise InstructionalAuditError("duplicate-check-coverage", "each Slice/check pair must occur exactly once", path="entries")
    if set(actual) != expected:
        raise InstructionalAuditError("slice-check-coverage", "every planned Slice must have every semantic check exactly once", path="entries")
    slice_rank = {value: index for index, value in enumerate(ordered_slices)}
    check_rank = {value: index for index, value in enumerate(SEMANTIC_CHECKS)}
    normalized.sort(key=lambda entry: (slice_rank[(entry["partId"], entry["sliceId"])], check_rank[entry["check"]]))
    return {
        "schemaVersion": INSTRUCTIONAL_AUDIT_VERSION,
        "artifactHashes": dict(hashes),
        "entries": normalized,
    }


def _same_semantic_context(old: Mapping[str, object], new_hashes: Mapping[str, str]) -> bool:
    hashes = old.get("artifactHashes")
    if not isinstance(hashes, dict):
        return False
    return all(hashes.get(field) == new_hashes[field] for field in _HASH_FIELDS if field != "decisionStoreHash")


def _existing_entries(root: Path) -> dict[Tuple[str, str, str], dict]:
    existing = _safe_json(root, INSTRUCTIONAL_AUDIT_RELATIVE_PATH, required=False)
    if not isinstance(existing, dict):
        return {}
    entries = existing.get("entries")
    if not isinstance(entries, list):
        return {}
    result: dict[Tuple[str, str, str], dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = (entry.get("partId"), entry.get("sliceId"), entry.get("check"))
        if all(isinstance(value, str) for value in key):
            result[key] = entry
    return result


def _audit_anchor(report: Mapping[str, object]) -> dict:
    """Small tamper-evident companion to the mutable human-readable report."""
    entries = report.get("entries")
    if not isinstance(entries, list):
        raise InstructionalAuditError("invalid-payload", "audit report has no entries")
    return {
        "schemaVersion": INSTRUCTIONAL_AUDIT_VERSION,
        "reportHash": canonical_json_hash(report),
        "entries": [
            {
                "partId": entry["partId"],
                "sliceId": entry["sliceId"],
                "check": entry["check"],
                "entryHash": canonical_json_hash(entry),
            }
            for entry in entries
        ],
    }


def _validate_existing_anchor(root: Path, report: Mapping[str, object], *, required: bool) -> None:
    anchor = _safe_json(root, INSTRUCTIONAL_AUDIT_ANCHOR_RELATIVE_PATH, required=required)
    if anchor is None and not required:
        return
    if not isinstance(anchor, dict) or anchor != _audit_anchor(report):
        raise InstructionalAuditError("audit-anchor-mismatch", "instructional audit was changed outside its atomic lifecycle record", path=INSTRUCTIONAL_AUDIT_ANCHOR_RELATIVE_PATH)


def _write_audit_documents(root: Path, report: Mapping[str, object]) -> None:
    """Descriptor-relative atomic replacement; parent and leaf symlinks never follow."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    directory_flags = flags | getattr(os, "O_DIRECTORY", 0)
    root_fd = os.open(root, directory_flags)
    work_fd = None
    temporary_names: List[str] = []
    try:
        work_fd = os.open(".course-work", directory_flags, dir_fd=root_fd)
        if not stat.S_ISDIR(os.fstat(work_fd).st_mode):
            raise InstructionalAuditError("unsafe-destination", "audit destination directory is unsafe", path=".course-work")
        documents = (
            ("instructional-audit.json", report),
            ("instructional-audit-anchor.json", _audit_anchor(report)),
        )
        prepared: List[Tuple[str, str]] = []
        for name, document in documents:
            try:
                existing = os.stat(name, dir_fd=work_fd, follow_symlinks=False)
                if stat.S_ISLNK(existing.st_mode):
                    raise InstructionalAuditError("symlink-evidence", "audit destination may not be a symlink", path=f".course-work/{name}")
                mode = stat.S_IMODE(existing.st_mode)
            except FileNotFoundError:
                mode = 0o644
            temporary = f".{name}.{secrets.token_hex(16)}.tmp"
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), mode, dir_fd=work_fd)
            temporary_names.append(temporary)
            try:
                content = dump_json(document).encode("utf-8")
                os.write(fd, content)
                os.fsync(fd)
            finally:
                os.close(fd)
            prepared.append((temporary, name))
        # Rename never follows the destination.  A race that replaces it with
        # a symlink is safe (the link itself is atomically replaced).
        for temporary, name in prepared:
            os.rename(temporary, name, src_dir_fd=work_fd, dst_dir_fd=work_fd)
            temporary_names.remove(temporary)
        try:
            os.fsync(work_fd)
        except OSError:
            pass
    except InstructionalAuditError:
        raise
    except OSError as exc:
        raise InstructionalAuditError("unsafe-destination", "audit destination cannot be written safely", path=".course-work") from exc
    finally:
        if work_fd is not None:
            for temporary in temporary_names:
                try:
                    os.unlink(temporary, dir_fd=work_fd)
                except OSError:
                    pass
            os.close(work_fd)
        os.close(root_fd)


def _confirmed_review_decision(
    root: Path,
    *,
    decision_id: str,
    arrangements: List[str],
    context_hash: str,
) -> str:
    """Validate the concrete teacher decision without loose model coercion."""
    document = _safe_json(root, ".course-work/decisions.json", required=False)
    if document is None:
        raise InstructionalAuditError("review-decision-missing", "a review cannot become pass without a confirmed teacher decision", path=".course-work/decisions.json")
    if not isinstance(document, dict) or document.get("schemaVersion") != DECISION_STORE_SCHEMA_VERSION or not isinstance(document.get("decisions"), list):
        raise InstructionalAuditError("invalid-decisions", "teacher decision record is invalid", path=".course-work/decisions.json")
    matches = [item for item in document["decisions"] if isinstance(item, dict) and item.get("id") == decision_id]
    if len(matches) != 1:
        raise InstructionalAuditError("review-decision-missing", "review resolution names no current teacher decision", path=".course-work/decisions.json")
    decision = matches[0]
    if decision.get("status") != "confirmed":
        raise InstructionalAuditError("review-decision-unconfirmed", "review resolution requires an explicit confirmed teacher decision", path=".course-work/decisions.json")
    if not _nonempty(decision.get("question")) or not _nonempty(decision.get("decidedAt")) or not _nonempty(decision.get("answer")):
        raise InstructionalAuditError("review-decision-invalid", "teacher decision needs a substantive question, answer, and decision time", path=".course-work/decisions.json")
    if decision.get("contextHash") != context_hash:
        raise InstructionalAuditError("review-decision-stale", "teacher decision does not bind this exact semantic review", path=".course-work/decisions.json")
    if decision["answer"].strip() not in arrangements:
        raise InstructionalAuditError("review-decision-answer-invalid", "teacher decision answer must choose one recorded plausible arrangement", path=".course-work/decisions.json")
    return canonical_json_hash(decision)


def _validate_resolved_passes(root: Path, report: Mapping[str, object], hashes: Mapping[str, str]) -> None:
    for entry in report["entries"]:
        if entry["status"] != "pass" or "decisionId" not in entry:
            continue
        expected_context_hash = _review_context_hash(entry, hashes)
        if entry.get("reviewContextHash") != expected_context_hash:
            raise InstructionalAuditError("review-context-stale", "resolved review context does not match current semantic evidence", path="entries")
        actual_decision_hash = _confirmed_review_decision(
            root,
            decision_id=entry["decisionId"],
            arrangements=entry["plausibleArrangements"],
            context_hash=entry["reviewContextHash"],
        )
        if entry.get("decisionRecordHash") != actual_decision_hash:
            raise InstructionalAuditError("review-decision-changed", "bound teacher decision has changed since the review was resolved", path="entries")


def _validate_lifecycle(root: Path, report: Mapping[str, object], hashes: Mapping[str, str]) -> None:
    previous_document = _safe_json(root, INSTRUCTIONAL_AUDIT_RELATIVE_PATH, required=False)
    if not isinstance(previous_document, dict) or not _same_semantic_context(previous_document, hashes):
        return
    previous = _existing_entries(root)
    for entry in report["entries"]:
        key = (entry["partId"], entry["sliceId"], entry["check"])
        old = previous.get(key)
        if entry["status"] == "pass" and "decisionId" in entry and old is None:
            raise InstructionalAuditError(
                "status-field-invalid",
                "decision ID may resolve only an earlier review",
                path="entries",
            )
        if old is None:
            continue
        old_status = old.get("status")
        new_status = entry["status"]
        if old_status == "blocker" and new_status != "blocker":
            raise InstructionalAuditError("blocker-downgrade-forbidden", "a current semantic blocker cannot be waived or downgraded", path="entries")
        if old_status == "review" and new_status == "pass":
            decision_id = entry.get("decisionId")
            if not isinstance(decision_id, str):
                raise InstructionalAuditError("review-decision-missing", "a review cannot become pass without a teacher decision", path="entries")
            arrangements = old.get("plausibleArrangements")
            if not isinstance(arrangements, list) or not all(isinstance(item, str) for item in arrangements):
                raise InstructionalAuditError("review-arrangements-required", "previous review has no valid alternatives", path="entries")
            context_hash = _review_context_hash(old, hashes)
            decision_hash = _confirmed_review_decision(
                root,
                decision_id=decision_id,
                arrangements=arrangements,
                context_hash=context_hash,
            )
            entry.update(
                {
                    "plausibleArrangements": arrangements,
                    "reviewContextHash": context_hash,
                    "decisionRecordHash": decision_hash,
                }
            )
        elif old_status == "pass" and new_status == "pass" and "decisionId" in old:
            required = ("decisionId", "plausibleArrangements", "reviewContextHash", "decisionRecordHash")
            if any(entry.get(field) != old.get(field) for field in required):
                raise InstructionalAuditError("review-provenance-lost", "a resolved review pass must preserve its exact teacher decision binding", path="entries")


def record_instructional_audit(root: Path, payload: dict) -> dict:
    """Validate and atomically replace the semantic audit for ``root``.

    Validation intentionally happens before the one destination write.  A bad
    candidate therefore leaves an earlier valid report byte-for-byte intact.
    """
    root = _safe_root(root)
    # The same per-course guard used for plan mutations gives recorders a
    # process-wide compare-and-swap boundary.  Critically, evidence and the
    # prior lifecycle state are re-read *inside* the guard.
    with _plan_guard(root):
        hashes, plan, coverage, blueprint, course = _current_artifact_hashes_at(root)
        previous = _safe_json(root, INSTRUCTIONAL_AUDIT_RELATIVE_PATH, required=False)
        if previous is not None:
            if not isinstance(previous, dict):
                raise InstructionalAuditError("invalid-payload", "previous instructional audit is invalid")
            _validate_existing_anchor(root, previous, required=True)
        report = _validate_payload(payload, hashes=hashes, plan=plan, coverage=coverage, blueprint=blueprint, course=course, allow_pending_resolution=True)
        _validate_lifecycle(root, report, hashes)
        report = _validate_payload(report, hashes=hashes, plan=plan, coverage=coverage, blueprint=blueprint, course=course)
        _validate_resolved_passes(root, report, hashes)
        _write_audit_documents(root, report)
        return report


def verify_instructional_audit(root: Path) -> Dict[str, str]:
    """Return current gate evidence, or fail closed for stale/blocking audit."""
    root = _safe_root(root)
    hashes, plan, coverage, blueprint, course = _current_artifact_hashes_at(root)
    payload = _safe_json(root, INSTRUCTIONAL_AUDIT_RELATIVE_PATH)
    if not isinstance(payload, dict):
        raise InstructionalAuditError("invalid-payload", "instructional audit must be an object")
    _validate_existing_anchor(root, payload, required=True)
    report = _validate_payload(payload, hashes=hashes, plan=plan, coverage=coverage, blueprint=blueprint, course=course)
    _validate_resolved_passes(root, report, hashes)
    blockers = [entry for entry in report["entries"] if entry["status"] == "blocker"]
    if blockers:
        raise InstructionalAuditError("semantic-audit-blocked", "semantic audit contains one or more blockers")
    return {"instructionalAuditHash": canonical_json_hash(report), **hashes}
