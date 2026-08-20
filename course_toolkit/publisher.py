from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional, Protocol, Tuple

from course_toolkit.course_compiler import canonical_json_hash
from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.publication import (
    ASSET_MANIFEST_RELATIVE_PATH,
    PUBLICATION_PREFLIGHT_RELATIVE_PATH,
    PublicationBlocked,
    PublishState,
    RemoteDiscoverySnapshot,
    load_publish_state,
    publication_preflight_status,
    write_asset_manifest,
    write_publish_state,
)
from course_toolkit.workflow import hash_path


PUBLISHER_VERSION = "1.0"
PUBLICATION_OPERATION_SCHEMA_VERSION = "1.0"
PUBLICATION_OPERATION_RELATIVE_PATH = Path(".course-work/publication-operation.json")
ACTIVE_PHASES = frozenset(
    {"planned", "uploading", "submitting", "ambiguous", "verifying", "remote-verified"}
)


class AmbiguousPublicationResult(RuntimeError):
    """The adapter cannot tell whether a remote write took effect."""


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value


def _required_hash(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field} must be a SHA-256 hash")
    return value


@dataclass(frozen=True)
class AssetUploadResult:
    object_key: str
    uploaded_sha256: str
    etag: Optional[str]
    verified_at: str

    def __post_init__(self) -> None:
        _required_text(self.object_key, "objectKey")
        _required_hash(self.uploaded_sha256, "uploadedSha256")
        if self.etag is not None:
            _required_text(self.etag, "etag")
        _required_text(self.verified_at, "verifiedAt")

    def as_dict(self) -> dict:
        return {
            "objectKey": self.object_key,
            "uploadedSha256": self.uploaded_sha256,
            "etag": self.etag,
            "verifiedAt": self.verified_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AssetUploadResult":
        return cls(
            object_key=data["objectKey"],
            uploaded_sha256=data["uploadedSha256"],
            etag=data.get("etag"),
            verified_at=data["verifiedAt"],
        )


@dataclass(frozen=True)
class CourseWriteRequest:
    course_local_id: str
    slug: str
    definition: dict
    definition_hash: str
    intended_status: str
    visibility: str
    assets: Tuple[dict, ...]
    idempotency_key: str


@dataclass(frozen=True)
class CourseWriteResult:
    remote_course_id: str
    revision: str

    def __post_init__(self) -> None:
        _required_text(self.remote_course_id, "remoteCourseId")
        _required_text(self.revision, "revision")

    def as_dict(self) -> dict:
        return {
            "remoteCourseId": self.remote_course_id,
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CourseWriteResult":
        return cls(data["remoteCourseId"], data["revision"])


@dataclass(frozen=True)
class RemoteCourseSnapshot:
    course_local_id: str
    remote_course_id: str
    slug: str
    status: str
    visibility: str
    revision: str
    definition_hash: str
    assets: Tuple[dict, ...]
    observed_at: str

    def __post_init__(self) -> None:
        _required_text(self.course_local_id, "courseLocalId")
        _required_text(self.remote_course_id, "remoteCourseId")
        _required_text(self.slug, "slug")
        if self.status not in {"preview", "published"}:
            raise ValueError("Remote course status is invalid")
        if self.visibility not in {"private", "unlisted", "public"}:
            raise ValueError("Remote course visibility is invalid")
        _required_text(self.revision, "revision")
        _required_hash(self.definition_hash, "definitionHash")
        _required_text(self.observed_at, "observedAt")
        pairs = set()
        hashes = set()
        keys = set()
        for asset in self.assets:
            if not isinstance(asset, dict) or set(asset) != {"sha256", "objectKey"}:
                raise ValueError("Remote course asset record is invalid")
            sha256 = _required_hash(asset["sha256"], "assets.sha256")
            object_key = _required_text(asset["objectKey"], "assets.objectKey")
            if sha256 in hashes or object_key in keys or (sha256, object_key) in pairs:
                raise ValueError("Remote course contains duplicate asset records")
            hashes.add(sha256)
            keys.add(object_key)
            pairs.add((sha256, object_key))

    def as_dict(self) -> dict:
        return {
            "courseLocalId": self.course_local_id,
            "remoteCourseId": self.remote_course_id,
            "slug": self.slug,
            "status": self.status,
            "visibility": self.visibility,
            "revision": self.revision,
            "definitionHash": self.definition_hash,
            "assets": list(self.assets),
            "observedAt": self.observed_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RemoteCourseSnapshot":
        return cls(
            course_local_id=data["courseLocalId"],
            remote_course_id=data["remoteCourseId"],
            slug=data["slug"],
            status=data["status"],
            visibility=data["visibility"],
            revision=data["revision"],
            definition_hash=data["definitionHash"],
            assets=tuple(data["assets"]),
            observed_at=data["observedAt"],
        )

    @classmethod
    def from_request(
        cls,
        request: CourseWriteRequest,
        *,
        remote_course_id: str,
        revision: str,
        observed_at: str,
    ) -> "RemoteCourseSnapshot":
        return cls(
            course_local_id=request.course_local_id,
            remote_course_id=remote_course_id,
            slug=request.slug,
            status=request.intended_status,
            visibility=request.visibility,
            revision=revision,
            definition_hash=request.definition_hash,
            assets=tuple(
                {
                    "sha256": asset["sha256"],
                    "objectKey": asset["objectKey"],
                }
                for asset in request.assets
            ),
            observed_at=observed_at,
        )

    def as_discovery(self) -> RemoteDiscoverySnapshot:
        return RemoteDiscoverySnapshot(
            schema_version="1.0",
            lookup_slug=self.slug,
            status="found",
            observed_at=self.observed_at,
            course_local_id=self.course_local_id,
            remote_course_id=self.remote_course_id,
            remote_status=self.status,
            remote_revision=self.revision,
            definition_hash=self.definition_hash,
            known_assets=self.assets,
        )


class ObjectStoreAdapter(Protocol):
    def ensure_asset(
        self,
        *,
        local_path: Path,
        object_key: str,
        sha256: str,
        idempotency_key: str,
    ) -> AssetUploadResult: ...


class CourseApiAdapter(Protocol):
    def discover(self, *, slug: str) -> RemoteDiscoverySnapshot: ...

    def create_course(self, *, request: CourseWriteRequest) -> CourseWriteResult: ...

    def update_course(
        self,
        *,
        remote_course_id: str,
        expected_revision: str,
        request: CourseWriteRequest,
    ) -> CourseWriteResult: ...

    def read_course(self, *, remote_course_id: str) -> RemoteCourseSnapshot: ...


@dataclass(frozen=True)
class PublicationOperation:
    schema_version: str
    operation_id: str
    preflight_hash: str
    adapter_mode: str
    mode: str
    phase: str
    write_attempted: bool
    verified_assets: Tuple[AssetUploadResult, ...] = ()
    write_result: Optional[CourseWriteResult] = None
    verified_remote: Optional[RemoteCourseSnapshot] = None

    def __post_init__(self) -> None:
        if self.schema_version != PUBLICATION_OPERATION_SCHEMA_VERSION:
            raise ValueError("Unsupported publication operation schemaVersion")
        if self.mode not in {"create", "update"}:
            raise ValueError("Publication operation mode is invalid")
        if self.adapter_mode not in {"test", "live"}:
            raise ValueError("Publication adapter mode is invalid")
        if self.phase not in ACTIVE_PHASES.union({"verified"}):
            raise ValueError("Publication operation phase is invalid")
        _required_hash(self.operation_id, "operationId")
        _required_hash(self.preflight_hash, "preflightHash")
        hashes = [asset.uploaded_sha256 for asset in self.verified_assets]
        keys = [asset.object_key for asset in self.verified_assets]
        if len(hashes) != len(set(hashes)) or len(keys) != len(set(keys)):
            raise ValueError("Publication operation contains duplicate verified assets")
        if not self.write_attempted and (
            self.write_result is not None or self.verified_remote is not None
        ):
            raise ValueError("Remote result requires a recorded write attempt")
        if self.phase in {"submitting", "ambiguous", "verifying", "remote-verified", "verified"} and not self.write_attempted:
            raise ValueError("Publication operation phase requires a write attempt")
        if self.verified_remote is not None and self.phase not in {
            "remote-verified",
            "verified",
        }:
            raise ValueError("Verified remote snapshot has an invalid operation phase")
        if self.phase in {"remote-verified", "verified"} and self.verified_remote is None:
            raise ValueError("Publication operation phase requires verified remote state")

    def as_dict(self) -> dict:
        return {
            "schemaVersion": self.schema_version,
            "operationId": self.operation_id,
            "preflightHash": self.preflight_hash,
            "adapterMode": self.adapter_mode,
            "mode": self.mode,
            "phase": self.phase,
            "writeAttempted": self.write_attempted,
            "verifiedAssets": [asset.as_dict() for asset in self.verified_assets],
            "writeResult": self.write_result.as_dict() if self.write_result else None,
            "verifiedRemote": (
                self.verified_remote.as_dict() if self.verified_remote else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PublicationOperation":
        return cls(
            schema_version=data["schemaVersion"],
            operation_id=data["operationId"],
            preflight_hash=data["preflightHash"],
            adapter_mode=data["adapterMode"],
            mode=data["mode"],
            phase=data["phase"],
            write_attempted=data["writeAttempted"],
            verified_assets=tuple(
                AssetUploadResult.from_dict(asset)
                for asset in data.get("verifiedAssets", [])
            ),
            write_result=(
                CourseWriteResult.from_dict(data["writeResult"])
                if data.get("writeResult") is not None
                else None
            ),
            verified_remote=(
                RemoteCourseSnapshot.from_dict(data["verifiedRemote"])
                if data.get("verifiedRemote") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class PublicationResult:
    operation_id: str
    remote_course_id: str
    revision: str
    status: str
    definition_hash: str


def load_publication_operation(root: Path) -> PublicationOperation:
    return PublicationOperation.from_dict(
        load_json(root.resolve() / PUBLICATION_OPERATION_RELATIVE_PATH)
    )


def _write_operation(root: Path, operation: PublicationOperation) -> None:
    write_json_atomic(root / PUBLICATION_OPERATION_RELATIVE_PATH, operation.as_dict())


def publisher_code_hash() -> str:
    root = Path(__file__).resolve().parent
    return canonical_json_hash(
        {
            path.name: hash_path(path)
            for path in (
                root / "publisher.py",
                root / "live_publication.py",
                root / "mind_imprint_api.py",
            )
        }
    )


def _operation_id(preflight_hash: str, adapter_mode: str) -> str:
    return canonical_json_hash(
        {
            "publisherVersion": PUBLISHER_VERSION,
            "publisherCodeHash": publisher_code_hash(),
            "preflightHash": preflight_hash,
            "adapterMode": adapter_mode,
        }
    )


def _result(operation: PublicationOperation) -> PublicationResult:
    remote = operation.verified_remote
    if remote is None:
        raise PublicationBlocked("Publication operation has no verified remote result")
    return PublicationResult(
        operation_id=operation.operation_id,
        remote_course_id=remote.remote_course_id,
        revision=remote.revision,
        status=remote.status,
        definition_hash=remote.definition_hash,
    )


def _safe_asset_source(root: Path, source: str, sha256: str) -> Path:
    relative = Path(source)
    if relative.is_absolute() or ".." in relative.parts:
        raise PublicationBlocked(f"Unsafe publication asset path: {source}")
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise PublicationBlocked(f"Publication asset is missing or unsafe: {source}")
    try:
        path.resolve().relative_to(root)
    except ValueError as exc:
        raise PublicationBlocked(f"Publication asset escapes course root: {source}") from exc
    if hash_path(path) != sha256:
        raise PublicationBlocked(f"Publication asset bytes changed: {source}")
    return path


def _request(root: Path, preflight: dict, operation_id: str) -> CourseWriteRequest:
    definition = load_json(root / "course/course.json")
    if canonical_json_hash(definition) != preflight["definition"]["sha256"]:
        raise PublicationBlocked("CourseDefinition changed after publication approval")
    assets = tuple(preflight["assets"]["upload"] + preflight["assets"]["reuse"])
    return CourseWriteRequest(
        course_local_id=preflight["courseLocalId"],
        slug=preflight["slug"],
        definition=definition,
        definition_hash=preflight["definition"]["sha256"],
        intended_status=preflight["intendedStatus"],
        visibility=preflight["visibility"],
        assets=assets,
        idempotency_key=operation_id,
    )


def _verify_remote(remote: RemoteCourseSnapshot, request: CourseWriteRequest) -> None:
    checks = (
        (remote.course_local_id == request.course_local_id, "course local identity"),
        (remote.slug == request.slug, "course slug"),
        (remote.definition_hash == request.definition_hash, "definition hash"),
        (remote.status == request.intended_status, "course status"),
        (remote.visibility == request.visibility, "course visibility"),
    )
    mismatch = next((label for valid, label in checks if not valid), None)
    if mismatch is not None:
        raise PublicationBlocked(f"Remote read-back has mismatched {mismatch}")
    remote_assets = {
        (asset.get("sha256"), asset.get("objectKey")) for asset in remote.assets
    }
    expected_assets = {
        (asset["sha256"], asset["objectKey"]) for asset in request.assets
    }
    if not expected_assets.issubset(remote_assets):
        raise PublicationBlocked("Remote read-back is missing published asset references")


def _recover_after_attempt(
    preflight: dict,
    request: CourseWriteRequest,
    operation: PublicationOperation,
    course_api: CourseApiAdapter,
) -> Optional[RemoteCourseSnapshot]:
    if operation.write_result is not None:
        remote = course_api.read_course(
            remote_course_id=operation.write_result.remote_course_id
        )
        _verify_remote(remote, request)
        return remote
    discovery = course_api.discover(slug=request.slug)
    if discovery.status in {"ambiguous", "unavailable"}:
        raise AmbiguousPublicationResult(
            f"Cannot recover publication while discovery is {discovery.status}"
        )
    if discovery.status == "not-found":
        if operation.mode == "update":
            raise PublicationBlocked("Known remote course disappeared during update")
        return None
    if (
        discovery.course_local_id != request.course_local_id
        or (
            operation.mode == "update"
            and discovery.remote_course_id != preflight["remote"]["courseId"]
        )
    ):
        raise PublicationBlocked("Recovered remote course identity does not match")
    remote = course_api.read_course(remote_course_id=discovery.remote_course_id)
    if remote.definition_hash == request.definition_hash:
        _verify_remote(remote, request)
        return remote
    if operation.mode == "create":
        raise PublicationBlocked(
            "A remote course appeared after create but does not match this operation"
        )
    if remote.revision != preflight["remote"]["expectedRevision"]:
        raise PublicationBlocked("Remote revision changed during update recovery")
    return None


def _update_asset_manifest(
    root: Path,
    operation: PublicationOperation,
    remote: RemoteCourseSnapshot,
) -> None:
    manifest = load_json(root / ASSET_MANIFEST_RELATIVE_PATH)
    uploaded = {
        asset.uploaded_sha256: asset for asset in operation.verified_assets
    }
    remote_pairs = {
        (asset["sha256"], asset["objectKey"]) for asset in remote.assets
    }
    for entry in manifest.get("entries", []):
        pair = (entry.get("sha256"), entry.get("objectKey"))
        if pair not in remote_pairs:
            raise PublicationBlocked(
                f"Verified remote is missing asset manifest entry: {entry.get('objectKey')}"
            )
        uploaded_result = uploaded.get(entry["sha256"])
        prior_remote = entry.get("remote") if isinstance(entry.get("remote"), dict) else {}
        entry["state"] = "reusable"
        entry["remote"] = {
            "objectKey": entry["objectKey"],
            "uploadedSha256": entry["sha256"],
            "etag": (
                uploaded_result.etag
                if uploaded_result is not None
                else prior_remote.get("etag")
            ),
            "verifiedAt": remote.observed_at,
        }
    write_asset_manifest(root, manifest)


def _finalize_verified_remote(
    root: Path,
    preflight: dict,
    operation: PublicationOperation,
) -> tuple[PublicationOperation, PublicationResult]:
    remote = operation.verified_remote
    if remote is None:
        raise PublicationBlocked("Cannot finalize without a verified remote snapshot")
    state = load_publish_state(root)
    if state.course_local_id != remote.course_local_id or state.slug != remote.slug:
        raise PublicationBlocked("Verified remote identity differs from publish state")
    if state.remote_course_id not in {None, remote.remote_course_id}:
        raise PublicationBlocked("Refusing to replace the stable remote course identity")
    _update_asset_manifest(root, operation, remote)
    write_publish_state(
        root,
        PublishState(
            schema_version="1.0",
            course_local_id=state.course_local_id,
            slug=state.slug,
            remote_course_id=remote.remote_course_id,
            remote_status=remote.status,
            last_known_remote_revision=remote.revision,
            last_uploaded_definition_hash=remote.definition_hash,
            last_published_definition_hash=(
                remote.definition_hash
                if preflight["intendedStatus"] == "published"
                else state.last_published_definition_hash
            ),
            last_publish_operation_id=operation.operation_id,
            verified_at=remote.observed_at,
        ),
    )
    completed = replace(operation, phase="verified")
    _write_operation(root, completed)
    return completed, _result(completed)


def publish_course(
    root: Path,
    *,
    object_store: ObjectStoreAdapter,
    course_api: CourseApiAdapter,
    now: str,
    adapter_mode: str = "test",
) -> PublicationResult:
    root = root.resolve()
    preflight_path = root / PUBLICATION_PREFLIGHT_RELATIVE_PATH
    if preflight_path.is_symlink() or not preflight_path.is_file():
        raise PublicationBlocked("Publication preflight is missing")
    preflight = load_json(preflight_path)
    preflight_hash = canonical_json_hash(preflight)
    if adapter_mode not in {"test", "live"}:
        raise ValueError("adapter_mode must be test or live")
    if adapter_mode == "live":
        from course_toolkit.workflow import load_session, reconcile_current_session

        session = load_session(root)
        reconcile_current_session(root, session, now)
        if "G9" not in session.completed_gate_ids:
            raise PublicationBlocked("Live publication requires completed G9 preflight")
        if session.artifact_hashes.get("@toolkit/course-publisher") != publisher_code_hash():
            raise PublicationBlocked("Live publication publisher code differs from G9 evidence")
    operation_id = _operation_id(preflight_hash, adapter_mode)
    operation_path = root / PUBLICATION_OPERATION_RELATIVE_PATH
    operation = None
    if operation_path.is_file() and not operation_path.is_symlink():
        existing = load_publication_operation(root)
        if existing.operation_id == operation_id:
            operation = existing
            if operation.phase == "verified":
                return _result(operation)
            if operation.phase == "remote-verified":
                return _finalize_verified_remote(root, preflight, operation)[1]
        elif existing.phase in ACTIVE_PHASES:
            raise PublicationBlocked(
                "A different publication operation is still active; resume it first"
            )

    status = publication_preflight_status(root)
    if not status["approved"]:
        reason = ", ".join(status.get("staleReasons", [])) or status["decisionStatus"]
        raise PublicationBlocked(f"Publication preflight is not approved and current: {reason}")
    if operation is None:
        operation = PublicationOperation(
            schema_version=PUBLICATION_OPERATION_SCHEMA_VERSION,
            operation_id=operation_id,
            preflight_hash=preflight_hash,
            adapter_mode=adapter_mode,
            mode=preflight["mode"],
            phase="planned",
            write_attempted=False,
        )
        _write_operation(root, operation)
    request = _request(root, preflight, operation_id)

    verified_hashes = {
        asset.uploaded_sha256 for asset in operation.verified_assets
    }
    if preflight["assets"]["upload"]:
        operation = replace(operation, phase="uploading")
        _write_operation(root, operation)
    for asset in preflight["assets"]["upload"]:
        if asset["sha256"] in verified_hashes:
            continue
        local_path = _safe_asset_source(
            root / "course",
            asset["sources"][0],
            asset["sha256"],
        )
        result = object_store.ensure_asset(
            local_path=local_path,
            object_key=asset["objectKey"],
            sha256=asset["sha256"],
            idempotency_key=canonical_json_hash(
                {"operationId": operation_id, "assetSha256": asset["sha256"]}
            ),
        )
        if (
            result.object_key != asset["objectKey"]
            or result.uploaded_sha256 != asset["sha256"]
            or not result.verified_at
        ):
            raise PublicationBlocked("Object store did not verify the requested asset")
        operation = replace(
            operation,
            verified_assets=operation.verified_assets + (result,),
        )
        _write_operation(root, operation)
        verified_hashes.add(result.uploaded_sha256)

    if operation.write_attempted:
        recovered = _recover_after_attempt(preflight, request, operation, course_api)
        if recovered is not None:
            _verify_remote(recovered, request)
            operation = replace(
                operation,
                phase="remote-verified",
                verified_remote=recovered,
            )
            _write_operation(root, operation)
            return _finalize_verified_remote(root, preflight, operation)[1]

    operation = replace(operation, phase="submitting", write_attempted=True)
    _write_operation(root, operation)
    try:
        if operation.mode == "create":
            write_result = course_api.create_course(request=request)
        else:
            remote_course_id = preflight["remote"]["courseId"]
            expected_revision = preflight["remote"]["expectedRevision"]
            if not remote_course_id or not expected_revision:
                raise PublicationBlocked("Update preflight lacks stable remote identity")
            write_result = course_api.update_course(
                remote_course_id=remote_course_id,
                expected_revision=expected_revision,
                request=request,
            )
    except AmbiguousPublicationResult:
        operation = replace(operation, phase="ambiguous")
        _write_operation(root, operation)
        recovered = _recover_after_attempt(preflight, request, operation, course_api)
        if recovered is None:
            raise AmbiguousPublicationResult(
                "Remote write remains unresolved after explicit discovery"
            )
        operation = replace(
            operation,
            phase="remote-verified",
            verified_remote=recovered,
        )
        _write_operation(root, operation)
        return _finalize_verified_remote(root, preflight, operation)[1]

    operation = replace(
        operation,
        phase="verifying",
        write_result=write_result,
    )
    _write_operation(root, operation)
    remote = course_api.read_course(remote_course_id=write_result.remote_course_id)
    _verify_remote(remote, request)
    if remote.revision != write_result.revision:
        raise PublicationBlocked("Remote read-back revision differs from write result")
    operation = replace(
        operation,
        phase="remote-verified",
        verified_remote=remote,
    )
    _write_operation(root, operation)
    return _finalize_verified_remote(root, preflight, operation)[1]
