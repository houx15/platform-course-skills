import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional

from course_toolkit.blueprint import ID_RE
from course_toolkit.jsonio import load_json, write_json_atomic


ANNOTATION_STORE_SCHEMA_VERSION = "1.0"
ANNOTATION_TYPES = frozenset(
    {"content", "layout", "workflow", "media", "bug", "question"}
)
ANNOTATION_STATUSES = frozenset(
    {"open", "proposed", "accepted", "applied", "verified", "dismissed", "orphaned"}
)
ANNOTATION_CLASSIFICATIONS = frozenset({"mechanical", "semantic", "runtime-bug"})
HASH_RE = re.compile(r"^[a-f0-9]{64}$")

TARGET_FIELDS = {
    "courseId",
    "partId",
    "sliceId",
    "blockId",
    "itemId",
    "workflowStepId",
}
ANNOTATION_FIELDS = {
    "id",
    "type",
    "status",
    "required",
    "target",
    "definitionHash",
    "text",
    "screenshotPath",
    "createdAt",
    "updatedAt",
    "classification",
    "proposedChange",
    "resolutionDecisionId",
    "appliedBlueprintHash",
    "verifiedAgainstDefinitionHash",
    "orphanReason",
    "reboundFromDefinitionHash",
}


def _stable_id(
    value: object,
    field: str,
    *,
    optional: bool = True,
) -> Optional[str]:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValueError(f"{field} must be a stable semantic ID")
    return value


def _hash(value: object, field: str, *, optional: bool = False) -> Optional[str]:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise ValueError(f"{field} must be a SHA-256 hash")
    return value


