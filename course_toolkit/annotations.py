import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional

from course_toolkit.blueprint import ID_RE
from course_toolkit.course_compiler import canonical_json_hash
from course_toolkit.issues import IssueStore, make_registered_issue
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


@dataclass(frozen=True)
class ResolvedAnnotationTarget:
    target_id: str
    blueprint_pointer: str
    runtime_pointer: str


@dataclass(frozen=True)
class AnnotationReconciliationResult:
    resolved_ids: tuple[str, ...]
    rebound_ids: tuple[str, ...]
    orphaned_ids: tuple[str, ...]
    restored_ids: tuple[str, ...]
    active_issue_ids: tuple[str, ...]


def _by_id(items: object, item_id: str) -> tuple[int, dict]:
    if not isinstance(items, list):
        raise ValueError(f"Target {item_id} is missing")
    matches = [
        (index, item)
        for index, item in enumerate(items)
        if isinstance(item, dict) and item.get("id") == item_id
    ]
    if len(matches) != 1:
        raise ValueError(f"Target {item_id} is missing or ambiguous")
    return matches[0]


def resolve_annotation_target(
    annotation: CourseAnnotation,
    document: dict,
    source_map: dict,
) -> ResolvedAnnotationTarget:
    course = document.get("course")
    if not isinstance(course, dict) or course.get("id") != annotation.target.course_id:
        raise ValueError(f"Course target is missing: {annotation.target.course_id}")
    target_id = "course"
    runtime_pointer = "/course"
    current = course
    target = annotation.target

    if target.part_id is not None:
        index, current = _by_id(course.get("parts"), target.part_id)
        runtime_pointer = f"/course/parts/{index}"
        target_id = f"part:{target.part_id}"
    if target.slice_id is not None:
        index, current = _by_id(current.get("slices"), target.slice_id)
        runtime_pointer = f"{runtime_pointer}/slices/{index}"
        target_id = f"slice:{target.slice_id}"
    slice_data = current
    if target.block_id is not None:
        index, current = _by_id(slice_data.get("blocks"), target.block_id)
        runtime_pointer = f"{runtime_pointer}/blocks/{index}"
        target_id = f"block:{target.block_id}"
    if target.item_id is not None:
        item_matches = []
        for field, value in current.items():
            if not isinstance(value, list):
                continue
            for index, item in enumerate(value):
                if isinstance(item, dict) and item.get("id") == target.item_id:
                    item_matches.append((field, index))
        if len(item_matches) != 1:
            raise ValueError(f"Item target is missing or ambiguous: {target.item_id}")
        field, index = item_matches[0]
        runtime_pointer = f"{runtime_pointer}/{field}/{index}"
    if target.workflow_step_id is not None:
        workflow = slice_data.get("workflow")
        steps = workflow.get("steps") if isinstance(workflow, dict) else None
        index, _ = _by_id(steps, target.workflow_step_id)
        runtime_pointer = f"{runtime_pointer}/workflow/steps/{index}"
        target_id = (
            f"slice:{target.slice_id}/workflow-step:{target.workflow_step_id}"
        )

    mappings = source_map.get("mappings")
    if not isinstance(mappings, list):
        raise ValueError("Runtime source map has no mappings")
    mapping_matches = [
        item
        for item in mappings
        if isinstance(item, dict) and item.get("targetId") == target_id
    ]
    if len(mapping_matches) != 1:
        raise ValueError(f"Source-map target is missing or ambiguous: {target_id}")
    mapping = mapping_matches[0]
    mapped_runtime = mapping.get("runtimePointer")
    if target.item_id is None and mapped_runtime != runtime_pointer:
        raise ValueError(f"Source-map pointer differs for target: {target_id}")
    if target.item_id is not None and not runtime_pointer.startswith(
        f"{mapped_runtime}/"
    ):
        raise ValueError(f"Item target is outside its owning Block: {target.item_id}")
    blueprint_pointer = mapping.get("blueprintPointer")
    if not isinstance(blueprint_pointer, str):
        raise ValueError(f"Source-map Blueprint pointer is missing: {target_id}")
    if target.item_id is not None:
        blueprint_pointer = f"{blueprint_pointer}{runtime_pointer[len(mapped_runtime):]}"
    return ResolvedAnnotationTarget(target_id, blueprint_pointer, runtime_pointer)


