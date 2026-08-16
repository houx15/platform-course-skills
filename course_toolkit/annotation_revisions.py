import copy
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

from course_toolkit.annotations import (
    ANNOTATION_STORE_SCHEMA_VERSION,
    AnnotationStore,
    reconcile_annotations,
    resolve_annotation_target,
)
from course_toolkit.blueprint import (
    ID_RE,
    index_blueprint_targets,
    validate_blueprint_authoring,
)
from course_toolkit.course_compiler import canonical_json_hash
from course_toolkit.decisions import DecisionStore
from course_toolkit.jsonio import dump_json, load_json, write_json_atomic
from course_toolkit.workflow import verify_g5_compilation


REVISION_PLAN_SCHEMA_VERSION = "1.0"
REVISION_PLAN_RELATIVE_PATH = Path(".course-work/annotation-revision-plan.json")
CLASSIFICATIONS = frozenset({"mechanical", "semantic", "runtime-bug"})
MECHANICAL_LEAF_FIELDS = frozenset(
    {"alt", "caption", "content", "label", "markdown", "text", "title"}
)


class RevisionPlanBlocked(ValueError):
    pass


def _require_hash(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field} must be a SHA-256 hash")
    return value


def _tokens(pointer: str) -> Tuple[str, ...]:
    if not isinstance(pointer, str) or not pointer.startswith("/") or pointer == "/":
        raise ValueError("relativePointer must address a field below the target")
    tokens = []
    for raw in pointer[1:].split("/"):
        if raw in {"", ".", ".."}:
            raise ValueError("relativePointer must not contain empty or traversal tokens")
        if "~" in raw and not re.fullmatch(r"(?:[^~]|~[01])*", raw):
            raise ValueError("relativePointer contains invalid JSON Pointer escaping")
        tokens.append(raw.replace("~1", "/").replace("~0", "~"))
    return tuple(tokens)


@dataclass(frozen=True)
class RevisionOperation:
    op: str
    relative_pointer: str
    before_hash: str
    value: Any

    def __post_init__(self) -> None:
        if self.op != "replace":
            raise ValueError("Only replace revision operations are supported")
        _tokens(self.relative_pointer)
        _require_hash(self.before_hash, "beforeHash")

    def as_dict(self) -> dict:
        return {
            "op": self.op,
            "relativePointer": self.relative_pointer,
            "beforeHash": self.before_hash,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, data: object) -> "RevisionOperation":
        if not isinstance(data, dict):
            raise ValueError("Revision operation must be an object")
        allowed = {"op", "relativePointer", "beforeHash", "value"}
        unknown = sorted(set(data).difference(allowed))
        if unknown:
            raise ValueError(f"Unknown revision operation field: {unknown[0]}")
        missing = sorted(allowed.difference(data))
        if missing:
            raise ValueError(f"Missing revision operation field: {missing[0]}")
        return cls(
            op=data["op"],
            relative_pointer=data["relativePointer"],
            before_hash=data["beforeHash"],
            value=data["value"],
        )


