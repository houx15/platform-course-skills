import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from course_toolkit.course_catalog import CourseCatalogError, load_confirmed_course_selection
from course_toolkit.course_compiler import canonical_json_hash
from course_toolkit.decisions import DecisionStore
from course_toolkit.issues import IssueStore
from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.mind_imprint_api import (
    AmbiguousRemoteWrite,
    MindImprintAuthoringApi,
    RemoteCourse,
)
from course_toolkit.package_review import verify_g8_review
from course_toolkit.workflow import (
    complete_gate,
    hash_path,
    invalidate_from_gate,
    load_session,
    save_session,
)


LIVE_SCHEMA_VERSION = "2.0"
STATE_PATH = Path(".course-work/publish-state.json")
MANIFEST_PATH = Path(".course-work/asset-manifest.json")
DISCOVERY_PATH = Path(".course-work/remote-discovery.json")
PREFLIGHT_PATH = Path(".course-work/publication-preflight.json")
REVIEW_EVIDENCE_PATH = Path(".course-work/publication-review-evidence.json")
OPERATION_PATH = Path(".course-work/publication-operation.json")
DECISION_ID = "decision-publication-preflight"


class LivePublicationBlocked(ValueError):
    pass


def live_publisher_hash() -> str:
    from course_toolkit.publisher import publisher_code_hash

    return publisher_code_hash()


def _slug(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value[0] not in "abcdefghijklmnopqrstuvwxyz"
        or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in value)
    ):
        raise LivePublicationBlocked("slug must be a stable lowercase URL-safe ID")
    return value


def _mime(source: str) -> str:
    explicit = {".json": "application/json", ".vtt": "text/vtt", ".html": "text/html"}
    return explicit.get(Path(source).suffix.lower()) or mimetypes.guess_type(source)[0] or "application/octet-stream"


def _empty_state(course_local_id: str, slug: str) -> dict:
    return {
        "schemaVersion": LIVE_SCHEMA_VERSION,
        "courseLocalId": course_local_id,
        "slug": slug,
        "remoteKnown": False,
        "remoteStatus": None,
        "remoteDefinitionHash": None,
        "uploadedAssets": {},
        "lastSavedDefinitionHash": None,
        "lastPublishedDefinitionHash": None,
        "lastOperationId": None,
        "verifiedAt": None,
    }


def init_live_publish_state(root: Path) -> dict:
    root = root.resolve()
    try:
        selection = load_confirmed_course_selection(root)
    except CourseCatalogError as exc:
        raise LivePublicationBlocked(str(exc)) from exc
    slug = _slug(selection["slug"])
    session = load_session(root)
    document = load_json(root / "course/course.json")
    course = document.get("course", {})
    if course.get("id") != slug or course.get("title") != selection["title"]:
        raise LivePublicationBlocked(
            "CourseDefinition identity must match the selected fixed catalog slug and title; "
            "update the Blueprint, then recompile, validate, preview, and review before publication"
        )
    path = root / STATE_PATH
    if path.is_file():
        state = load_json(path)
        if state.get("schemaVersion") != LIVE_SCHEMA_VERSION:
            raise LivePublicationBlocked("existing publish state uses an unsupported schema")
        if state.get("courseLocalId") != session.course_local_id or state.get("slug") != slug:
            raise LivePublicationBlocked("refusing to replace an existing course publication identity")
        return state
    state = _empty_state(session.course_local_id, slug)
    write_json_atomic(path, state)
    return state


def _load_state(root: Path) -> dict:
    path = root / STATE_PATH
    if path.is_symlink() or not path.is_file():
        raise LivePublicationBlocked("publish state is missing; initialize the stable slug first")
    state = load_json(path)
    if state.get("schemaVersion") != LIVE_SCHEMA_VERSION:
        raise LivePublicationBlocked("publish state schema is unsupported")
    return state