def _preview_issue_candidate(annotation: CourseAnnotation, now: str):
    if annotation.classification == "runtime-bug" and annotation.status != "verified":
        code = "preview-runtime-bug"
    elif annotation.required and annotation.status == "orphaned":
        code = "preview-orphaned-annotation"
    elif annotation.required and annotation.status not in {"verified", "dismissed"}:
        code = "preview-required-annotation"
    else:
        return None
    return make_registered_issue(
        code=code,
        source="preview",
        message=(annotation.orphan_reason or annotation.text),
        seen_at=now,
        target={"annotationId": annotation.id},
        evidence=(".course-work/annotations.json",),
        remediation=(
            "Fix the renderer/runtime behavior and verify it in a new G7 preview."
            if code == "preview-runtime-bug"
            else "Resolve this annotation and verify the result in a current G7 preview."
        ),
    )


def _sync_preview_issues(root: Path, store: AnnotationStore, now: str) -> tuple[str, ...]:
    issues = IssueStore.load(root / ".course-work/issues.json")
    candidates = [
        candidate
        for candidate in (
            _preview_issue_candidate(annotation, now) for annotation in store.all()
        )
        if candidate is not None
    ]
    fingerprints = {candidate.fingerprint for candidate in candidates}
    for candidate in candidates:
        issues.upsert(candidate)
    for issue in issues.all():
        if (
            issue.source == "preview"
            and issue.gate_id == "G7"
            and issue.fingerprint not in fingerprints
            and issue.status != "resolved"
        ):
            issues.resolve(issue.id, now)
    issues.save()
    return tuple(
        issue.id
        for issue in issues.all()
        if issue.source == "preview" and issue.gate_id == "G7" and issue.status == "active"
    )


def _sync_session_pending_annotations(
    root: Path,
    store: AnnotationStore,
    now: str,
) -> None:
    from course_toolkit.workflow import SESSION_RELATIVE_PATH, load_session, save_session

    if not (root / SESSION_RELATIVE_PATH).is_file():
        return
    session = load_session(root)
    session.pending_annotation_ids = [
        annotation.id
        for annotation in store.all()
        if (
            annotation.classification == "runtime-bug"
            and annotation.status != "verified"
        )
        or (
            annotation.required
            and annotation.status not in {"verified", "dismissed"}
        )
    ]
    session.updated_at = now
    save_session(root, session)


def reconcile_annotations(root: Path, now: str) -> AnnotationReconciliationResult:
    from course_toolkit.workflow import verify_g5_compilation

    root = root.resolve()
    verify_g5_compilation(root)
    document = load_json(root / "course/course.json")
    source_map = load_json(root / ".course-work/course-runtime-source-map.json")
    current_hash = canonical_json_hash(document)
    store = AnnotationStore.load(root / ".course-work/annotations.json")
    resolved_ids = []
    rebound_ids = []
    orphaned_ids = []
    restored_ids = []
    for original in store.all():
        if original.status == "dismissed":
            continue
        try:
            resolve_annotation_target(original, document, source_map)
        except ValueError as exc:
            if original.status != "orphaned":
                store.transition(
                    original.id,
                    "orphaned",
                    now,
                    orphan_reason=str(exc),
                )
            else:
                store.replace(replace(original, orphan_reason=str(exc), updated_at=now))
            orphaned_ids.append(original.id)
            continue
        current = store.get(original.id)
        if current.status == "orphaned":
            current = store.transition(current.id, "open", now)
            restored_ids.append(current.id)
        if current.definition_hash != current_hash:
            store.replace(
                replace(
                    current,
                    definition_hash=current_hash,
                    rebound_from_definition_hash=current.definition_hash,
                    updated_at=now,
                )
            )
            rebound_ids.append(current.id)
        resolved_ids.append(current.id)
    store.save()
    active_issue_ids = _sync_preview_issues(root, store, now)
    _sync_session_pending_annotations(root, store, now)
    return AnnotationReconciliationResult(
        resolved_ids=tuple(resolved_ids),
        rebound_ids=tuple(rebound_ids),
        orphaned_ids=tuple(orphaned_ids),
        restored_ids=tuple(restored_ids),
        active_issue_ids=active_issue_ids,
    )
