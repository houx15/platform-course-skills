from typing import List, Optional, Set

from .errors import ValidationIssue


ALLOWED_STATUSES = {
    "unresolved",
    "mapped",
    "merged",
    "discard-proposed",
    "discard-approved",
}


def validate_coverage(
    data: object,
    valid_destinations: Optional[Set[str]] = None,
) -> List[ValidationIssue]:
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return [
            ValidationIssue(
                "items",
                "required",
                "coverage items are required",
            )
        ]
    issues: List[ValidationIssue] = []
    for index, item in enumerate(data["items"]):
        path = f"items[{index}]"
        if not isinstance(item, dict):
            issues.append(ValidationIssue(path, "required", "coverage item must be an object"))
            continue
        if not isinstance(item.get("sourceId"), str) or not item["sourceId"].strip():
            issues.append(
                ValidationIssue(f"{path}.sourceId", "required", "sourceId is required")
            )
        for field in ("sourceFile", "location", "summary"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                issues.append(
                    ValidationIssue(
                        f"{path}.{field}",
                        "required",
                        f"{field} is required for source traceability",
                    )
                )
        status = item.get("status")
        if status not in ALLOWED_STATUSES:
            issues.append(
                ValidationIssue(
                    f"{path}.status",
                    "invalid-status",
                    f"unsupported status: {status}",
                )
            )
        elif status in {"unresolved", "discard-proposed"}:
            issues.append(
                ValidationIssue(path, status, "source item has not been resolved")
            )
        elif status in {"mapped", "merged"} and (
            not isinstance(item.get("destinations"), list)
            or not item["destinations"]
        ):
            issues.append(
                ValidationIssue(
                    f"{path}.destinations",
                    "missing-destination",
                    "resolved source item needs a destination",
                )
            )
        elif status in {"mapped", "merged"} and valid_destinations is not None:
            for destination_index, destination in enumerate(item["destinations"]):
                if destination not in valid_destinations:
                    issues.append(
                        ValidationIssue(
                            f"{path}.destinations[{destination_index}]",
                            "unknown-destination",
                            f"course block does not exist: {destination}",
                        )
                    )
        elif status == "discard-approved":
            if item.get("teacherConfirmed") is not True:
                issues.append(
                    ValidationIssue(
                        f"{path}.teacherConfirmed",
                        "unconfirmed-discard",
                        "discard needs teacher confirmation",
                    )
                )
            if not isinstance(item.get("reason"), str) or not item["reason"].strip():
                issues.append(
                    ValidationIssue(
                        f"{path}.reason",
                        "required",
                        "approved discard needs a reason",
                    )
                )
    return issues


def validate_coverage_inventory(
    extracted: object,
    coverage: object,
) -> List[ValidationIssue]:
    if not isinstance(extracted, dict) or not isinstance(extracted.get("items"), list):
        return [
            ValidationIssue(
                "materials-extracted.json",
                "required",
                "extracted material items are required",
            )
        ]
    if not isinstance(coverage, dict) or not isinstance(coverage.get("items"), list):
        return []

    issues: List[ValidationIssue] = []
    extracted_by_id = {}
    for index, item in enumerate(extracted["items"]):
        if not isinstance(item, dict):
            continue
        source_id = item.get("sourceId")
        if not isinstance(source_id, str):
            continue
        if source_id in extracted_by_id:
            issues.append(
                ValidationIssue(
                    f"materials-extracted.json.items[{index}].sourceId",
                    "duplicate-source",
                    f"sourceId is repeated: {source_id}",
                )
            )
        extracted_by_id[source_id] = item

    coverage_by_id = {}
    for index, item in enumerate(coverage["items"]):
        if not isinstance(item, dict):
            continue
        source_id = item.get("sourceId")
        if not isinstance(source_id, str):
            continue
        if source_id in coverage_by_id:
            issues.append(
                ValidationIssue(
                    f"source-coverage.json.items[{index}].sourceId",
                    "duplicate-source",
                    f"sourceId is repeated: {source_id}",
                )
            )
        coverage_by_id[source_id] = (index, item)

    for source_id, extracted_item in extracted_by_id.items():
        coverage_entry = coverage_by_id.get(source_id)
        if coverage_entry is None:
            issues.append(
                ValidationIssue(
                    f"source-coverage.json:{source_id}",
                    "missing-source-coverage",
                    "extracted source item is absent from source coverage",
                )
            )
            continue
        index, coverage_item = coverage_entry
        for field in ("sourceFile", "location"):
            if coverage_item.get(field) != extracted_item.get(field):
                issues.append(
                    ValidationIssue(
                        f"source-coverage.json.items[{index}].{field}",
                        "source-mismatch",
                        f"{field} does not match extracted material",
                    )
                )

    for source_id, (index, _) in coverage_by_id.items():
        if source_id not in extracted_by_id:
            issues.append(
                ValidationIssue(
                    f"source-coverage.json.items[{index}].sourceId",
                    "unknown-source",
                    f"sourceId was not found in extracted materials: {source_id}",
                )
            )
    return issues


def validate_decisions(data: object) -> List[ValidationIssue]:
    if not isinstance(data, dict) or not isinstance(data.get("decisions"), list):
        return [
            ValidationIssue(
                "decisions",
                "required",
                "decisions list is required",
            )
        ]
    issues: List[ValidationIssue] = []
    for index, decision in enumerate(data["decisions"]):
        path = f"decisions[{index}]"
        if not isinstance(decision, dict):
            issues.append(ValidationIssue(path, "required", "decision must be an object"))
            continue
        if decision.get("substantive") is True and decision.get("teacherConfirmed") is not True:
            issues.append(
                ValidationIssue(
                    path,
                    "unconfirmed-decision",
                    "substantive AI addition needs teacher confirmation",
                )
            )
    return issues


def validate_unresolved(data: object) -> List[ValidationIssue]:
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return [
            ValidationIssue(
                "items",
                "required",
                "unresolved items list is required",
            )
        ]
    issues: List[ValidationIssue] = []
    for index, item in enumerate(data["items"]):
        path = f"items[{index}]"
        if not isinstance(item, dict):
            issues.append(
                ValidationIssue(path, "required", "unresolved item must be an object")
            )
            continue
        if not isinstance(item.get("id"), str) or not item["id"].strip():
            issues.append(ValidationIssue(f"{path}.id", "required", "id is required"))
        if not isinstance(item.get("summary"), str) or not item["summary"].strip():
            issues.append(
                ValidationIssue(f"{path}.summary", "required", "summary is required")
            )
        status = item.get("status")
        if status not in {"open", "resolved"}:
            issues.append(
                ValidationIssue(
                    f"{path}.status",
                    "invalid-status",
                    "status must be open or resolved",
                )
            )
        if status == "open" and item.get("blocking") is True:
            issues.append(
                ValidationIssue(
                    path,
                    "unresolved-item",
                    item.get("summary", "blocking item is unresolved"),
                )
            )
    return issues


def validate_session(data: object) -> List[ValidationIssue]:
    if not isinstance(data, dict):
        return [ValidationIssue("$", "required", "session must be an object")]
    issues: List[ValidationIssue] = []
    if data.get("schemaVersion") != "1.0":
        issues.append(
            ValidationIssue(
                "schemaVersion",
                "invalid-version",
                "session schemaVersion must be 1.0",
            )
        )
    allowed_states = {
        "materials-intake",
        "media-intent",
        "media-design",
        "structure-proposal",
        "part-detail",
        "generation",
        "review",
        "complete",
    }
    if data.get("state") not in allowed_states:
        issues.append(
            ValidationIssue(
                "state",
                "invalid-status",
                "session state is invalid",
            )
        )
    return issues
