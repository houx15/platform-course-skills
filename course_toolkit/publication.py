import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from course_toolkit.course_package_validation import VALIDATION_REPORT_RELATIVE_PATH
from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.workflow import hash_path, verify_g6_validation


ASSET_MANIFEST_SCHEMA_VERSION = "1.0"
ASSET_MANIFEST_RELATIVE_PATH = Path(".course-work/asset-manifest.json")
PUBLISH_STATE_SCHEMA_VERSION = "1.0"
PUBLISH_STATE_RELATIVE_PATH = Path(".course-work/publish-state.json")
REMOTE_DISCOVERY_SCHEMA_VERSION = "1.0"
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


class PublicationBlocked(ValueError):
    pass


def _optional_hash(value: Optional[str], field: str) -> None:
    if value is None:
        return
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field} must be a SHA-256 hash")


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value


@dataclass(frozen=True)
class PublishState:
    schema_version: str
    course_local_id: str
    slug: str
    remote_course_id: Optional[str]
    remote_status: Optional[str]
    last_known_remote_revision: Optional[str]
    last_uploaded_definition_hash: Optional[str]
    last_published_definition_hash: Optional[str]
    last_publish_operation_id: Optional[str]
    verified_at: Optional[str]

    def __post_init__(self) -> None:
        if self.schema_version != PUBLISH_STATE_SCHEMA_VERSION:
            raise ValueError(f"Unsupported publish state schemaVersion: {self.schema_version}")
        _safe_course_local_id(self.course_local_id)
        _safe_course_local_id(self.slug)
        _optional_hash(
            self.last_uploaded_definition_hash,
            "lastUploadedDefinitionHash",
        )
        _optional_hash(
            self.last_published_definition_hash,
            "lastPublishedDefinitionHash",
        )
        _optional_hash(self.last_publish_operation_id, "lastPublishOperationId")
        remote_fields = (
            self.remote_status,
            self.last_known_remote_revision,
            self.last_uploaded_definition_hash,
            self.last_published_definition_hash,
            self.last_publish_operation_id,
            self.verified_at,
        )
        if self.remote_course_id is None:
            if any(value is not None for value in remote_fields):
                raise ValueError("remoteCourseId is required before storing remote state")
        else:
            _required_text(self.remote_course_id, "remoteCourseId")
            if self.remote_status not in {"preview", "published"}:
                raise ValueError("remoteStatus must be preview or published")
            _required_text(
                self.last_known_remote_revision,
                "lastKnownRemoteRevision",
            )
            _required_text(self.verified_at, "verifiedAt")

    def as_dict(self) -> dict:
        return {
            "schemaVersion": self.schema_version,
            "courseLocalId": self.course_local_id,
            "slug": self.slug,
            "remoteCourseId": self.remote_course_id,
            "remoteStatus": self.remote_status,
            "lastKnownRemoteRevision": self.last_known_remote_revision,
            "lastUploadedDefinitionHash": self.last_uploaded_definition_hash,
            "lastPublishedDefinitionHash": self.last_published_definition_hash,
            "lastPublishOperationId": self.last_publish_operation_id,
            "verifiedAt": self.verified_at,
        }

    @classmethod
    def from_dict(cls, data: object) -> "PublishState":
        if not isinstance(data, dict):
            raise ValueError("Publish state must be an object")
        fields = {
            "schemaVersion",
            "courseLocalId",
            "slug",
            "remoteCourseId",
            "remoteStatus",
            "lastKnownRemoteRevision",
            "lastUploadedDefinitionHash",
            "lastPublishedDefinitionHash",
            "lastPublishOperationId",
            "verifiedAt",
        }
        unknown = sorted(set(data).difference(fields))
        missing = sorted(fields.difference(data))
        if unknown:
            raise ValueError(f"Unknown publish state field: {unknown[0]}")
        if missing:
            raise ValueError(f"Missing publish state field: {missing[0]}")
        return cls(
            schema_version=data["schemaVersion"],
            course_local_id=data["courseLocalId"],
            slug=data["slug"],
            remote_course_id=data["remoteCourseId"],
            remote_status=data["remoteStatus"],
            last_known_remote_revision=data["lastKnownRemoteRevision"],
            last_uploaded_definition_hash=data["lastUploadedDefinitionHash"],
            last_published_definition_hash=data["lastPublishedDefinitionHash"],
            last_publish_operation_id=data["lastPublishOperationId"],
            verified_at=data["verifiedAt"],
        )


def new_publish_state(course_local_id: str, slug: str) -> PublishState:
    return PublishState(
        schema_version=PUBLISH_STATE_SCHEMA_VERSION,
        course_local_id=course_local_id,
        slug=slug,
        remote_course_id=None,
        remote_status=None,
        last_known_remote_revision=None,
        last_uploaded_definition_hash=None,
        last_published_definition_hash=None,
        last_publish_operation_id=None,
        verified_at=None,
    )


def load_publish_state(root: Path) -> PublishState:
    return PublishState.from_dict(load_json(root.resolve() / PUBLISH_STATE_RELATIVE_PATH))


def write_publish_state(root: Path, state: PublishState) -> Path:
    path = root.resolve() / PUBLISH_STATE_RELATIVE_PATH
    write_json_atomic(path, state.as_dict())
    return path


