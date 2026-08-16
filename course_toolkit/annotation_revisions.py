import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Tuple

from course_toolkit.annotations import (
    AnnotationStore,
    reconcile_annotations,
    resolve_annotation_target,
)
from course_toolkit.blueprint import ID_RE
from course_toolkit.course_compiler import canonical_json_hash
from course_toolkit.decisions import DecisionStore
from course_toolkit.jsonio import load_json, write_json_atomic
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