def _screenshot_path(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("screenshotPath must be a safe preview screenshot path")
    path = Path(value)
    allowed_suffixes = {".png", ".jpg", ".jpeg", ".webp"}
    if (
        path.is_absolute()
        or path.parts[:2] != (".course-work", "screenshots")
        or len(path.parts) < 3
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.suffix.lower() not in allowed_suffixes
    ):
        raise ValueError("screenshotPath must stay under .course-work/screenshots")
    return value


@dataclass(frozen=True)
class AnnotationTarget:
    course_id: str
    part_id: Optional[str] = None
    slice_id: Optional[str] = None
    block_id: Optional[str] = None
    item_id: Optional[str] = None
    workflow_step_id: Optional[str] = None

    def __post_init__(self) -> None:
        _stable_id(self.course_id, "courseId", optional=False)
        _stable_id(self.part_id, "partId")
        _stable_id(self.slice_id, "sliceId")
        _stable_id(self.block_id, "blockId")
        _stable_id(self.item_id, "itemId")
        _stable_id(self.workflow_step_id, "workflowStepId")
        if self.slice_id is not None and self.part_id is None:
            raise ValueError("sliceId requires partId")
        if self.block_id is not None and self.slice_id is None:
            raise ValueError("blockId requires sliceId")
        if self.item_id is not None and self.block_id is None:
            raise ValueError("itemId requires blockId")
        if self.workflow_step_id is not None and self.slice_id is None:
            raise ValueError("workflowStepId requires sliceId")
        if self.workflow_step_id is not None and (
            self.block_id is not None or self.item_id is not None
        ):
            raise ValueError("workflowStepId cannot be combined with blockId or itemId")

    def as_dict(self) -> dict:
        return {
            "courseId": self.course_id,
            "partId": self.part_id,
            "sliceId": self.slice_id,
            "blockId": self.block_id,
            "itemId": self.item_id,
            "workflowStepId": self.workflow_step_id,
        }

    @classmethod
    def from_dict(cls, data: object) -> "AnnotationTarget":
        if not isinstance(data, dict):
            raise ValueError("Annotation target must be an object")
        unknown = sorted(set(data).difference(TARGET_FIELDS))
        if unknown:
            raise ValueError(f"Unknown annotation target field: {unknown[0]}")
        return cls(
            course_id=data.get("courseId"),
            part_id=data.get("partId"),
            slice_id=data.get("sliceId"),
            block_id=data.get("blockId"),
            item_id=data.get("itemId"),
            workflow_step_id=data.get("workflowStepId"),
        )


@dataclass(frozen=True)
class CourseAnnotation:
    id: str
    type: str
    status: str
    required: bool
    target: AnnotationTarget
    definition_hash: str
    text: str
    created_at: str
    updated_at: str
    screenshot_path: Optional[str] = None
    classification: Optional[str] = None
    proposed_change: Optional[str] = None
    resolution_decision_id: Optional[str] = None
    applied_blueprint_hash: Optional[str] = None
    verified_against_definition_hash: Optional[str] = None
    orphan_reason: Optional[str] = None
    rebound_from_definition_hash: Optional[str] = None

    def __post_init__(self) -> None:
        _stable_id(self.id, "annotation id", optional=False)
        if self.type not in ANNOTATION_TYPES:
            raise ValueError(f"Unknown annotation type: {self.type}")
        if self.status not in ANNOTATION_STATUSES:
            raise ValueError(f"Unknown annotation status: {self.status}")
        if not isinstance(self.required, bool):
            raise ValueError("required must be boolean")
        if not isinstance(self.target, AnnotationTarget):
            raise ValueError("target must be an AnnotationTarget")
        _hash(self.definition_hash, "definitionHash")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("Annotation text is required")
        if not isinstance(self.created_at, str) or not self.created_at:
            raise ValueError("createdAt is required")
        if not isinstance(self.updated_at, str) or not self.updated_at:
            raise ValueError("updatedAt is required")
        _screenshot_path(self.screenshot_path)
        if self.classification is not None and self.classification not in ANNOTATION_CLASSIFICATIONS:
            raise ValueError(f"Unknown annotation classification: {self.classification}")
        _stable_id(self.resolution_decision_id, "resolutionDecisionId")
        _hash(self.applied_blueprint_hash, "appliedBlueprintHash", optional=True)
        _hash(
            self.verified_against_definition_hash,
            "verifiedAgainstDefinitionHash",
            optional=True,
        )
        _hash(
            self.rebound_from_definition_hash,
            "reboundFromDefinitionHash",
            optional=True,
        )
        if self.status in {"proposed", "accepted", "applied", "verified"}:
            if self.classification is None or not self.proposed_change:
                raise ValueError(f"{self.status} annotation requires a classified proposal")
        if self.status in {"accepted", "applied", "verified"} and self.classification == "semantic":
            if not self.resolution_decision_id:
                raise ValueError("Semantic annotation requires a teacher decision")
        if self.status in {"applied", "verified"} and self.applied_blueprint_hash is None:
            raise ValueError(f"{self.status} annotation requires appliedBlueprintHash")
        if self.status == "verified" and self.verified_against_definition_hash is None:
            raise ValueError("verified annotation requires verifiedAgainstDefinitionHash")
        if self.status == "orphaned" and not self.orphan_reason:
            raise ValueError("orphaned annotation requires orphanReason")
        if self.status == "dismissed" and self.required and not self.resolution_decision_id:
            raise ValueError("Required annotation dismissal requires a teacher decision")

    def as_dict(self) -> dict:
        data = asdict(self)
        return {
            "id": data["id"],
            "type": data["type"],
            "status": data["status"],
            "required": data["required"],
            "target": self.target.as_dict(),
            "definitionHash": data["definition_hash"],
            "text": data["text"],
            "screenshotPath": data["screenshot_path"],
            "createdAt": data["created_at"],
            "updatedAt": data["updated_at"],
            "classification": data["classification"],
            "proposedChange": data["proposed_change"],
            "resolutionDecisionId": data["resolution_decision_id"],
            "appliedBlueprintHash": data["applied_blueprint_hash"],
            "verifiedAgainstDefinitionHash": data["verified_against_definition_hash"],
            "orphanReason": data["orphan_reason"],
            "reboundFromDefinitionHash": data["rebound_from_definition_hash"],
        }

    @classmethod
    def from_dict(cls, data: object) -> "CourseAnnotation":
        if not isinstance(data, dict):
            raise ValueError("Annotation must be an object")
        unknown = sorted(set(data).difference(ANNOTATION_FIELDS))
        if unknown:
            raise ValueError(f"Unknown annotation field: {unknown[0]}")
        required = {
            "id",
            "type",
            "status",
            "required",
            "target",
            "definitionHash",
            "text",
            "createdAt",
            "updatedAt",
        }
        missing = sorted(required.difference(data))
        if missing:
            raise ValueError(f"Missing annotation field: {missing[0]}")
        return cls(
            id=data["id"],
            type=data["type"],
            status=data["status"],
            required=data["required"],
            target=AnnotationTarget.from_dict(data["target"]),
            definition_hash=data["definitionHash"],
            text=data["text"],
            screenshot_path=data.get("screenshotPath"),
            created_at=data["createdAt"],
            updated_at=data["updatedAt"],
            classification=data.get("classification"),
            proposed_change=data.get("proposedChange"),
            resolution_decision_id=data.get("resolutionDecisionId"),
            applied_blueprint_hash=data.get("appliedBlueprintHash"),
            verified_against_definition_hash=data.get(
                "verifiedAgainstDefinitionHash"
            ),
            orphan_reason=data.get("orphanReason"),
            rebound_from_definition_hash=data.get("reboundFromDefinitionHash"),
        )


LEGAL_TRANSITIONS = {
    "open": {"proposed", "dismissed", "orphaned"},
    "proposed": {"open", "accepted", "applied", "dismissed", "orphaned"},
    "accepted": {"open", "applied", "orphaned"},
    "applied": {"open", "verified", "orphaned"},
    "verified": {"open", "orphaned"},
    "dismissed": {"open", "orphaned"},
    "orphaned": {"open", "dismissed"},
}


class AnnotationStore:
    def __init__(
        self,
        path: Path,
        annotations: Optional[List[CourseAnnotation]] = None,
    ) -> None:
        self.path = path
        self._annotations: Dict[str, CourseAnnotation] = {}
        for annotation in annotations or []:
            self.add(annotation)

    @classmethod
    def load(cls, path: Path) -> "AnnotationStore":
        if not path.exists():
            return cls(path)
        data = load_json(path)
        if data.get("schemaVersion") != ANNOTATION_STORE_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported annotation schemaVersion: {data.get('schemaVersion')}"
            )
        raw = data.get("annotations")
        if not isinstance(raw, list):
            raise ValueError("annotations must be an array")
        return cls(path, [CourseAnnotation.from_dict(item) for item in raw])

    def save(self) -> None:
        write_json_atomic(
            self.path,
            {
                "schemaVersion": ANNOTATION_STORE_SCHEMA_VERSION,
                "annotations": [item.as_dict() for item in self.all()],
            },
        )

    def all(self) -> List[CourseAnnotation]:
        return sorted(self._annotations.values(), key=lambda item: item.id)

    def get(self, annotation_id: str) -> CourseAnnotation:
        try:
            return self._annotations[annotation_id]
        except KeyError as exc:
            raise ValueError(f"Unknown annotation: {annotation_id}") from exc

    def add(self, annotation: CourseAnnotation) -> CourseAnnotation:
        if annotation.id in self._annotations:
            raise ValueError(f"Duplicate annotation: {annotation.id}")
        self._annotations[annotation.id] = annotation
        return annotation

    def replace(self, annotation: CourseAnnotation) -> CourseAnnotation:
        if annotation.id not in self._annotations:
            raise ValueError(f"Unknown annotation: {annotation.id}")
        self._annotations[annotation.id] = annotation
        return annotation

    def transition(
        self,
        annotation_id: str,
        status: str,
        updated_at: str,
        **changes,
    ) -> CourseAnnotation:
        current = self.get(annotation_id)
        if status == current.status:
            return current
        if status not in LEGAL_TRANSITIONS[current.status]:
            raise ValueError(
                f"Illegal annotation transition: {current.status} -> {status}"
            )
        values = {"status": status, "updated_at": updated_at, **changes}
        if status == "open":
            values.update(
                classification=None,
                proposed_change=None,
                resolution_decision_id=None,
                applied_blueprint_hash=None,
                verified_against_definition_hash=None,
                orphan_reason=None,
            )
        elif status == "proposed":
            values.update(
                resolution_decision_id=None,
                applied_blueprint_hash=None,
                verified_against_definition_hash=None,
                orphan_reason=None,
            )
        elif status == "orphaned":
            values.setdefault("orphan_reason", "Target is absent from the current definition")
        updated = replace(current, **values)
        self._annotations[annotation_id] = updated
        return updated
