from pathlib import Path
from typing import Dict, List

from course_toolkit.annotations import AnnotationStore
from course_toolkit.course_compiler import canonical_json_hash
from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.workflow import hash_path


PREVIEW_EVIDENCE_SCHEMA_VERSION = "1.0"
PREVIEW_MANIFEST_RELATIVE_PATH = Path(".course-work/preview-manifest.json")
ROOT = Path(__file__).resolve().parent.parent
RUNTIME_SNAPSHOT = ROOT / "course-contract.snapshot.json"
PREVIEW_BUNDLE = ROOT / "course_toolkit/runtime_dist/preview"
CLIENT_FIELDS = {
    "viewport",
    "visitedSliceIds",
    "exercisedEvents",
    "runtimeErrors",
    "teacherConfirmed",
    "completedAt",
}
EVENT_FIELDS = {"id", "type", "sourceId", "sliceId"}


class PreviewEvidenceError(ValueError):
    pass


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PreviewEvidenceError(f"{field} must be a non-empty string")
    return value


def _course_slices(document: dict) -> List[str]:
    try:
        slices = [
            slice_data["id"]
            for part in document["course"]["parts"]
            for slice_data in part["slices"]
        ]
    except (KeyError, TypeError) as exc:
        raise PreviewEvidenceError("course definition has unreadable Slice structure") from exc
    if not slices or any(not isinstance(slice_id, str) for slice_id in slices):
        raise PreviewEvidenceError("course definition must contain stable Slice IDs")
    return slices


