import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from course_toolkit.jsonio import load_json


BLUEPRINT_SCHEMA_VERSION = "1.0"
TARGET_CONTRACT_VERSION = "2.0"
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TARGET_RE = re.compile(
    r"^(?:course|opening|closing|(?:objective|part|slice|block):"
    r"[a-z0-9]+(?:-[a-z0-9]+)*|slice:[a-z0-9]+(?:-[a-z0-9]+)*/"
    r"(?:narration|workflow-step):[a-z0-9]+(?:-[a-z0-9]+)*)$"
)


@dataclass(frozen=True)
class BlueprintIssue:
    path: str
    code: str
    message: str


class BlueprintValidationError(ValueError):
    def __init__(self, issues: Sequence[BlueprintIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__("; ".join(f"{issue.path}: {issue.message}" for issue in issues))


class DuplicateBlueprintTarget(ValueError):
    pass


def _issue(path: str, code: str, message: str) -> BlueprintIssue:
    return BlueprintIssue(path=path, code=code, message=message)


def _unknown_fields(
    value: dict,
    allowed: set,
    path: str,
    issues: List[BlueprintIssue],
) -> None:
    for field in sorted(set(value).difference(allowed)):
        issues.append(_issue(f"{path}.{field}", "unknown-field", f"Unknown field: {field}"))


def _string_list(
    value: object,
    path: str,
    issues: List[BlueprintIssue],
) -> Optional[List[str]]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        issues.append(_issue(path, "invalid-value", f"{path} must be a string array"))
        return None
    if len(set(value)) != len(value):
        issues.append(_issue(path, "duplicate-value", f"{path} must contain unique values"))
    return value


def _register_target(targets: Dict[str, str], target_id: str, pointer: str) -> None:
    if target_id in targets:
        raise DuplicateBlueprintTarget(f"Duplicate Blueprint target: {target_id}")
    targets[target_id] = pointer


def _require_list(value: object, label: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _require_dict(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def index_blueprint_targets(data: dict) -> Dict[str, str]:
    course = _require_dict(data.get("course"), "course")
    targets: Dict[str, str] = {}
    _register_target(targets, "course", "/course")
    _require_dict(course.get("opening"), "course.opening")
    _register_target(targets, "opening", "/course/opening")
    _require_dict(course.get("closing"), "course.closing")
    _register_target(targets, "closing", "/course/closing")

    objectives = _require_list(course.get("objectives"), "course.objectives")
    for objective_index, objective_value in enumerate(objectives):
        objective = _require_dict(
            objective_value,
            f"course.objectives[{objective_index}]",
        )
        objective_id = objective.get("id")
        if not isinstance(objective_id, str) or not ID_RE.fullmatch(objective_id):
            raise ValueError(f"Invalid objective id at index {objective_index}")
        _register_target(
            targets,
            f"objective:{objective_id}",
            f"/course/objectives/{objective_index}",
        )

    parts = _require_list(course.get("parts"), "course.parts")
    for part_index, part_value in enumerate(parts):
        part = _require_dict(part_value, f"course.parts[{part_index}]")
        part_id = part.get("id")
        if not isinstance(part_id, str) or not ID_RE.fullmatch(part_id):
            raise ValueError(f"Invalid part id at index {part_index}")
        part_pointer = f"/course/parts/{part_index}"
        _register_target(targets, f"part:{part_id}", part_pointer)

        slices = _require_list(part.get("slices"), f"{part_pointer}/slices")
        for slice_index, slice_value in enumerate(slices):
            slice_data = _require_dict(
                slice_value,
                f"course.parts[{part_index}].slices[{slice_index}]",
            )
            slice_id = slice_data.get("id")
            if not isinstance(slice_id, str) or not ID_RE.fullmatch(slice_id):
                raise ValueError(
                    f"Invalid slice id at part {part_index}, slice {slice_index}"
                )
            slice_pointer = f"{part_pointer}/slices/{slice_index}"
            _register_target(targets, f"slice:{slice_id}", slice_pointer)

            blocks = _require_list(
                slice_data.get("blocks"),
                f"{slice_pointer}/blocks",
            )
            for block_index, block_value in enumerate(blocks):
                block = _require_dict(block_value, f"{slice_pointer}/blocks/{block_index}")
                block_id = block.get("id")
                if not isinstance(block_id, str) or not ID_RE.fullmatch(block_id):
                    raise ValueError(
                        f"Invalid block id at {slice_pointer}/blocks/{block_index}"
                    )
                _register_target(
                    targets,
                    f"block:{block_id}",
                    f"{slice_pointer}/blocks/{block_index}",
                )

            narrations = _require_list(
                slice_data.get("narrations"),
                f"{slice_pointer}/narrations",
            )
            for narration_index, narration_value in enumerate(narrations):
                narration = _require_dict(
                    narration_value,
                    f"{slice_pointer}/narrations/{narration_index}",
                )
                narration_id = narration.get("id")
                if not isinstance(narration_id, str) or not ID_RE.fullmatch(
                    narration_id
                ):
                    raise ValueError(
                        f"Invalid narration id at {slice_pointer}/narrations/{narration_index}"
                    )
                _register_target(
                    targets,
                    f"slice:{slice_id}/narration:{narration_id}",
                    f"{slice_pointer}/narrations/{narration_index}",
                )

            workflow = _require_dict(
                slice_data.get("workflow"),
                f"{slice_pointer}/workflow",
            )
            steps = _require_list(
                workflow.get("steps"),
                f"{slice_pointer}/workflow/steps",
            )
            for step_index, step_value in enumerate(steps):
                step = _require_dict(
                    step_value,
                    f"{slice_pointer}/workflow/steps/{step_index}",
                )
                step_id = step.get("id")
                if not isinstance(step_id, str) or not ID_RE.fullmatch(step_id):
                    raise ValueError(
                        f"Invalid workflow step id at {slice_pointer}/workflow/steps/{step_index}"
                    )
                _register_target(
                    targets,
                    f"slice:{slice_id}/workflow-step:{step_id}",
                    f"{slice_pointer}/workflow/steps/{step_index}",
                )
    return targets


def validate_blueprint_authoring(
    data: object,
    *,
    require_approval: bool = True,
) -> List[BlueprintIssue]:
    issues: List[BlueprintIssue] = []
    if not isinstance(data, dict):
        return [_issue("$", "required", "Blueprint must be an object")]
    required = {
        "schemaVersion",
        "targetContractVersion",
        "approval",
        "course",
        "provenance",
        "migration",
    }
    _unknown_fields(data, required, "$", issues)
    for field in sorted(required.difference(data)):
        issues.append(_issue(f"$.{field}", "required", f"Missing field: {field}"))
    if data.get("schemaVersion") != BLUEPRINT_SCHEMA_VERSION:
        issues.append(_issue("$.schemaVersion", "invalid-version", "Expected 1.0"))
    if data.get("targetContractVersion") != TARGET_CONTRACT_VERSION:
        issues.append(
            _issue("$.targetContractVersion", "invalid-version", "Expected 2.0")
        )

    approval = data.get("approval")
    if not isinstance(approval, dict):
        issues.append(_issue("$.approval", "required", "approval must be an object"))
    else:
        _unknown_fields(
            approval,
            {"teacherConfirmed", "decisionIds"},
            "$.approval",
            issues,
        )
        teacher_confirmed = approval.get("teacherConfirmed")
        if not isinstance(teacher_confirmed, bool):
            issues.append(
                _issue(
                    "$.approval.teacherConfirmed",
                    "invalid-value",
                    "teacherConfirmed must be a boolean",
                )
            )
        decision_ids = _string_list(
            approval.get("decisionIds"),
            "$.approval.decisionIds",
            issues,
        )
        if teacher_confirmed is True and not decision_ids:
            issues.append(
                _issue(
                    "$.approval.decisionIds",
                    "missing-decision",
                    "A confirmed Blueprint requires a teacher decision identity",
                )
            )
        if require_approval and teacher_confirmed is not True:
            issues.append(
                _issue(
                    "$.approval.teacherConfirmed",
                    "blueprint-unconfirmed",
                    "Blueprint requires teacher confirmation before compilation",
                )
            )

    try:
        targets = index_blueprint_targets(data)
    except DuplicateBlueprintTarget as exc:
        targets = {}
        issues.append(_issue("$.course", "duplicate-target", str(exc)))
    except (KeyError, TypeError, ValueError) as exc:
        targets = {}
        issues.append(_issue("$.course", "invalid-course", str(exc)))

    provenance = data.get("provenance")
    if not isinstance(provenance, list):
        issues.append(
            _issue("$.provenance", "invalid-value", "provenance must be an array")
        )
    else:
        seen_targets = set()
        for index, record in enumerate(provenance):
            path = f"$.provenance[{index}]"
            if not isinstance(record, dict):
                issues.append(_issue(path, "invalid-value", "record must be an object"))
                continue
            _unknown_fields(
                record,
                {"targetId", "sourceIds", "decisionIds", "status"},
                path,
                issues,
            )
            target_id = record.get("targetId")
            if not isinstance(target_id, str) or not TARGET_RE.fullmatch(target_id):
                issues.append(
                    _issue(f"{path}.targetId", "invalid-target", "Malformed targetId")
                )
            else:
                if target_id in seen_targets:
                    issues.append(
                        _issue(
                            f"{path}.targetId",
                            "duplicate-provenance",
                            f"Duplicate provenance target: {target_id}",
                        )
                    )
                seen_targets.add(target_id)
                if targets and target_id not in targets:
                    issues.append(
                        _issue(
                            f"{path}.targetId",
                            "unknown-target",
                            f"Unknown Blueprint target: {target_id}",
                        )
                    )
            _string_list(record.get("sourceIds"), f"{path}.sourceIds", issues)
            _string_list(record.get("decisionIds"), f"{path}.decisionIds", issues)
            if record.get("status") not in {
                "source-backed",
                "teacher-confirmed",
                "ai-proposed",
            }:
                issues.append(
                    _issue(f"{path}.status", "invalid-value", "Unknown provenance status")
                )

    migration = data.get("migration")
    if migration is not None:
        if not isinstance(migration, dict):
            issues.append(
                _issue("$.migration", "invalid-value", "migration must be null or object")
            )
        else:
            _unknown_fields(
                migration,
                {"sourceSchemaVersion", "sourceHash", "assumptions"},
                "$.migration",
                issues,
            )
            if migration.get("sourceSchemaVersion") != "1.1":
                issues.append(
                    _issue(
                        "$.migration.sourceSchemaVersion",
                        "invalid-version",
                        "Only schemaVersion 1.1 can be imported",
                    )
                )
            source_hash = migration.get("sourceHash")
            if not isinstance(source_hash, str) or not re.fullmatch(
                r"[a-f0-9]{64}", source_hash
            ):
                issues.append(
                    _issue(
                        "$.migration.sourceHash",
                        "invalid-value",
                        "sourceHash must be SHA-256",
                    )
                )
            assumptions = migration.get("assumptions")
            if not isinstance(assumptions, list):
                issues.append(
                    _issue(
                        "$.migration.assumptions",
                        "invalid-value",
                        "assumptions must be an array",
                    )
                )
            else:
                for index, assumption in enumerate(assumptions):
                    path = f"$.migration.assumptions[{index}]"
                    if not isinstance(assumption, dict):
                        issues.append(
                            _issue(path, "invalid-value", "assumption must be an object")
                        )
                        continue
                    _unknown_fields(
                        assumption,
                        {"id", "description", "targetIds"},
                        path,
                        issues,
                    )
                    assumption_id = assumption.get("id")
                    if not isinstance(assumption_id, str) or not ID_RE.fullmatch(
                        assumption_id
                    ):
                        issues.append(
                            _issue(f"{path}.id", "invalid-value", "Invalid assumption id")
                        )
                    description = assumption.get("description")
                    if not isinstance(description, str) or not description.strip():
                        issues.append(
                            _issue(
                                f"{path}.description",
                                "invalid-value",
                                "Assumption description is required",
                            )
                        )
                    target_ids = _string_list(
                        assumption.get("targetIds"),
                        f"{path}.targetIds",
                        issues,
                    )
                    for target_id in target_ids or []:
                        if targets and target_id not in targets:
                            issues.append(
                                _issue(
                                    f"{path}.targetIds",
                                    "unknown-target",
                                    f"Unknown Blueprint target: {target_id}",
                                )
                            )
    return issues


def load_blueprint(path: Path, *, require_approval: bool = True) -> dict:
    data = load_json(path)
    issues = validate_blueprint_authoring(data, require_approval=require_approval)
    if issues:
        raise BlueprintValidationError(issues)
    return data


def project_course_definition(data: dict) -> dict:
    return {
        "schemaVersion": TARGET_CONTRACT_VERSION,
        "course": copy.deepcopy(data["course"]),
    }