@dataclass(frozen=True)
class RevisionPlanEntry:
    annotation_id: str
    classification: str
    target_id: str
    summary: str
    decision_id: Optional[str]
    operations: Tuple[RevisionOperation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.annotation_id, str) or not ID_RE.fullmatch(
            self.annotation_id
        ):
            raise ValueError("annotationId must be a stable ID")
        if self.classification not in CLASSIFICATIONS:
            raise ValueError(f"Unknown revision classification: {self.classification}")
        if not isinstance(self.target_id, str) or not self.target_id:
            raise ValueError("targetId is required")
        if not isinstance(self.summary, str) or not self.summary.strip():
            raise ValueError("Revision summary is required")
        if self.decision_id is not None and not ID_RE.fullmatch(self.decision_id):
            raise ValueError("decisionId must be a stable ID")
        if self.classification == "runtime-bug":
            if self.operations:
                raise ValueError("runtime-bug entries cannot mutate Blueprint")
            if self.decision_id is not None:
                raise ValueError("runtime-bug entries cannot use a content decision")
        else:
            if not self.operations:
                raise ValueError(f"{self.classification} entry requires operations")
        if self.classification == "mechanical":
            if self.decision_id is not None:
                raise ValueError("mechanical entry must not claim a teacher decision")
            for operation in self.operations:
                tokens = _tokens(operation.relative_pointer)
                if (
                    tokens[-1] not in MECHANICAL_LEAF_FIELDS
                    or not isinstance(operation.value, str)
                ):
                    raise ValueError(
                        "mechanical revisions may replace copy fields only"
                    )
        if self.classification == "semantic" and self.decision_id is None:
            raise ValueError("semantic entry requires decisionId")

    def as_dict(self) -> dict:
        return {
            "annotationId": self.annotation_id,
            "classification": self.classification,
            "targetId": self.target_id,
            "summary": self.summary,
            "decisionId": self.decision_id,
            "operations": [operation.as_dict() for operation in self.operations],
        }

    @classmethod
    def from_dict(cls, data: object) -> "RevisionPlanEntry":
        if not isinstance(data, dict):
            raise ValueError("Revision plan entry must be an object")
        allowed = {
            "annotationId",
            "classification",
            "targetId",
            "summary",
            "decisionId",
            "operations",
        }
        unknown = sorted(set(data).difference(allowed))
        if unknown:
            raise ValueError(f"Unknown revision plan entry field: {unknown[0]}")
        missing = sorted(allowed.difference(data))
        if missing:
            raise ValueError(f"Missing revision plan entry field: {missing[0]}")
        if not isinstance(data["operations"], list):
            raise ValueError("operations must be an array")
        return cls(
            annotation_id=data["annotationId"],
            classification=data["classification"],
            target_id=data["targetId"],
            summary=data["summary"],
            decision_id=data["decisionId"],
            operations=tuple(
                RevisionOperation.from_dict(item) for item in data["operations"]
            ),
        )


