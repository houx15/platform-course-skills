import mimetypes
from pathlib import Path
from typing import Dict, Optional

from course_toolkit.course_package_validation import VALIDATION_REPORT_RELATIVE_PATH
from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.workflow import hash_path, verify_g6_validation


ASSET_MANIFEST_SCHEMA_VERSION = "1.0"
ASSET_MANIFEST_RELATIVE_PATH = Path(".course-work/asset-manifest.json")
LOCAL_ASSET_ROOTS = (
    Path("assets"),
    Path("interactions"),
    Path("course/assets"),
    Path("course/interactions"),
)


def _safe_course_local_id(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in value)
        or value[0] not in "abcdefghijklmnopqrstuvwxyz"
    ):
        raise ValueError("courseLocalId must be a stable lowercase ID")
    return value


def _mime_type(source: str) -> str:
    guessed, _ = mimetypes.guess_type(source)
    return guessed or "application/octet-stream"


def _object_key(course_local_id: str, sha256: str, source: str) -> str:
    suffix = Path(source).suffix.lower()
    if not suffix or any(character not in ".abcdefghijklmnopqrstuvwxyz0123456789" for character in suffix):
        suffix = ""
    return f"courses/{course_local_id}/assets/{sha256[:2]}/{sha256}{suffix}"


def _valid_remote(remote: object, sha256: str, object_key: str) -> bool:
    return (
        isinstance(remote, dict)
        and remote.get("uploadedSha256") == sha256
        and remote.get("objectKey") == object_key
        and isinstance(remote.get("verifiedAt"), str)
        and bool(remote["verifiedAt"])
    )


def _local_only_paths(root: Path, referenced: set[str]) -> list[str]:
    observations = []
    for relative_root in LOCAL_ASSET_ROOTS:
        asset_root = root / relative_root
        if not asset_root.is_dir() or asset_root.is_symlink():
            continue
        for path in asset_root.rglob("*"):
            if (
                not path.is_file()
                or path.is_symlink()
                or path.suffix.lower() == ".zip"
                or path.name == ".DS_Store"
            ):
                continue
            relative = path.relative_to(root).as_posix()
            if relative not in referenced:
                observations.append(relative)
    return sorted(set(observations))


def build_asset_manifest(
    root: Path,
    course_local_id: str,
    *,
    previous_manifest: Optional[dict] = None,
) -> dict:
    course_local_id = _safe_course_local_id(course_local_id)
    root = root.resolve()
    verify_g6_validation(root)
    report = load_json(root / VALIDATION_REPORT_RELATIVE_PATH)
    document = load_json(root / "course/course.json")
    previous = previous_manifest
    if previous is None and (root / ASSET_MANIFEST_RELATIVE_PATH).is_file():
        previous = load_json(root / ASSET_MANIFEST_RELATIVE_PATH)
    if previous is not None:
        if not isinstance(previous, dict) or previous.get("schemaVersion") != ASSET_MANIFEST_SCHEMA_VERSION:
            raise ValueError("Previous asset manifest has an unsupported schemaVersion")
        if previous.get("courseLocalId") != course_local_id:
            raise ValueError("Previous asset manifest belongs to a different courseLocalId")
    previous_by_hash = {
        entry.get("sha256"): entry
        for entry in (previous or {}).get("entries", [])
        if isinstance(entry, dict) and isinstance(entry.get("sha256"), str)
    }

    grouped: Dict[str, dict] = {}
    referenced = set()
    for asset in report.get("assets", []):
        if not isinstance(asset, dict):
            raise ValueError("G6 report contains invalid asset evidence")
        source = asset.get("source")
        sha256 = asset.get("sha256")
        size_bytes = asset.get("sizeBytes")
        if (
            not isinstance(source, str)
            or not isinstance(sha256, str)
            or not isinstance(size_bytes, int)
        ):
            raise ValueError("G6 report contains incomplete asset evidence")
        referenced.add(source)
        entry = grouped.setdefault(
            sha256,
            {
                "sha256": sha256,
                "sizeBytes": size_bytes,
                "sources": [],
                "roles": set(),
                "runtimePaths": set(),
            },
        )
        if entry["sizeBytes"] != size_bytes:
            raise ValueError("Equal asset hash has inconsistent size evidence")
        entry["sources"].append(source)
        entry["roles"].update(asset.get("roles", []))
        entry["runtimePaths"].update(asset.get("runtimePaths", []))

    entries = []
    for sha256, grouped_entry in sorted(grouped.items()):
        sources = sorted(set(grouped_entry["sources"]))
        suffixes = {Path(source).suffix.lower() for source in sources}
        mime_types = {_mime_type(source) for source in sources}
        if len(suffixes) != 1 or len(mime_types) != 1:
            raise ValueError(
                f"Equal asset bytes have conflicting media identity: {sources}"
            )
        canonical_source = sources[0]
        object_key = _object_key(course_local_id, sha256, canonical_source)
        prior_entry = previous_by_hash.get(sha256)
        prior_remote = prior_entry.get("remote") if isinstance(prior_entry, dict) else None
        remote = prior_remote if _valid_remote(prior_remote, sha256, object_key) else None
        entries.append(
            {
                "sha256": sha256,
                "sizeBytes": grouped_entry["sizeBytes"],
                "extension": Path(canonical_source).suffix.lower(),
                "mimeType": _mime_type(canonical_source),
                "objectKey": object_key,
                "sources": sources,
                "roles": sorted(grouped_entry["roles"]),
                "runtimePaths": sorted(grouped_entry["runtimePaths"]),
                "state": "reusable" if remote is not None else "upload-required",
                "remote": remote,
            }
        )
    return {
        "schemaVersion": ASSET_MANIFEST_SCHEMA_VERSION,
        "courseLocalId": course_local_id,
        "courseId": document["course"]["id"],
        "courseDefinitionHash": report["courseDefinitionHash"],
        "validationReportHash": hash_path(root / VALIDATION_REPORT_RELATIVE_PATH),
        "assetSetHash": report["assetSetHash"],
        "entries": entries,
        "localOnlyPaths": _local_only_paths(root, referenced),
    }


def write_asset_manifest(root: Path, manifest: dict) -> Path:
    root = root.resolve()
    path = root / ASSET_MANIFEST_RELATIVE_PATH
    write_json_atomic(path, manifest)
    return path