def build_live_asset_manifest(root: Path, state: dict) -> dict:
    root = root.resolve()
    verify_g8_review(root)
    validation = load_json(root / ".course-work/course-validation-report.json")
    definition = load_json(root / "course/course.json")
    slug = state["slug"]
    try:
        catalog_selection = load_confirmed_course_selection(root)
    except CourseCatalogError as exc:
        raise LivePublicationBlocked(str(exc)) from exc
    if catalog_selection["slug"] != slug:
        raise LivePublicationBlocked("publish state does not match the selected fixed catalog slug")
    prior = state.get("uploadedAssets", {})
    entries = []
    for asset in validation.get("assets", []):
        source = asset["source"]
        sha256 = asset["sha256"]
        size = asset["sizeBytes"]
        local = root / "course" / source
        if local.is_symlink() or not local.is_file() or hash_path(local) != sha256:
            raise LivePublicationBlocked(f"publication asset is missing or changed: {source}")
        object_key = f"courses/{slug}/{source}"
        previous = prior.get(source) if isinstance(prior, dict) else None
        reusable = (
            isinstance(previous, dict)
            and previous.get("slug") == slug
            and previous.get("relativePath") == source
            and previous.get("sha256") == sha256
            and previous.get("objectKey") == object_key
            and isinstance(previous.get("uploadedAt"), str)
        )
        entries.append(
            {
                "slug": slug,
                "relativePath": source,
                "sha256": sha256,
                "sizeBytes": size,
                "contentType": _mime(source),
                "objectKey": object_key,
                "state": "reuse-local-proof" if reusable else "upload-required",
            }
        )
    if catalog_selection["cover"]["relativePath"] in {entry["relativePath"] for entry in entries}:
        raise LivePublicationBlocked("course content must not define the reserved catalog cover path")
    manifest = {
        "schemaVersion": LIVE_SCHEMA_VERSION,
        "slug": slug,
        "courseLocalId": state["courseLocalId"],
        "definitionHash": canonical_json_hash(definition),
        "validationReportHash": hash_path(root / ".course-work/course-validation-report.json"),
        "entries": entries,
    }
    write_json_atomic(root / MANIFEST_PATH, manifest)
    return manifest


def _remote_record(remote: Optional[RemoteCourse], observed_at: str) -> dict:
    if remote is None:
        return {"status": "not-found", "observedAt": observed_at}
    return {
        "status": "found",
        "slug": remote.slug,
        "courseStatus": remote.status,
        "definitionHash": remote.definition_hash,
        "observedAt": observed_at,
    }