@dataclass(frozen=True)
class AnnotationRevisionPlan:
    schema_version: str
    plan_id: str
    base_blueprint_hash: str
    base_definition_hash: str
    base_source_map_hash: str
    entries: Tuple[RevisionPlanEntry, ...]

    def __post_init__(self) -> None:
        if self.schema_version != REVISION_PLAN_SCHEMA_VERSION:
            raise ValueError(f"Unsupported revision plan schemaVersion: {self.schema_version}")
        if not isinstance(self.plan_id, str) or not ID_RE.fullmatch(self.plan_id):
            raise ValueError("planId must be a stable ID")
        _require_hash(self.base_blueprint_hash, "baseBlueprintHash")
        _require_hash(self.base_definition_hash, "baseDefinitionHash")
        _require_hash(self.base_source_map_hash, "baseSourceMapHash")
        if not self.entries:
            raise ValueError("Revision plan must contain at least one entry")
        annotation_ids = [entry.annotation_id for entry in self.entries]
        if len(set(annotation_ids)) != len(annotation_ids):
            raise ValueError("Revision plan contains duplicate annotationId")

    def as_dict(self) -> dict:
        return {
            "schemaVersion": self.schema_version,
            "planId": self.plan_id,
            "baseBlueprintHash": self.base_blueprint_hash,
            "baseDefinitionHash": self.base_definition_hash,
            "baseSourceMapHash": self.base_source_map_hash,
            "entries": [entry.as_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, data: object) -> "AnnotationRevisionPlan":
        if not isinstance(data, dict):
            raise ValueError("Annotation revision plan must be an object")
        allowed = {
            "schemaVersion",
            "planId",
            "baseBlueprintHash",
            "baseDefinitionHash",
            "baseSourceMapHash",
            "entries",
        }
        unknown = sorted(set(data).difference(allowed))
        if unknown:
            raise ValueError(f"Unknown revision plan field: {unknown[0]}")
        missing = sorted(allowed.difference(data))
        if missing:
            raise ValueError(f"Missing revision plan field: {missing[0]}")
        if not isinstance(data["entries"], list):
            raise ValueError("entries must be an array")
        return cls(
            schema_version=data["schemaVersion"],
            plan_id=data["planId"],
            base_blueprint_hash=data["baseBlueprintHash"],
            base_definition_hash=data["baseDefinitionHash"],
            base_source_map_hash=data["baseSourceMapHash"],
            entries=tuple(RevisionPlanEntry.from_dict(item) for item in data["entries"]),
        )


@dataclass(frozen=True)
class RevisionPreparationResult:
    plan_id: str
    proposed_annotation_ids: Tuple[str, ...]
    pending_decision_ids: Tuple[str, ...]
    runtime_bug_annotation_ids: Tuple[str, ...]


@dataclass(frozen=True)
class RevisionApplicationResult:
    plan_id: str
    blueprint_hash: str
    applied_annotation_ids: Tuple[str, ...]
    runtime_bug_annotation_ids: Tuple[str, ...]
    idempotent: bool


def revision_entry_context(entry: RevisionPlanEntry) -> dict:
    return {
        "annotationId": entry.annotation_id,
        "classification": entry.classification,
        "targetId": entry.target_id,
        "summary": entry.summary,
        "operations": [operation.as_dict() for operation in entry.operations],
    }


def _read_pointer(document: object, pointer: str) -> object:
    current = document
    for token in _tokens(pointer):
        if isinstance(current, list):
            if not token.isdigit() or int(token) >= len(current):
                raise RevisionPlanBlocked(f"Revision pointer is missing: {pointer}")
            current = current[int(token)]
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            raise RevisionPlanBlocked(f"Revision pointer is missing: {pointer}")
    return current


def _replace_pointer(document: object, pointer: str, value: object) -> None:
    tokens = _tokens(pointer)
    current = document
    for token in tokens[:-1]:
        if isinstance(current, list):
            if not token.isdigit() or int(token) >= len(current):
                raise RevisionPlanBlocked(f"Revision pointer is missing: {pointer}")
            current = current[int(token)]
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            raise RevisionPlanBlocked(f"Revision pointer is missing: {pointer}")
    leaf = tokens[-1]
    if isinstance(current, list):
        if not leaf.isdigit() or int(leaf) >= len(current):
            raise RevisionPlanBlocked(f"Revision pointer is missing: {pointer}")
        current[int(leaf)] = copy.deepcopy(value)
    elif isinstance(current, dict) and leaf in current:
        current[leaf] = copy.deepcopy(value)
    else:
        raise RevisionPlanBlocked(f"Revision pointer is missing: {pointer}")


def _join_pointer(base: str, relative: str) -> str:
    if not base.startswith("/course"):
        raise RevisionPlanBlocked("Revision target is outside Blueprint course data")
    return f"{base}{relative}"


def _verify_base_hashes(root: Path, plan: AnnotationRevisionPlan) -> tuple[dict, dict, dict]:
    verify_g5_compilation(root)
    blueprint = load_json(root / ".course-work/course-blueprint.json")
    document = load_json(root / "course/course.json")
    source_map = load_json(root / ".course-work/course-runtime-source-map.json")
    actual = {
        "baseBlueprintHash": canonical_json_hash(blueprint),
        "baseDefinitionHash": canonical_json_hash(document),
        "baseSourceMapHash": canonical_json_hash(source_map),
    }
    expected = {
        "baseBlueprintHash": plan.base_blueprint_hash,
        "baseDefinitionHash": plan.base_definition_hash,
        "baseSourceMapHash": plan.base_source_map_hash,
    }
    for field in expected:
        if actual[field] != expected[field]:
            raise RevisionPlanBlocked(f"Revision plan {field} is stale")
    return blueprint, document, source_map


def prepare_revision_plan(
    root: Path,
    plan_path: Path,
    now: str,
) -> RevisionPreparationResult:
    root = root.resolve()
    plan = AnnotationRevisionPlan.from_dict(load_json(plan_path))
    blueprint, document, source_map = _verify_base_hashes(root, plan)
    reconcile_annotations(root, now)
    annotations = AnnotationStore.load(root / ".course-work/annotations.json")
    decisions = DecisionStore.load(root / ".course-work/decisions.json")
    proposed = []
    pending = []
    runtime_bugs = []
    for entry in plan.entries:
        annotation = annotations.get(entry.annotation_id)
        if annotation.status == "orphaned":
            raise RevisionPlanBlocked(
                f"Cannot prepare orphaned annotation: {annotation.id}"
            )
        if annotation.type == "bug" and entry.classification != "runtime-bug":
            raise RevisionPlanBlocked("Bug annotations must be classified runtime-bug")
        if entry.classification == "runtime-bug" and annotation.type != "bug":
            raise RevisionPlanBlocked("runtime-bug classification requires a bug annotation")
        resolved = resolve_annotation_target(annotation, document, source_map)
        if entry.target_id != resolved.target_id:
            raise RevisionPlanBlocked(
                f"Revision targetId differs for annotation {annotation.id}"
            )
        for operation in entry.operations:
            absolute_pointer = _join_pointer(
                resolved.blueprint_pointer,
                operation.relative_pointer,
            )
            current_value = _read_pointer(blueprint, absolute_pointer)
            if canonical_json_hash(current_value) != operation.before_hash:
                raise RevisionPlanBlocked(
                    f"Revision beforeHash is stale: {annotation.id}{operation.relative_pointer}"
                )

        if entry.classification == "semantic":
            context = revision_entry_context(entry)
            decision = decisions.request(
                entry.decision_id,
                f"Approve the proposed change for annotation {annotation.id}?",
                canonical_json_hash(context),
                context=context,
                options=("approve", "revise"),
                affected_artifact_ids=("course-blueprint",),
                requested_at=now,
            )
            if decision.status == "pending":
                pending.append(decision.id)
        if annotation.status == "open":
            annotations.transition(
                annotation.id,
                "proposed",
                now,
                classification=entry.classification,
                proposed_change=entry.summary,
            )
        elif annotation.status == "proposed":
            if (
                annotation.classification != entry.classification
                or annotation.proposed_change != entry.summary
            ):
                raise RevisionPlanBlocked(
                    f"Annotation already has a different proposal: {annotation.id}"
                )
        elif annotation.status not in {"accepted", "applied"}:
            raise RevisionPlanBlocked(
                f"Annotation cannot be prepared from status {annotation.status}: {annotation.id}"
            )
        proposed.append(annotation.id)
        if entry.classification == "runtime-bug":
            runtime_bugs.append(annotation.id)

    annotations.save()
    decisions.save()
    write_json_atomic(root / REVISION_PLAN_RELATIVE_PATH, plan.as_dict())
    reconcile_annotations(root, now)
    return RevisionPreparationResult(
        plan_id=plan.plan_id,
        proposed_annotation_ids=tuple(proposed),
        pending_decision_ids=tuple(pending),
        runtime_bug_annotation_ids=tuple(runtime_bugs),
    )


def _approve_semantic_entry(
    entry: RevisionPlanEntry,
    decisions: DecisionStore,
) -> None:
    decision = decisions.get(entry.decision_id)
    expected_context_hash = canonical_json_hash(revision_entry_context(entry))
    answer = decision.answer if isinstance(decision.answer, dict) else {}
    if (
        decision.status != "confirmed"
        or decision.context_hash != expected_context_hash
        or answer.get("choice") != "approve"
        or not isinstance(answer.get("rationale"), str)
        or not answer["rationale"].strip()
    ):
        raise RevisionPlanBlocked(
            f"Semantic revision is not approved for annotation {entry.annotation_id}"
        )


def _record_semantic_decision(
    blueprint: dict,
    entry: RevisionPlanEntry,
) -> None:
    approval = blueprint.get("approval")
    if not isinstance(approval, dict) or not isinstance(
        approval.get("decisionIds"), list
    ):
        raise RevisionPlanBlocked("Blueprint approval record is missing")
    if entry.decision_id not in approval["decisionIds"]:
        approval["decisionIds"].append(entry.decision_id)
    provenance = blueprint.get("provenance")
    if not isinstance(provenance, list):
        raise RevisionPlanBlocked("Blueprint provenance is missing")
    record = next(
        (
            item
            for item in provenance
            if isinstance(item, dict) and item.get("targetId") == entry.target_id
        ),
        None,
    )
    if record is None:
        record = {
            "targetId": entry.target_id,
            "sourceIds": [],
            "decisionIds": [],
            "status": "teacher-confirmed",
        }
        provenance.append(record)
    decision_ids = record.get("decisionIds")
    if not isinstance(decision_ids, list):
        raise RevisionPlanBlocked(
            f"Blueprint provenance decisionIds is invalid: {entry.target_id}"
        )
    if entry.decision_id not in decision_ids:
        decision_ids.append(entry.decision_id)


def _write_revision_outputs_atomic(
    root: Path,
    blueprint: dict,
    annotations: AnnotationStore,
    *,
    replace_output: Callable[[Path, Path], None] = os.replace,
) -> None:
    outputs = (
        (root / ".course-work/course-blueprint.json", blueprint),
        (
            root / ".course-work/annotations.json",
            {
                "schemaVersion": ANNOTATION_STORE_SCHEMA_VERSION,
                "annotations": [item.as_dict() for item in annotations.all()],
            },
        ),
    )
    staged: List[Path] = []
    backups = {}
    originally_present = {
        destination: destination.exists() for destination, _ in outputs
    }
    try:
        for destination, payload in outputs:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.parent.is_symlink() or destination.is_symlink():
                raise ValueError(f"Revision output must not be a symlink: {destination}")
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.name}.",
                suffix=".tmp",
                dir=destination.parent,
            )
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(dump_json(payload))
                stream.flush()
                os.fsync(stream.fileno())
            staged.append(temporary)
        for destination, _ in outputs:
            if destination.exists():
                descriptor, backup_name = tempfile.mkstemp(
                    prefix=f".{destination.name}.",
                    suffix=".bak",
                    dir=destination.parent,
                )
                os.close(descriptor)
                backup = Path(backup_name)
                shutil.copy2(destination, backup)
                backups[destination] = backup
        for (destination, _), temporary in zip(outputs, staged):
            replace_output(temporary, destination)
    except Exception:
        for destination, _ in outputs:
            backup = backups.get(destination)
            if backup is not None and backup.exists():
                os.replace(backup, destination)
            elif not originally_present[destination] and destination.exists():
                destination.unlink()
        raise
    finally:
        for temporary in staged:
            if temporary.exists():
                temporary.unlink()
        for backup in backups.values():
            if backup.exists():
                backup.unlink()