def _validate_viewport(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {"width", "height"}:
        raise PreviewEvidenceError("viewport must contain width and height")
    width, height = value.get("width"), value.get("height")
    if (
        isinstance(width, bool)
        or isinstance(height, bool)
        or not isinstance(width, int)
        or not isinstance(height, int)
        or width < 1024
        or height < 600
    ):
        raise PreviewEvidenceError("preview review requires a desktop viewport of at least 1024x600")
    return {"width": width, "height": height}


def _validate_events(value: object, slice_ids: List[str]) -> List[dict]:
    if not isinstance(value, list):
        raise PreviewEvidenceError("exercisedEvents must be an array")
    events = []
    seen = set()
    for raw in value:
        if not isinstance(raw, dict) or set(raw) != EVENT_FIELDS:
            raise PreviewEvidenceError("each exercised event must contain id, type, sourceId, and sliceId")
        event = {
            "id": _string(raw.get("id"), "event id"),
            "type": _string(raw.get("type"), "event type"),
            "sourceId": _string(raw.get("sourceId"), "event sourceId"),
            "sliceId": raw.get("sliceId"),
        }
        if event["sliceId"] is not None and event["sliceId"] not in slice_ids:
            raise PreviewEvidenceError("exercised event refers to an unknown Slice")
        if event["id"] not in seen:
            events.append(event)
            seen.add(event["id"])
    return events


def _load_annotations(root: Path, definition_hash: str, completed_at: str) -> tuple:
    path = root / ".course-work/annotations.json"
    store = AnnotationStore.load(path)
    changed = False
    for annotation in store.all():
        if annotation.status == "applied" and annotation.definition_hash == definition_hash:
            store.transition(
                annotation.id,
                "verified",
                completed_at,
                verified_against_definition_hash=definition_hash,
            )
            changed = True
    if changed:
        store.save()
    unresolved = [
        annotation
        for annotation in store.all()
        if annotation.required and annotation.status not in {"verified", "dismissed"}
    ]
    if unresolved:
        raise PreviewEvidenceError(f"required annotation is unresolved: {unresolved[0].id}")
    document = (
        load_json(path)
        if path.is_file()
        else {"schemaVersion": "1.0", "annotations": []}
    )
    return document, canonical_json_hash(document)


def _renderer_record(snapshot: dict) -> dict:
    packages = snapshot.get("packages")
    if not isinstance(packages, dict):
        raise PreviewEvidenceError("runtime snapshot does not identify renderer packages")
    return {
        "upstreamTag": snapshot.get("upstreamTag"),
        "upstreamCommit": snapshot.get("upstreamCommit"),
        "packages": {
            name: {
                "packageVersion": record.get("packageVersion"),
                "treeHash": record.get("treeHash"),
            }
            for name, record in sorted(packages.items())
        },
    }


def record_preview_evidence(root: Path, client_evidence: object) -> dict:
    root = root.resolve()
    if not isinstance(client_evidence, dict) or set(client_evidence) != CLIENT_FIELDS:
        raise PreviewEvidenceError("preview evidence has unknown or missing fields")
    if client_evidence.get("teacherConfirmed") is not True:
        raise PreviewEvidenceError("teacher completion must be explicitly confirmed")
    completed_at = _string(client_evidence.get("completedAt"), "completedAt")
    document = load_json(root / "course/course.json")
    definition_hash = canonical_json_hash(document)
    slice_ids = _course_slices(document)
    visited = client_evidence.get("visitedSliceIds")
    if not isinstance(visited, list) or any(not isinstance(item, str) for item in visited):
        raise PreviewEvidenceError("visitedSliceIds must be an array of stable Slice IDs")
    unknown = sorted(set(visited).difference(slice_ids))
    if unknown:
        raise PreviewEvidenceError(f"preview visited an unknown Slice: {unknown[0]}")
    missing = [slice_id for slice_id in slice_ids if slice_id not in visited]
    if missing:
        raise PreviewEvidenceError(f"Slice was not reviewed: {missing[0]}")
    runtime_errors = client_evidence.get("runtimeErrors")
    if not isinstance(runtime_errors, list) or any(
        not isinstance(error, str) or not error.strip() for error in runtime_errors
    ):
        raise PreviewEvidenceError("runtimeErrors must be an array of messages")
    if runtime_errors:
        raise PreviewEvidenceError(f"preview has a runtime error: {runtime_errors[0]}")
    annotation_document, annotation_hash = _load_annotations(
        root, definition_hash, completed_at
    )
    snapshot = load_json(RUNTIME_SNAPSHOT)
    manifest = {
        "schemaVersion": PREVIEW_EVIDENCE_SCHEMA_VERSION,
        "courseId": document["course"]["id"],
        "definitionHash": definition_hash,
        "renderer": _renderer_record(snapshot),
        "previewBundleHash": hash_path(PREVIEW_BUNDLE),
        "viewport": _validate_viewport(client_evidence.get("viewport")),
        "visitedSliceIds": [slice_id for slice_id in slice_ids if slice_id in set(visited)],
        "exercisedEvents": _validate_events(client_evidence.get("exercisedEvents"), slice_ids),
        "annotationHash": annotation_hash,
        "annotationCount": len(annotation_document["annotations"]),
        "runtimeErrors": [],
        "teacherConfirmed": True,
        "completedAt": completed_at,
    }
    write_json_atomic(root / PREVIEW_MANIFEST_RELATIVE_PATH, manifest)
    return manifest


def verify_g7_preview(root: Path) -> Dict[str, str]:
    root = root.resolve()
    path = root / PREVIEW_MANIFEST_RELATIVE_PATH
    if path.is_symlink() or not path.is_file():
        raise PreviewEvidenceError("G7 preview manifest is missing")
    manifest = load_json(path)
    if manifest.get("schemaVersion") != PREVIEW_EVIDENCE_SCHEMA_VERSION:
        raise PreviewEvidenceError("G7 preview manifest schema is unsupported")
    document = load_json(root / "course/course.json")
    if manifest.get("definitionHash") != canonical_json_hash(document):
        raise PreviewEvidenceError("G7 preview definition hash is stale")
    snapshot = load_json(RUNTIME_SNAPSHOT)
    renderer = manifest.get("renderer")
    if not isinstance(renderer, dict) or renderer.get("upstreamTag") != snapshot.get("upstreamTag"):
        raise PreviewEvidenceError("G7 preview renderer tag is stale")
    if renderer != _renderer_record(snapshot):
        raise PreviewEvidenceError("G7 preview renderer packages are stale")
    bundle_hash = hash_path(PREVIEW_BUNDLE)
    if manifest.get("previewBundleHash") != bundle_hash:
        raise PreviewEvidenceError("G7 preview bundle is stale")
    expected_slices = _course_slices(document)
    if manifest.get("visitedSliceIds") != expected_slices:
        raise PreviewEvidenceError("G7 preview did not review every Slice")
    if manifest.get("runtimeErrors") != []:
        raise PreviewEvidenceError("G7 preview contains runtime errors")
    if manifest.get("teacherConfirmed") is not True or not manifest.get("completedAt"):
        raise PreviewEvidenceError("G7 preview lacks teacher completion")
    annotation_path = root / ".course-work/annotations.json"
    annotation_document = (
        load_json(annotation_path)
        if annotation_path.is_file()
        else {"schemaVersion": "1.0", "annotations": []}
    )
    if manifest.get("annotationHash") != canonical_json_hash(annotation_document):
        raise PreviewEvidenceError("G7 preview annotation hash is stale")
    unresolved = [
        annotation
        for annotation in AnnotationStore.load(annotation_path).all()
        if annotation.required and annotation.status not in {"verified", "dismissed"}
    ]
    if unresolved:
        raise PreviewEvidenceError(f"G7 has an unresolved required annotation: {unresolved[0].id}")
    return {
        ".course-work/preview-manifest.json": hash_path(path),
        "@toolkit/course-preview-bundle": bundle_hash,
    }