def prepare_live_preflight(
    root: Path,
    api: MindImprintAuthoringApi,
    *,
    action: str,
    now: str,
) -> dict:
    root = root.resolve()
    if action not in {"save-preview", "publish"}:
        raise LivePublicationBlocked("action must be save-preview or publish")
    verify_g8_review(root)
    try:
        catalog_selection = load_confirmed_course_selection(root)
    except CourseCatalogError as exc:
        raise LivePublicationBlocked(str(exc)) from exc
    if action == "publish" and not getattr(api, "supports_course_asset_cover", False):
        raise LivePublicationBlocked(
            "the configured student authoring API cannot bind the fixed catalog WebP cover"
        )
    state = _load_state(root)
    if state["slug"] != catalog_selection["slug"]:
        raise LivePublicationBlocked("publish state does not match the selected fixed catalog slug")
    manifest = build_live_asset_manifest(root, state)
    remote = api.get_course(state["slug"])
    if state["remoteKnown"] and remote is None:
        raise LivePublicationBlocked("the previously verified remote course is missing")
    if remote is not None and state.get("remoteDefinitionHash") not in {None, remote.definition_hash}:
        raise LivePublicationBlocked("remote course changed since the last verified operation")
    if remote is not None and remote.status == "published" and action != "publish":
        raise LivePublicationBlocked("editing a published course must use publish so save and re-ship stay together")
    discovery = _remote_record(remote, now)
    write_json_atomic(root / DISCOVERY_PATH, {"schemaVersion": LIVE_SCHEMA_VERSION, **discovery})
    definition = load_json(root / "course/course.json")
    course = definition.get("course", {})
    if course.get("id") != catalog_selection["slug"] or course.get("title") != catalog_selection["title"]:
        raise LivePublicationBlocked("CourseDefinition identity differs from the selected fixed catalog course")
    uploads = [entry for entry in manifest["entries"] if entry["state"] == "upload-required"]
    reuse = [entry for entry in manifest["entries"] if entry["state"] == "reuse-local-proof"]
    review_evidence = load_json(root / REVIEW_EVIDENCE_PATH)
    preflight = {
        "schemaVersion": LIVE_SCHEMA_VERSION,
        "courseLocalId": state["courseLocalId"],
        "slug": state["slug"],
        "mode": "create" if remote is None else "update",
        "action": action,
        "apiBase": api.api_base,
        "definition": {"path": "course/course.json", "sha256": canonical_json_hash(definition)},
        "catalog": {
            "catalogId": catalog_selection["catalogId"],
            "title": catalog_selection["title"],
            "catalogHash": catalog_selection["catalogHash"],
        },
        "catalogCover": {
            key: catalog_selection["cover"][key]
            for key in ("relativePath", "objectKey", "sha256", "sizeBytes", "contentType")
        },
        "options": {
            "blurb": catalog_selection["blurb"],
            "cardIds": catalog_selection["cardIds"],
            "category": catalog_selection["category"],
            "introduction": catalog_selection["introduction"],
            "cover": "",
            "coverAssetPath": catalog_selection["cover"]["relativePath"] if action == "publish" else None,
        },
        "remote": discovery,
        "assets": {"upload": uploads, "reuse": reuse},
        "evidence": {
            "validationReportHash": manifest["validationReportHash"],
            "previewManifestHash": hash_path(root / ".course-work/preview-manifest.json"),
            "reviewReportHash": hash_path(root / ".course-work/review-report.json"),
            "reviewEvidenceHash": canonical_json_hash(review_evidence),
            "assetManifestHash": hash_path(root / MANIFEST_PATH),
            "catalogSelectionHash": hash_path(root / ".course-work/course-catalog-selection.json"),
        },
        "risks": {
            "productionOnly": True,
            "lastWriterWins": True,
            "publishedSaveMutatesLiveBytes": remote is not None and remote.status == "published",
            "shipRegeneratesTTS": action == "publish",
            "assetReuseUsesLocalProofOnly": bool(reuse),
            "fixedCatalogCover": True,
            "catalogCoverRequiresCourseAssetPathSupport": action == "publish",
        },
        "preparedAt": now,
    }
    write_json_atomic(root / PREFLIGHT_PATH, preflight)
    context_hash = canonical_json_hash(preflight)
    decisions = DecisionStore.load(root / ".course-work/decisions.json")
    try:
        prior = decisions.get(DECISION_ID)
    except ValueError:
        prior = None
    if prior is not None and prior.context_hash != context_hash:
        decisions.reconcile_context(DECISION_ID, context_hash, now)
    decision = decisions.request(
        DECISION_ID,
        "Approve this exact production course write?",
        context_hash,
        context={
            "slug": state["slug"],
            "mode": preflight["mode"],
            "action": action,
            "uploadCount": len(uploads),
            "reuseCount": len(reuse),
            "publishedLiveMutation": preflight["risks"]["publishedSaveMutatesLiveBytes"],
            "catalogId": catalog_selection["catalogId"],
        },
        options=("approve", "revise"),
        affected_artifact_ids=(PREFLIGHT_PATH.as_posix(),),
        requested_at=now,
    )
    decisions.save()
    session = load_session(root)
    session.pending_decision_ids = sorted(
        set(session.pending_decision_ids).union({DECISION_ID})
        if decision.status == "pending"
        else set(session.pending_decision_ids).difference({DECISION_ID})
    )
    save_session(root, session)
    return preflight


def live_preflight_status(root: Path) -> dict:
    root = root.resolve()
    path = root / PREFLIGHT_PATH
    if path.is_symlink() or not path.is_file():
        raise LivePublicationBlocked("publication preflight is missing")
    preflight = load_json(path)
    stale = []
    if preflight.get("schemaVersion") != LIVE_SCHEMA_VERSION:
        stale.append("unsupported-preflight-schema")
    try:
        definition = load_json(root / "course/course.json")
        checks = {
            "definition": canonical_json_hash(definition),
            "validationReportHash": hash_path(root / ".course-work/course-validation-report.json"),
            "previewManifestHash": hash_path(root / ".course-work/preview-manifest.json"),
            "reviewReportHash": hash_path(root / ".course-work/review-report.json"),
            "reviewEvidenceHash": canonical_json_hash(load_json(root / REVIEW_EVIDENCE_PATH)),
            "assetManifestHash": hash_path(root / MANIFEST_PATH),
            "catalogSelectionHash": hash_path(root / ".course-work/course-catalog-selection.json"),
        }
        if preflight["definition"]["sha256"] != checks.pop("definition"):
            stale.append("course-definition-changed")
        for key, value in checks.items():
            if preflight["evidence"].get(key) != value:
                stale.append(f"{key}-changed")
    except (KeyError, TypeError, ValueError):
        stale.append("preflight-evidence-unreadable")
    decisions = DecisionStore.load(root / ".course-work/decisions.json")
    try:
        decision = decisions.get(DECISION_ID)
    except ValueError:
        decision = None
    preflight_hash = canonical_json_hash(preflight)
    answer = decision.answer if decision and isinstance(decision.answer, dict) else {}
    approved = bool(
        decision
        and decision.status == "confirmed"
        and decision.context_hash == preflight_hash
        and answer.get("choice") == "approve"
        and isinstance(answer.get("rationale"), str)
        and answer["rationale"].strip()
        and not stale
    )
    return {
        "preflightHash": preflight_hash,
        "current": not stale,
        "staleReasons": sorted(set(stale)),
        "decisionStatus": decision.status if decision else "missing",
        "approved": approved,
    }


