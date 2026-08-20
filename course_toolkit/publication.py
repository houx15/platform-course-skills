import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

from course_toolkit.course_compiler import canonical_json_hash
from course_toolkit.course_package_validation import VALIDATION_REPORT_RELATIVE_PATH
from course_toolkit.decisions import DecisionStore
from course_toolkit.issues import IssueStore, make_registered_issue
from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.workflow import (
    hash_path,
    load_session,
    reconcile_current_session,
    save_session,
    verify_g6_validation,
)


ASSET_MANIFEST_SCHEMA_VERSION = "1.0"
ASSET_MANIFEST_RELATIVE_PATH = Path(".course-work/asset-manifest.json")
PUBLISH_STATE_SCHEMA_VERSION = "1.0"
PUBLISH_STATE_RELATIVE_PATH = Path(".course-work/publish-state.json")
REMOTE_DISCOVERY_SCHEMA_VERSION = "1.0"
PUBLICATION_REVIEW_EVIDENCE_SCHEMA_VERSION = "1.0"
PUBLICATION_PREFLIGHT_SCHEMA_VERSION = "1.0"
PUBLICATION_PREFLIGHT_RELATIVE_PATH = Path(".course-work/publication-preflight.json")
PUBLICATION_REVIEW_EVIDENCE_RELATIVE_PATH = Path(
    ".course-work/publication-review-evidence.json"
)
REMOTE_DISCOVERY_RELATIVE_PATH = Path(".course-work/remote-discovery.json")
PUBLICATION_DECISION_ID = "decision-publication-preflight"
PUBLICATION_ISSUE_CODES = frozenset(
    {
        "publication-identity-conflict",
        "publication-review-stale",
        "publication-asset-state-stale",
    }
)
LOCAL_ASSET_ROOTS = (
    Path("assets"),
    Path("interactions"),
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
        "localOnlyPaths": _local_only_paths(root / "course", referenced),
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


@dataclass(frozen=True)
class PublicationReviewEvidence:
    schema_version: str
    status: str
    renderer_backed: bool
    course_definition_hash: str
    validation_report_hash: str
    preview_manifest_hash: str
    review_report_hash: str
    reviewed_at: str

    def __post_init__(self) -> None:
        if self.schema_version != PUBLICATION_REVIEW_EVIDENCE_SCHEMA_VERSION:
            raise ValueError(
                "Unsupported publication review evidence schemaVersion: "
                f"{self.schema_version}"
            )
        if self.status != "approved":
            raise ValueError("Publication review evidence must be approved")
        if self.renderer_backed is not True:
            raise ValueError("Publication review evidence must be renderer-backed")
        _optional_hash(self.course_definition_hash, "courseDefinitionHash")
        _optional_hash(self.validation_report_hash, "validationReportHash")
        _optional_hash(self.preview_manifest_hash, "previewManifestHash")
        _optional_hash(self.review_report_hash, "reviewReportHash")
        if None in (
            self.course_definition_hash,
            self.validation_report_hash,
            self.preview_manifest_hash,
            self.review_report_hash,
        ):
            raise ValueError("Publication review evidence hashes are required")
        _required_text(self.reviewed_at, "reviewedAt")

    def as_dict(self) -> dict:
        return {
            "schemaVersion": self.schema_version,
            "status": self.status,
            "rendererBacked": self.renderer_backed,
            "courseDefinitionHash": self.course_definition_hash,
            "validationReportHash": self.validation_report_hash,
            "previewManifestHash": self.preview_manifest_hash,
            "reviewReportHash": self.review_report_hash,
            "reviewedAt": self.reviewed_at,
        }

    @classmethod
    def from_dict(cls, data: object) -> "PublicationReviewEvidence":
        if not isinstance(data, dict):
            raise ValueError("Publication review evidence must be an object")
        fields = {
            "schemaVersion",
            "status",
            "rendererBacked",
            "courseDefinitionHash",
            "validationReportHash",
            "previewManifestHash",
            "reviewReportHash",
            "reviewedAt",
        }
        unknown = sorted(set(data).difference(fields))
        missing = sorted(fields.difference(data))
        if unknown:
            raise ValueError(f"Unknown publication review evidence field: {unknown[0]}")
        if missing:
            raise ValueError(f"Missing publication review evidence field: {missing[0]}")
        return cls(
            schema_version=data["schemaVersion"],
            status=data["status"],
            renderer_backed=data["rendererBacked"],
            course_definition_hash=data["courseDefinitionHash"],
            validation_report_hash=data["validationReportHash"],
            preview_manifest_hash=data["previewManifestHash"],
            review_report_hash=data["reviewReportHash"],
            reviewed_at=data["reviewedAt"],
        )


def _verify_review_evidence(
    root: Path,
    evidence: PublicationReviewEvidence,
) -> None:
    session = load_session(root)
    reconcile_current_session(
        root,
        session,
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    if "G8" not in session.completed_gate_ids:
        raise PublicationBlocked("G8 final review is not complete")
    report_path = root / VALIDATION_REPORT_RELATIVE_PATH
    report = load_json(report_path)
    expected = {
        "courseDefinitionHash": report.get("courseDefinitionHash"),
        "validationReportHash": hash_path(report_path),
        "previewManifestHash": hash_path(root / ".course-work/preview-manifest.json"),
        "reviewReportHash": hash_path(root / ".course-work/review-report.json"),
    }
    actual = {
        "courseDefinitionHash": evidence.course_definition_hash,
        "validationReportHash": evidence.validation_report_hash,
        "previewManifestHash": evidence.preview_manifest_hash,
        "reviewReportHash": evidence.review_report_hash,
    }
    mismatch = next(
        (field for field, value in actual.items() if value != expected[field]),
        None,
    )
    if mismatch is not None:
        raise PublicationBlocked(f"Publication review evidence is stale: {mismatch}")


def _load_current_asset_manifest(root: Path, course_local_id: str) -> dict:
    path = root / ASSET_MANIFEST_RELATIVE_PATH
    if path.is_symlink() or not path.is_file():
        raise PublicationBlocked("Current publication asset manifest is missing")
    current = load_json(path)
    rebuilt = build_asset_manifest(
        root,
        course_local_id,
        previous_manifest=current,
    )
    if canonical_json_hash(current) != canonical_json_hash(rebuilt):
        raise PublicationBlocked("Current publication asset manifest is stale")
    return current


def _asset_plan(manifest: dict, discovery: RemoteDiscoverySnapshot) -> dict:
    discovered_by_hash = {
        asset["sha256"]: asset["objectKey"] for asset in discovery.known_assets
    }
    discovered_by_key = {
        asset["objectKey"]: asset["sha256"] for asset in discovery.known_assets
    }
    upload = []
    reuse = []
    for entry in manifest.get("entries", []):
        if not isinstance(entry, dict):
            raise PublicationBlocked("Current publication asset manifest is invalid")
        sha256 = entry.get("sha256")
        object_key = entry.get("objectKey")
        if not isinstance(sha256, str) or not isinstance(object_key, str):
            raise PublicationBlocked("Current publication asset manifest is incomplete")
        collision_hash = discovered_by_key.get(object_key)
        if collision_hash is not None and collision_hash != sha256:
            raise PublicationBlocked(
                f"Remote asset key has conflicting bytes: {object_key}"
            )
        item = {
            "sha256": sha256,
            "sizeBytes": entry.get("sizeBytes"),
            "mimeType": entry.get("mimeType"),
            "objectKey": object_key,
            "sources": entry.get("sources", []),
        }
        if entry.get("state") == "reusable":
            item["reuseProof"] = "asset-manifest"
            reuse.append(item)
        elif discovered_by_hash.get(sha256) == object_key:
            item["reuseProof"] = "remote-discovery"
            reuse.append(item)
        else:
            upload.append(item)
    return {"upload": upload, "reuse": reuse}


def _publisher_issue(code: str, message: str, now: str):
    return make_registered_issue(
        code=code,
        source="publisher",
        message=message,
        gate_id="G9",
        seen_at=now,
        target={"scope": "publication-preflight"},
        remediation="Refresh the affected evidence and prepare publication again.",
    )


def _sync_publication_issues(root: Path, candidates: list, now: str) -> None:
    store = IssueStore.load(root / ".course-work/issues.json")
    active_candidate_codes = {candidate.code for candidate in candidates}
    for candidate in candidates:
        store.upsert(candidate)
    for issue in store.all():
        if (
            issue.source == "publisher"
            and issue.gate_id == "G9"
            and issue.code in PUBLICATION_ISSUE_CODES
            and issue.code not in active_candidate_codes
            and issue.status == "active"
        ):
            store.resolve(issue.id, now)
    store.save()
    session = load_session(root)
    session.active_issue_ids = [
        issue.id for issue in store.all() if issue.status == "active"
    ]
    session.updated_at = now
    save_session(root, session)


def prepare_publication_preflight(
    *,
    root: Path,
    discovery: RemoteDiscoverySnapshot,
    review_evidence: PublicationReviewEvidence,
    intended_status: str,
    visibility: str,
    now: str,
) -> dict:
    root = root.resolve()
    if intended_status not in {"preview", "published"}:
        raise ValueError("intendedStatus must be preview or published")
    if visibility not in {"private", "unlisted", "public"}:
        raise ValueError("visibility must be private, unlisted, or public")

    session = load_session(root)
    reconcile_current_session(root, session, now)

    candidates = []
    state = None
    identity = None
    manifest = None
    asset_plan = None

    try:
        state = load_publish_state(root)
        identity = resolve_publication_identity(state, discovery)
    except (ValueError, PublicationBlocked) as exc:
        candidates.append(_publisher_issue("publication-identity-conflict", str(exc), now))

    try:
        verify_g6_validation(root)
        course_local_id = state.course_local_id if state is not None else load_session(root).course_local_id
        manifest = _load_current_asset_manifest(root, course_local_id)
        asset_plan = _asset_plan(manifest, discovery)
    except (ValueError, PublicationBlocked) as exc:
        candidates.append(_publisher_issue("publication-asset-state-stale", str(exc), now))

    try:
        _verify_review_evidence(root, review_evidence)
    except (ValueError, PublicationBlocked) as exc:
        candidates.append(_publisher_issue("publication-review-stale", str(exc), now))

    _sync_publication_issues(root, candidates, now)
    if candidates:
        raise PublicationBlocked("; ".join(candidate.message for candidate in candidates))
    assert state is not None and identity is not None and manifest is not None
    assert asset_plan is not None

    preflight = {
        "schemaVersion": PUBLICATION_PREFLIGHT_SCHEMA_VERSION,
        "courseLocalId": state.course_local_id,
        "courseId": manifest["courseId"],
        "slug": state.slug,
        "mode": identity.mode,
        "intendedStatus": intended_status,
        "visibility": visibility,
        "remote": {
            "courseId": identity.remote_course_id,
            "expectedRevision": identity.expected_remote_revision,
            "discoveryHash": canonical_json_hash(discovery.as_dict()),
            "observedAt": discovery.observed_at,
        },
        "definition": {
            "path": "course/course.json",
            "sha256": manifest["courseDefinitionHash"],
        },
        "evidence": {
            "validationReportHash": manifest["validationReportHash"],
            "reviewEvidenceHash": canonical_json_hash(review_evidence.as_dict()),
            "previewManifestHash": review_evidence.preview_manifest_hash,
            "reviewReportHash": review_evidence.review_report_hash,
            "assetManifestHash": hash_path(root / ASSET_MANIFEST_RELATIVE_PATH),
        },
        "assets": asset_plan,
        "limitations": {
            "liveAdapterRequired": True,
            "remoteWritePerformed": False,
            "credentialsRead": False,
        },
    }
    write_json_atomic(root / REMOTE_DISCOVERY_RELATIVE_PATH, discovery.as_dict())
    write_json_atomic(
        root / PUBLICATION_REVIEW_EVIDENCE_RELATIVE_PATH,
        review_evidence.as_dict(),
    )
    write_json_atomic(root / PUBLICATION_PREFLIGHT_RELATIVE_PATH, preflight)

    context_hash = canonical_json_hash(preflight)
    decisions = DecisionStore.load(root / ".course-work/decisions.json")
    try:
        existing = decisions.get(PUBLICATION_DECISION_ID)
    except ValueError:
        existing = None
    if existing is not None and existing.context_hash != context_hash:
        decisions.reconcile_context(PUBLICATION_DECISION_ID, context_hash, now)
    decision = decisions.request(
        PUBLICATION_DECISION_ID,
        "Approve this exact publication dry run?",
        context_hash,
        context={
            "preflightHash": context_hash,
            "mode": identity.mode,
            "intendedStatus": intended_status,
            "visibility": visibility,
            "uploadCount": len(asset_plan["upload"]),
            "reuseCount": len(asset_plan["reuse"]),
        },
        options=("approve", "revise"),
        affected_artifact_ids=(PUBLICATION_PREFLIGHT_RELATIVE_PATH.as_posix(),),
        requested_at=now,
    )
    decisions.save()
    session = load_session(root)
    pending = set(session.pending_decision_ids)
    if decision.status == "pending":
        pending.add(PUBLICATION_DECISION_ID)
    else:
        pending.discard(PUBLICATION_DECISION_ID)
    session.pending_decision_ids = sorted(pending)
    save_session(root, session)
    return preflight


def publication_preflight_status(root: Path) -> dict:
    root = root.resolve()
    session = load_session(root)
    reconcile_current_session(
        root,
        session,
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    path = root / PUBLICATION_PREFLIGHT_RELATIVE_PATH
    if path.is_symlink() or not path.is_file():
        raise PublicationBlocked("Publication preflight is missing")
    preflight = load_json(path)
    context_hash = canonical_json_hash(preflight)
    stale_reasons = []
    try:
        if preflight.get("schemaVersion") != PUBLICATION_PREFLIGHT_SCHEMA_VERSION:
            stale_reasons.append("unsupported-preflight-schema")
        definition = load_json(root / "course/course.json")
        if canonical_json_hash(definition) != preflight["definition"]["sha256"]:
            stale_reasons.append("course-definition-changed")
        current_hashes = {
            "validationReportHash": hash_path(root / VALIDATION_REPORT_RELATIVE_PATH),
            "previewManifestHash": hash_path(
                root / ".course-work/preview-manifest.json"
            ),
            "reviewReportHash": hash_path(root / ".course-work/review-report.json"),
            "assetManifestHash": hash_path(root / ASSET_MANIFEST_RELATIVE_PATH),
        }
        for key, current_hash in current_hashes.items():
            if preflight["evidence"][key] != current_hash:
                stale_reasons.append(f"{key}-changed")
        current_review = PublicationReviewEvidence.from_dict(
            load_json(root / PUBLICATION_REVIEW_EVIDENCE_RELATIVE_PATH)
        )
        if (
            canonical_json_hash(current_review.as_dict())
            != preflight["evidence"]["reviewEvidenceHash"]
        ):
            stale_reasons.append("review-evidence-changed")
        current_discovery = RemoteDiscoverySnapshot.from_dict(
            load_json(root / REMOTE_DISCOVERY_RELATIVE_PATH)
        )
        if (
            canonical_json_hash(current_discovery.as_dict())
            != preflight["remote"]["discoveryHash"]
        ):
            stale_reasons.append("remote-discovery-changed")
        state = load_publish_state(root)
        if state.course_local_id != preflight["courseLocalId"] or state.slug != preflight["slug"]:
            stale_reasons.append("publish-identity-changed")
        if preflight["mode"] == "create":
            if state.remote_course_id is not None:
                stale_reasons.append("publish-mode-changed")
        elif (
            state.remote_course_id != preflight["remote"]["courseId"]
            or state.last_known_remote_revision
            != preflight["remote"]["expectedRevision"]
        ):
            stale_reasons.append("remote-revision-changed")
    except (KeyError, TypeError, ValueError):
        stale_reasons.append("preflight-evidence-unreadable")
    stale_reasons = sorted(set(stale_reasons))
    decisions = DecisionStore.load(root / ".course-work/decisions.json")
    try:
        decision = decisions.get(PUBLICATION_DECISION_ID)
    except ValueError:
        return {
            "preflightHash": context_hash,
            "decisionStatus": "missing",
            "current": not stale_reasons,
            "staleReasons": stale_reasons,
            "approved": False,
        }
    answer = decision.answer if isinstance(decision.answer, dict) else {}
    approved = (
        decision.status == "confirmed"
        and decision.context_hash == context_hash
        and answer.get("choice") == "approve"
        and isinstance(answer.get("rationale"), str)
        and bool(answer["rationale"].strip())
        and not stale_reasons
    )
    return {
        "preflightHash": context_hash,
        "decisionStatus": decision.status,
        "current": not stale_reasons,
        "staleReasons": stale_reasons,
        "approved": approved,
    }