@dataclass(frozen=True)
class RemoteDiscoverySnapshot:
    schema_version: str
    lookup_slug: str
    status: str
    observed_at: str
    course_local_id: Optional[str] = None
    remote_course_id: Optional[str] = None
    remote_status: Optional[str] = None
    remote_revision: Optional[str] = None
    definition_hash: Optional[str] = None
    known_assets: Tuple[dict, ...] = ()
    message: Optional[str] = None

    def __post_init__(self) -> None:
        if self.schema_version != REMOTE_DISCOVERY_SCHEMA_VERSION:
            raise ValueError(f"Unsupported discovery schemaVersion: {self.schema_version}")
        _safe_course_local_id(self.lookup_slug)
        if self.status not in {"found", "not-found", "ambiguous", "unavailable"}:
            raise ValueError(f"Unknown discovery status: {self.status}")
        _required_text(self.observed_at, "observedAt")
        seen_asset_hashes = set()
        seen_object_keys = set()
        for asset in self.known_assets:
            if not isinstance(asset, dict) or set(asset) != {"sha256", "objectKey"}:
                raise ValueError("knownAssets entry is invalid")
            _optional_hash(asset.get("sha256"), "knownAssets.sha256")
            if asset.get("sha256") is None:
                raise ValueError("knownAssets.sha256 is required")
            _required_text(asset.get("objectKey"), "knownAssets.objectKey")
            if asset["sha256"] in seen_asset_hashes:
                raise ValueError("knownAssets contains duplicate sha256")
            if asset["objectKey"] in seen_object_keys:
                raise ValueError("knownAssets contains duplicate objectKey")
            seen_asset_hashes.add(asset["sha256"])
            seen_object_keys.add(asset["objectKey"])
        remote_values = (
            self.course_local_id,
            self.remote_course_id,
            self.remote_status,
            self.remote_revision,
            self.definition_hash,
        )
        if self.status == "found":
            _safe_course_local_id(self.course_local_id)
            _required_text(self.remote_course_id, "remoteCourseId")
            if self.remote_status not in {"preview", "published"}:
                raise ValueError("remoteStatus must be preview or published")
            _required_text(self.remote_revision, "remoteRevision")
            _optional_hash(self.definition_hash, "definitionHash")
            if self.definition_hash is None:
                raise ValueError("definitionHash is required for found discovery")
            if self.message is not None:
                raise ValueError("Found discovery must not contain message")
        elif self.status == "not-found":
            if any(value is not None for value in remote_values) or self.known_assets:
                raise ValueError("not-found discovery must not contain remote state")
            if self.message is not None:
                raise ValueError("not-found discovery must not contain message")
        else:
            if any(value is not None for value in remote_values) or self.known_assets:
                raise ValueError(f"{self.status} discovery must not claim remote state")
            _required_text(self.message, "message")

    def as_dict(self) -> dict:
        return {
            "schemaVersion": self.schema_version,
            "lookupSlug": self.lookup_slug,
            "status": self.status,
            "observedAt": self.observed_at,
            "courseLocalId": self.course_local_id,
            "remoteCourseId": self.remote_course_id,
            "remoteStatus": self.remote_status,
            "remoteRevision": self.remote_revision,
            "definitionHash": self.definition_hash,
            "knownAssets": list(self.known_assets),
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: object) -> "RemoteDiscoverySnapshot":
        if not isinstance(data, dict):
            raise ValueError("Remote discovery snapshot must be an object")
        fields = {
            "schemaVersion",
            "lookupSlug",
            "status",
            "observedAt",
            "courseLocalId",
            "remoteCourseId",
            "remoteStatus",
            "remoteRevision",
            "definitionHash",
            "knownAssets",
            "message",
        }
        unknown = sorted(set(data).difference(fields))
        required = {"schemaVersion", "lookupSlug", "status", "observedAt"}
        if unknown:
            raise ValueError(f"Unknown discovery field: {unknown[0]}")
        missing = sorted(required.difference(data))
        if missing:
            raise ValueError(f"Missing discovery field: {missing[0]}")
        known_assets = data.get("knownAssets", [])
        if not isinstance(known_assets, list):
            raise ValueError("knownAssets must be an array")
        return cls(
            schema_version=data["schemaVersion"],
            lookup_slug=data["lookupSlug"],
            status=data["status"],
            observed_at=data["observedAt"],
            course_local_id=data.get("courseLocalId"),
            remote_course_id=data.get("remoteCourseId"),
            remote_status=data.get("remoteStatus"),
            remote_revision=data.get("remoteRevision"),
            definition_hash=data.get("definitionHash"),
            known_assets=tuple(known_assets),
            message=data.get("message"),
        )


@dataclass(frozen=True)
class PublicationIdentityResolution:
    mode: str
    remote_course_id: Optional[str]
    expected_remote_revision: Optional[str]


def resolve_publication_identity(
    state: PublishState,
    discovery: RemoteDiscoverySnapshot,
) -> PublicationIdentityResolution:
    if discovery.lookup_slug != state.slug:
        raise PublicationBlocked("Remote discovery lookup slug differs from publish state")
    if discovery.status in {"ambiguous", "unavailable"}:
        raise PublicationBlocked(
            f"Remote discovery is {discovery.status}: {discovery.message}"
        )
    if state.remote_course_id is None:
        if discovery.status == "found":
            raise PublicationBlocked(
                "A remote course already exists for this slug; reconcile identity before update"
            )
        if discovery.status != "not-found":
            raise PublicationBlocked("Create requires an explicit not-found discovery")
        return PublicationIdentityResolution("create", None, None)
    if discovery.status != "found":
        raise PublicationBlocked("Known remote course is absent from discovery")
    if (
        discovery.remote_course_id != state.remote_course_id
        or discovery.course_local_id != state.course_local_id
    ):
        raise PublicationBlocked("Remote course identity mismatch")
    if discovery.remote_revision != state.last_known_remote_revision:
        raise PublicationBlocked(
            "Remote revision changed; reconcile state before preparing an update"
        )
    return PublicationIdentityResolution(
        "update",
        state.remote_course_id,
        state.last_known_remote_revision,
    )