def verify_live_preflight(root: Path) -> dict:
    status = live_preflight_status(root)
    if not status["approved"]:
        reason = ", ".join(status["staleReasons"]) or status["decisionStatus"]
        raise LivePublicationBlocked(f"publication preflight is not approved and current: {reason}")
    root = root.resolve()
    evidence = {
        ".course-work/publication-preflight.json": hash_path(root / PREFLIGHT_PATH),
        ".course-work/asset-manifest.json": hash_path(root / MANIFEST_PATH),
        ".course-work/publish-state.json": hash_path(root / STATE_PATH),
        ".course-work/publication-review-evidence.json": hash_path(root / REVIEW_EVIDENCE_PATH),
        ".course-work/remote-discovery.json": hash_path(root / DISCOVERY_PATH),
        ".course-work/course-catalog-selection.json": hash_path(
            root / ".course-work/course-catalog-selection.json"
        ),
        "@toolkit/course-publisher": live_publisher_hash(),
    }
    return evidence


def _remote_matches(remote: Optional[RemoteCourse], preflight_remote: dict) -> bool:
    if preflight_remote["status"] == "not-found":
        return remote is None
    return bool(
        remote
        and remote.slug == preflight_remote["slug"]
        and remote.status == preflight_remote["courseStatus"]
        and remote.definition_hash == preflight_remote["definitionHash"]
    )


def _verify_definition(remote: Optional[RemoteCourse], definition: dict, slug: str) -> RemoteCourse:
    if remote is None or remote.slug != slug or remote.definition != definition:
        raise LivePublicationBlocked("remote definition readback does not match the approved course")
    return remote


def _complete_trusted_gate(root: Path, gate_id: str, evidence: dict, now: str) -> None:
    session = load_session(root)
    issues = IssueStore.load(root / ".course-work/issues.json")
    decisions = DecisionStore.load(root / ".course-work/decisions.json")
    active = [issue for issue in issues.all() if issue.status == "active"]
    pending = [decision.id for decision in decisions.all() if decision.status in {"pending", "invalidated"}]
    if gate_id in session.completed_gate_ids:
        invalidate_from_gate(session, gate_id, now)
    complete_gate(
        session,
        gate_id,
        now,
        active_issues=active,
        pending_decision_ids=pending,
        gate_evidence=evidence,
    )
    save_session(root, session)