def apply_revision_plan(
    root: Path,
    plan_path: Path,
    now: str,
    *,
    replace_output: Callable[[Path, Path], None] = os.replace,
) -> RevisionApplicationResult:
    root = root.resolve()
    plan = AnnotationRevisionPlan.from_dict(load_json(plan_path))
    annotations = AnnotationStore.load(root / ".course-work/annotations.json")
    applicable = [
        entry for entry in plan.entries if entry.classification != "runtime-bug"
    ]
    if applicable:
        applied_records = [annotations.get(entry.annotation_id) for entry in applicable]
        applied_hashes = {
            record.applied_blueprint_hash
            for record in applied_records
            if record.status == "applied"
        }
        if (
            all(record.status == "applied" for record in applied_records)
            and len(applied_hashes) == 1
        ):
            applied_hash = next(iter(applied_hashes))
            current_blueprint = load_json(
                root / ".course-work/course-blueprint.json"
            )
            if applied_hash == canonical_json_hash(current_blueprint):
                return RevisionApplicationResult(
                    plan_id=plan.plan_id,
                    blueprint_hash=applied_hash,
                    applied_annotation_ids=tuple(
                        entry.annotation_id for entry in applicable
                    ),
                    runtime_bug_annotation_ids=tuple(
                        entry.annotation_id
                        for entry in plan.entries
                        if entry.classification == "runtime-bug"
                    ),
                    idempotent=True,
                )

    blueprint, document, source_map = _verify_base_hashes(root, plan)
    updated_blueprint = copy.deepcopy(blueprint)
    decisions = DecisionStore.load(root / ".course-work/decisions.json")
    original_target_ids = set(index_blueprint_targets(blueprint))
    absolute_pointers = set()
    resolved_entries = []
    for entry in plan.entries:
        annotation = annotations.get(entry.annotation_id)
        resolved = resolve_annotation_target(annotation, document, source_map)
        if resolved.target_id != entry.target_id:
            raise RevisionPlanBlocked(
                f"Revision targetId differs for annotation {annotation.id}"
            )
        if entry.classification == "runtime-bug":
            if annotation.status != "proposed" or annotation.classification != "runtime-bug":
                raise RevisionPlanBlocked(
                    f"Runtime bug was not prepared: {annotation.id}"
                )
            resolved_entries.append((entry, annotation, resolved))
            continue
        if annotation.status not in {"proposed", "accepted"}:
            raise RevisionPlanBlocked(
                f"Annotation was not prepared for application: {annotation.id}"
            )
        if annotation.classification != entry.classification:
            raise RevisionPlanBlocked(
                f"Annotation classification differs from plan: {annotation.id}"
            )
        if entry.classification == "semantic":
            _approve_semantic_entry(entry, decisions)
        for operation in entry.operations:
            absolute_pointer = _join_pointer(
                resolved.blueprint_pointer,
                operation.relative_pointer,
            )
            if absolute_pointer in absolute_pointers:
                raise RevisionPlanBlocked(
                    f"Revision plan writes the same field twice: {absolute_pointer}"
                )
            absolute_pointers.add(absolute_pointer)
            if _tokens(absolute_pointer)[-1] == "id":
                raise RevisionPlanBlocked("Revision plan cannot change stable IDs")
            current_value = _read_pointer(updated_blueprint, absolute_pointer)
            if canonical_json_hash(current_value) != operation.before_hash:
                raise RevisionPlanBlocked(
                    f"Revision beforeHash is stale: {annotation.id}{operation.relative_pointer}"
                )
            _replace_pointer(updated_blueprint, absolute_pointer, operation.value)
        if entry.classification == "semantic":
            _record_semantic_decision(updated_blueprint, entry)
        resolved_entries.append((entry, annotation, resolved))

    if set(index_blueprint_targets(updated_blueprint)) != original_target_ids:
        raise RevisionPlanBlocked("Revision plan cannot add, remove, or rename stable targets")
    authoring_issues = validate_blueprint_authoring(
        updated_blueprint,
        require_approval=True,
    )
    if authoring_issues:
        first = authoring_issues[0]
        raise RevisionPlanBlocked(
            f"Revised Blueprint is invalid: {first.path}: {first.message}"
        )
    new_blueprint_hash = canonical_json_hash(updated_blueprint)
    applied_ids = []
    runtime_ids = []
    for entry, annotation, _ in resolved_entries:
        if entry.classification == "runtime-bug":
            runtime_ids.append(annotation.id)
            continue
        current = annotations.get(annotation.id)
        if entry.classification == "semantic" and current.status == "proposed":
            current = annotations.transition(
                current.id,
                "accepted",
                now,
                resolution_decision_id=entry.decision_id,
            )
        changes = {"applied_blueprint_hash": new_blueprint_hash}
        if entry.classification == "semantic":
            changes["resolution_decision_id"] = entry.decision_id
        annotations.transition(current.id, "applied", now, **changes)
        applied_ids.append(current.id)

    _write_revision_outputs_atomic(
        root,
        updated_blueprint,
        annotations,
        replace_output=replace_output,
    )
    return RevisionApplicationResult(
        plan_id=plan.plan_id,
        blueprint_hash=new_blueprint_hash,
        applied_annotation_ids=tuple(applied_ids),
        runtime_bug_annotation_ids=tuple(runtime_ids),
        idempotent=False,
    )