def execute_live_publication(
    root: Path,
    api: MindImprintAuthoringApi,
    *,
    now: str,
) -> dict:
    root = root.resolve()
    preflight = load_json(root / PREFLIGHT_PATH)
    evidence = verify_live_preflight(root)
    _complete_trusted_gate(root, "G9", evidence, now)
    if api.api_base != preflight["apiBase"]:
        raise LivePublicationBlocked("API base differs from the approved preflight")
    state = _load_state(root)
    slug = preflight["slug"]
    remote_before = api.get_course(slug)
    if not _remote_matches(remote_before, preflight["remote"]):
        raise LivePublicationBlocked("remote course changed after publication approval")
    uploaded = dict(state.get("uploadedAssets", {}))
    newly_uploaded_paths = []
    resumed_reused_paths = []
    for asset in preflight["assets"]["upload"]:
        prior_upload = uploaded.get(asset["relativePath"])
        if (
            isinstance(prior_upload, dict)
            and prior_upload.get("slug") == slug
            and prior_upload.get("relativePath") == asset["relativePath"]
            and prior_upload.get("sha256") == asset["sha256"]
            and prior_upload.get("objectKey") == asset["objectKey"]
            and isinstance(prior_upload.get("uploadedAt"), str)
            and prior_upload["uploadedAt"]
        ):
            resumed_reused_paths.append(asset["relativePath"])
            continue
        local_path = root / asset.get("localPath", f"course/{asset['relativePath']}")
        if local_path.is_symlink() or not local_path.is_file() or hash_path(local_path) != asset["sha256"]:
            raise LivePublicationBlocked(f"approved asset changed: {asset['relativePath']}")
        plan = api.plan_asset_upload(
            slug,
            asset["relativePath"],
            asset["contentType"],
            asset["sizeBytes"],
        )
        if (
            not isinstance(plan.get("putUrl"), str)
            or plan.get("objectKey") != asset["objectKey"]
            or plan.get("requiredContentType") != asset["contentType"]
        ):
            raise LivePublicationBlocked("asset upload plan differs from the approved path or content type")
        max_bytes = plan.get("maxBytes")
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or asset["sizeBytes"] > max_bytes:
            raise LivePublicationBlocked(
                f"asset exceeds the server upload limit: {asset['relativePath']}"
            )
        etag = api.upload_asset(plan["putUrl"], local_path, plan["requiredContentType"])
        uploaded[asset["relativePath"]] = {
            **{key: asset[key] for key in ("slug", "relativePath", "sha256", "sizeBytes", "contentType", "objectKey")},
            "etag": etag,
            "uploadedAt": now,
        }
        state["uploadedAssets"] = uploaded
        write_json_atomic(root / STATE_PATH, state)
        newly_uploaded_paths.append(asset["relativePath"])
    definition = load_json(root / preflight["definition"]["path"])
    try:
        api.save_definition(
            slug,
            definition,
            blurb=preflight["options"]["blurb"],
            card_ids=preflight["options"]["cardIds"],
            category=preflight["options"]["category"],
            introduction=preflight["options"]["introduction"],
        )
    except AmbiguousRemoteWrite:
        _verify_definition(api.get_course(slug), definition, slug)
    saved = _verify_definition(api.get_course(slug), definition, slug)
    if preflight["action"] == "publish":
        try:
            api.ship(
                slug,
                cover=preflight["options"]["cover"],
                cover_asset_path=preflight["options"]["coverAssetPath"],
            )
        except AmbiguousRemoteWrite:
            recovered = _verify_definition(api.get_course(slug), definition, slug)
            if recovered.status != "published":
                raise
        saved = _verify_definition(api.get_course(slug), definition, slug)
        if saved.status != "published":
            raise LivePublicationBlocked("remote course did not reach published status")
    elif saved.status != "preview":
        raise LivePublicationBlocked("save-preview did not leave the remote course in preview")
    cover_verification = None
    if preflight["action"] == "publish":
        catalog_cover = preflight["catalogCover"]
        cover_verification = api.verify_published_cover(
            slug,
            catalog_cover["sha256"],
        )
    operation_id = canonical_json_hash(
        {
            "preflightHash": canonical_json_hash(preflight),
            "remoteHash": saved.definition_hash,
            "status": saved.status,
            "coverVerification": cover_verification,
        }
    )
    state.update(
        remoteKnown=True,
        remoteStatus=saved.status,
        remoteDefinitionHash=saved.definition_hash,
        lastSavedDefinitionHash=preflight["definition"]["sha256"],
        lastPublishedDefinitionHash=(
            preflight["definition"]["sha256"]
            if saved.status == "published"
            else state.get("lastPublishedDefinitionHash")
        ),
        lastOperationId=operation_id,
        verifiedAt=now,
    )
    write_json_atomic(root / STATE_PATH, state)
    operation = {
        "schemaVersion": LIVE_SCHEMA_VERSION,
        "operationId": operation_id,
        "adapterMode": "live",
        "preflightHash": canonical_json_hash(preflight),
        "slug": slug,
        "status": saved.status,
        "remoteDefinitionHash": saved.definition_hash,
        "localDefinitionHash": preflight["definition"]["sha256"],
        "uploadedPaths": sorted(newly_uploaded_paths),
        "reusedPaths": sorted(
            {
                *(asset["relativePath"] for asset in preflight["assets"]["reuse"]),
                *resumed_reused_paths,
            }
        ),
        "coverVerification": cover_verification,
        "verifiedAt": now,
    }
    write_json_atomic(root / OPERATION_PATH, operation)
    g10_evidence = {
        ".course-work/publication-operation.json": hash_path(root / OPERATION_PATH),
        ".course-work/asset-manifest.json": hash_path(root / MANIFEST_PATH),
        ".course-work/publish-state.json": hash_path(root / STATE_PATH),
        "@toolkit/course-publisher": live_publisher_hash(),
    }
    _complete_trusted_gate(root, "G10", g10_evidence, now)
    return operation
