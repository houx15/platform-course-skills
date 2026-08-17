import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from course_toolkit.issues import (
    CourseProductionIssue,
    IssueStore,
    make_registered_issue,
)
from course_toolkit.course_compiler import (
    COMPILER_VERSION,
    CONTRACT_SNAPSHOT,
    canonical_json_hash,
    validate_with_shared_contract,
)
from course_toolkit.jsonio import load_json, write_json_atomic


WORKFLOW_VERSION = "1.0"
SESSION_RELATIVE_PATH = Path(".course-work/session.json")

PHASES = (
    "intake",
    "material-review",
    "course-brief",
    "course-design",
    "media-design",
    "compile",
    "validate",
    "preview",
    "revise",
    "final-review",
    "publish",
    "complete",
)

SESSION_STATUSES = (
    "in-progress",
    "waiting-for-teacher",
    "blocked",
    "ready-to-publish",
    "publishing",
    "complete",
    "failed",
)


@dataclass(frozen=True)
class Gate:
    id: str
    phase: str
    prerequisite_id: Optional[str]
    next_phase: str


GATES = (
    Gate("G0", "intake", None, "material-review"),
    Gate("G1", "material-review", "G0", "course-brief"),
    Gate("G2", "course-brief", "G1", "course-design"),
    Gate("G3", "course-design", "G2", "media-design"),
    Gate("G4", "media-design", "G3", "compile"),
    Gate("G5", "compile", "G4", "validate"),
    Gate("G6", "validate", "G5", "preview"),
    Gate("G7", "preview", "G6", "final-review"),
    Gate("G8", "final-review", "G7", "publish"),
    Gate("G9", "publish", "G8", "complete"),
    Gate("G10", "complete", "G9", "complete"),
)

GATE_BY_ID = {gate.id: gate for gate in GATES}
GATE_INDEX = {gate.id: index for index, gate in enumerate(GATES)}


@dataclass(frozen=True)
class ArtifactRule:
    path: str
    gate_id: str


ARTIFACT_GATE_RULES = (
    ArtifactRule("materials/", "G1"),
    ArtifactRule(".course-work/course-brief.json", "G2"),
    ArtifactRule(".course-work/course-blueprint.json", "G3"),
    ArtifactRule(".course-work/media/", "G4"),
    ArtifactRule("course/course.json", "G5"),
    ArtifactRule(".course-work/course-runtime-source-map.json", "G5"),
    ArtifactRule(".course-work/compilation-report.json", "G5"),
    ArtifactRule("course/assets/", "G6"),
    ArtifactRule(".course-work/course-validation-report.json", "G6"),
    ArtifactRule(".course-work/preview-manifest.json", "G7"),
    ArtifactRule(".course-work/annotations.json", "G7"),
    ArtifactRule(".course-work/review-report.json", "G8"),
    ArtifactRule(".course-work/asset-manifest.json", "G9"),
    ArtifactRule(".course-work/publish-state.json", "G9"),
    ArtifactRule(".course-work/publication-review-evidence.json", "G9"),
    ArtifactRule(".course-work/remote-discovery.json", "G9"),
    ArtifactRule(".course-work/publication-preflight.json", "G9"),
    ArtifactRule(".course-work/publication-operation.json", "G10"),
)

G5_EVIDENCE_KEYS = (
    ".course-work/course-blueprint.json",
    "course/course.json",
    ".course-work/course-runtime-source-map.json",
    ".course-work/compilation-report.json",
    "@toolkit/course-compiler",
    "@toolkit/course-contract-snapshot",
)

G6_EVIDENCE_KEYS = (
    ".course-work/course-validation-report.json",
    "@toolkit/course-package-validator",
    "@course/asset-set",
)
G6_ASSET_EVIDENCE_PREFIX = "@course/asset:"

G7_EVIDENCE_KEYS = (
    ".course-work/preview-manifest.json",
    "@toolkit/course-preview-bundle",
)

G9_EVIDENCE_KEYS = (
    ".course-work/publication-preflight.json",
    ".course-work/asset-manifest.json",
    ".course-work/publish-state.json",
    ".course-work/publication-review-evidence.json",
    ".course-work/remote-discovery.json",
    "@toolkit/course-publisher",
)

G10_EVIDENCE_KEYS = (
    ".course-work/publication-operation.json",
    ".course-work/asset-manifest.json",
    ".course-work/publish-state.json",
    "@toolkit/course-publisher",
)

TOOLKIT_G5_ARTIFACTS = {
    "@toolkit/course-compiler": Path(__file__).resolve().parent / "course_compiler.py",
    "@toolkit/course-contract-snapshot": CONTRACT_SNAPSHOT,
}

TOOLKIT_G9_ARTIFACTS = {
    "@toolkit/course-publisher": Path(__file__).resolve().parent / "publisher.py",
}


@dataclass(frozen=True)
class ArtifactReconciliationResult:
    changed_paths: Tuple[str, ...]
    missing_source_paths: Tuple[str, ...]
    earliest_invalidated_gate_id: Optional[str]
    active_issues: Tuple[CourseProductionIssue, ...]


class WorkflowError(ValueError):
    pass


@dataclass
class CourseProductionSession:
    workflow_version: str
    course_local_id: str
    source_paths: List[str]
    phase: str
    status: str
    completed_gate_ids: List[str] = field(default_factory=list)
    invalidated_gate_ids: List[str] = field(default_factory=list)
    active_issue_ids: List[str] = field(default_factory=list)
    pending_decision_ids: List[str] = field(default_factory=list)
    pending_annotation_ids: List[str] = field(default_factory=list)
    artifact_hashes: Dict[str, str] = field(default_factory=dict)
    last_successful_action: Optional[dict] = None
    failure: Optional[dict] = None
    created_at: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict:
        data = asdict(self)
        return {
            "workflowVersion": data["workflow_version"],
            "courseLocalId": data["course_local_id"],
            "sourcePaths": data["source_paths"],
            "phase": data["phase"],
            "status": data["status"],
            "completedGateIds": data["completed_gate_ids"],
            "invalidatedGateIds": data["invalidated_gate_ids"],
            "activeIssueIds": data["active_issue_ids"],
            "pendingDecisionIds": data["pending_decision_ids"],
            "pendingAnnotationIds": data["pending_annotation_ids"],
            "artifactHashes": data["artifact_hashes"],
            "lastSuccessfulAction": data["last_successful_action"],
            "failure": data["failure"],
            "createdAt": data["created_at"],
            "updatedAt": data["updated_at"],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CourseProductionSession":
        if data.get("workflowVersion") != WORKFLOW_VERSION:
            raise ValueError(
                f"Unsupported workflowVersion: {data.get('workflowVersion')}"
            )
        phase = data["phase"]
        status = data["status"]
        if phase not in PHASES:
            raise ValueError(f"Unknown workflow phase: {phase}")
        if status not in SESSION_STATUSES:
            raise ValueError(f"Unknown workflow status: {status}")
        completed = list(data.get("completedGateIds", []))
        invalidated = list(data.get("invalidatedGateIds", []))
        _validate_gate_ids(completed + invalidated)
        expected_completed = [gate.id for gate in GATES[: len(completed)]]
        if completed != expected_completed:
            raise ValueError("Completed workflow gates must be contiguous and ordered")
        if set(completed).intersection(invalidated):
            raise ValueError("Completed and invalidated workflow gates cannot overlap")
        return cls(
            workflow_version=WORKFLOW_VERSION,
            course_local_id=data["courseLocalId"],
            source_paths=list(data.get("sourcePaths", [])),
            phase=phase,
            status=status,
            completed_gate_ids=completed,
            invalidated_gate_ids=invalidated,
            active_issue_ids=list(data.get("activeIssueIds", [])),
            pending_decision_ids=list(data.get("pendingDecisionIds", [])),
            pending_annotation_ids=list(data.get("pendingAnnotationIds", [])),
            artifact_hashes=dict(data.get("artifactHashes", {})),
            last_successful_action=data.get("lastSuccessfulAction"),
            failure=data.get("failure"),
            created_at=data["createdAt"],
            updated_at=data["updatedAt"],
        )


def _validate_gate_ids(gate_ids: Iterable[str]) -> None:
    unknown = [gate_id for gate_id in gate_ids if gate_id not in GATE_BY_ID]
    if unknown:
        raise ValueError(f"Unknown workflow gate: {unknown[0]}")


def _gate(gate_id: str) -> Gate:
    try:
        return GATE_BY_ID[gate_id]
    except KeyError as exc:
        raise WorkflowError(f"Unknown workflow gate: {gate_id}") from exc


def new_session(
    course_local_id: str,
    source_paths: Sequence[str],
    now: str,
) -> CourseProductionSession:
    if not course_local_id.strip():
        raise WorkflowError("course_local_id is required")
    return CourseProductionSession(
        workflow_version=WORKFLOW_VERSION,
        course_local_id=course_local_id,
        source_paths=list(dict.fromkeys(source_paths)),
        phase="intake",
        status="in-progress",
        created_at=now,
        updated_at=now,
    )


def load_session(root: Path) -> CourseProductionSession:
    return CourseProductionSession.from_dict(load_json(root / SESSION_RELATIVE_PATH))


def save_session(root: Path, session: CourseProductionSession) -> None:
    write_json_atomic(root / SESSION_RELATIVE_PATH, session.as_dict())


def complete_gate(
    session: CourseProductionSession,
    gate_id: str,
    now: str,
    *,
    active_issues: Sequence[CourseProductionIssue] = (),
    pending_decision_ids: Sequence[str] = (),
    gate_evidence: Optional[Dict[str, str]] = None,
) -> CourseProductionSession:
    gate = _gate(gate_id)
    if gate_id in session.completed_gate_ids and gate_id not in session.invalidated_gate_ids:
        return session
    if gate.prerequisite_id not in (None, *session.completed_gate_ids):
        raise WorkflowError(f"{gate_id} requires {gate.prerequisite_id}")
    blockers = [
        issue
        for issue in active_issues
        if issue.status == "active"
        and issue.severity == "blocker"
        and GATE_INDEX[issue.gate_id] <= GATE_INDEX[gate_id]
    ]
    if blockers:
        raise WorkflowError(
            f"{gate_id} has an active blocker: {blockers[0].code}"
        )
    effective_pending = list(
        dict.fromkeys([*session.pending_decision_ids, *pending_decision_ids])
    )
    if effective_pending:
        raise WorkflowError(
            f"{gate_id} has a pending teacher decision: {effective_pending[0]}"
        )
    if gate_id == "G5":
        evidence = gate_evidence or {}
        missing = [key for key in G5_EVIDENCE_KEYS if key not in evidence]
        if missing:
            raise WorkflowError(
                f"G5 requires current compilation evidence: {missing[0]}"
            )
        session.artifact_hashes.update(evidence)
    if gate_id == "G6":
        evidence = gate_evidence or {}
        missing = [key for key in G6_EVIDENCE_KEYS if key not in evidence]
        if missing:
            raise WorkflowError(
                f"G6 requires current package validation evidence: {missing[0]}"
            )
        session.artifact_hashes.update(evidence)
    if gate_id == "G7":
        evidence = gate_evidence or {}
        missing = [key for key in G7_EVIDENCE_KEYS if key not in evidence]
        if missing:
            raise WorkflowError(
                f"G7 requires current renderer preview evidence: {missing[0]}"
            )
        session.artifact_hashes.update(evidence)
    if gate_id == "G9":
        evidence = gate_evidence or {}
        missing = [key for key in G9_EVIDENCE_KEYS if key not in evidence]
        if missing:
            raise WorkflowError(
                f"G9 requires current publication preflight evidence: {missing[0]}"
            )
        session.artifact_hashes.update(evidence)
    if gate_id == "G10":
        evidence = gate_evidence or {}
        missing = [key for key in G10_EVIDENCE_KEYS if key not in evidence]
        if missing:
            raise WorkflowError(
                f"G10 requires current remote verification evidence: {missing[0]}"
            )
        session.artifact_hashes.update(evidence)
    if gate_id not in session.completed_gate_ids:
        session.completed_gate_ids.append(gate_id)
        session.completed_gate_ids.sort(key=GATE_INDEX.__getitem__)
    if gate_id in session.invalidated_gate_ids:
        session.invalidated_gate_ids.remove(gate_id)
    session.phase = gate.next_phase
    session.status = "complete" if gate_id == "G10" else "in-progress"
    session.failure = None
    session.last_successful_action = {
        "action": "complete-gate",
        "gateId": gate_id,
        "at": now,
    }
    session.updated_at = now
    return session


def invalidate_from_gate(
    session: CourseProductionSession,
    gate_id: str,
    now: str,
) -> CourseProductionSession:
    gate = _gate(gate_id)
    affected = [
        completed
        for completed in session.completed_gate_ids
        if GATE_INDEX[completed] >= GATE_INDEX[gate_id]
    ]
    session.completed_gate_ids = [
        completed for completed in session.completed_gate_ids if completed not in affected
    ]
    session.invalidated_gate_ids = sorted(
        set(session.invalidated_gate_ids).union(affected),
        key=GATE_INDEX.__getitem__,
    )
    session.phase = gate.phase
    session.status = "in-progress"
    session.failure = None
    session.updated_at = now
    return session


def set_phase_status(
    session: CourseProductionSession,
    status: str,
    now: str,
    *,
    failure: Optional[dict] = None,
) -> CourseProductionSession:
    if status not in SESSION_STATUSES:
        raise WorkflowError(f"Unknown workflow status: {status}")
    if status == "complete":
        raise WorkflowError("complete status may only be set by G10")
    if status == "ready-to-publish" and "G8" not in session.completed_gate_ids:
        raise WorkflowError("ready-to-publish status requires G8")
    if status == "publishing" and "G9" not in session.completed_gate_ids:
        raise WorkflowError("publishing status requires G9")
    if session.status == "complete":
        raise WorkflowError("A complete session is terminal until artifact reconciliation")
    if status == "failed" and failure is None:
        raise WorkflowError("failed status requires a failure record")
    if status != "failed" and failure is not None:
        raise WorkflowError("failure record is only valid for failed status")
    session.status = status
    session.failure = failure
    session.updated_at = now
    return session


def workflow_summary(session: CourseProductionSession) -> dict:
    next_gate = next(
        (gate.id for gate in GATES if gate.id not in session.completed_gate_ids),
        None,
    )
    if session.status == "complete":
        next_action = "none"
    elif session.status == "waiting-for-teacher":
        next_action = "wait for teacher decision"
    elif session.pending_annotation_ids:
        next_action = "resolve preview annotations"
    elif next_gate is None:
        next_action = "verify remote course"
    else:
        next_action = f"complete {next_gate}"
    return {
        "courseLocalId": session.course_local_id,
        "phase": session.phase,
        "status": session.status,
        "completedGates": list(session.completed_gate_ids),
        "invalidatedGates": list(session.invalidated_gate_ids),
        "issues": list(session.active_issue_ids),
        "pendingDecisions": list(session.pending_decision_ids),
        "pendingAnnotations": list(session.pending_annotation_ids),
        "nextAction": next_action,
    }


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_path(path: Path) -> str:
    if path.is_symlink():
        raise ValueError(f"Cannot hash symlink: {path}")
    if not path.exists():
        raise ValueError(f"Cannot hash missing path: {path}")
    if path.is_file():
        return _hash_file(path)
    if not path.is_dir():
        raise ValueError(f"Cannot hash unsupported path: {path}")

    entries = []
    for candidate in path.rglob("*"):
        if candidate.is_symlink():
            raise ValueError(f"Cannot hash tree containing symlink: {candidate}")
        if not candidate.is_file() or candidate.suffix.lower() == ".zip":
            continue
        relative = candidate.relative_to(path).as_posix()
        entries.append((relative, _hash_file(candidate)))
    digest = hashlib.sha256()
    for relative, file_hash in sorted(entries):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def verify_g5_compilation(root: Path) -> Dict[str, str]:
    root = root.resolve()
    relative_paths = {
        ".course-work/course-blueprint.json": root
        / ".course-work"
        / "course-blueprint.json",
        "course/course.json": root / "course" / "course.json",
        ".course-work/course-runtime-source-map.json": root
        / ".course-work"
        / "course-runtime-source-map.json",
        ".course-work/compilation-report.json": root
        / ".course-work"
        / "compilation-report.json",
    }
    for label, path in relative_paths.items():
        if path.is_symlink() or not path.is_file():
            raise WorkflowError(f"G5 compilation evidence is missing: {label}")

    blueprint = load_json(relative_paths[".course-work/course-blueprint.json"])
    document = load_json(relative_paths["course/course.json"])
    source_map = load_json(
        relative_paths[".course-work/course-runtime-source-map.json"]
    )
    report = load_json(relative_paths[".course-work/compilation-report.json"])
    snapshot = load_json(CONTRACT_SNAPSHOT)

    if report.get("status") != "compiled" or report.get("issues") != []:
        raise WorkflowError("G5 compilation report is not successful")
    if report.get("compilerVersion") != COMPILER_VERSION:
        raise WorkflowError("G5 compilation report uses a stale compiler version")
    if source_map.get("compilerVersion") != COMPILER_VERSION:
        raise WorkflowError("G5 source map uses a stale compiler version")

    expected_blueprint_hash = canonical_json_hash(blueprint)
    if report.get("blueprintHash") != expected_blueprint_hash:
        raise WorkflowError("G5 Blueprint hash does not match the compilation report")
    if source_map.get("blueprintHash") != expected_blueprint_hash:
        raise WorkflowError("G5 Blueprint hash does not match the source map")

    expected_document_hash = canonical_json_hash(document)
    if report.get("courseDefinitionHash") != expected_document_hash:
        raise WorkflowError("G5 course definition hash does not match the compilation report")
    if source_map.get("courseDefinitionHash") != expected_document_hash:
        raise WorkflowError("G5 course definition hash does not match the source map")

    if report.get("sourceMapHash") != canonical_json_hash(source_map):
        raise WorkflowError("G5 source map hash does not match the compilation report")

    compiler_hash = hash_path(TOOLKIT_G5_ARTIFACTS["@toolkit/course-compiler"])
    snapshot_hash = hash_path(
        TOOLKIT_G5_ARTIFACTS["@toolkit/course-contract-snapshot"]
    )
    if report.get("compilerHash") != compiler_hash:
        raise WorkflowError("G5 compilation report was produced by different compiler code")
    if report.get("contractSnapshotHash") != snapshot_hash:
        raise WorkflowError("G5 compilation report uses a different contract snapshot")
    expected_snapshot = {
        "packageName": snapshot.get("packageName"),
        "packageVersion": snapshot.get("packageVersion"),
        "upstreamCommit": snapshot.get("upstreamCommit"),
    }
    if report.get("contractSnapshot") != expected_snapshot:
        raise WorkflowError("G5 shared contract identity does not match the snapshot")

    contract_result = validate_with_shared_contract(document)
    if not contract_result.ok:
        first = contract_result.issues[0] if contract_result.issues else None
        detail = first.message if first else "unknown contract failure"
        raise WorkflowError(f"G5 shared course contract rejected the definition: {detail}")
    if report.get("assetPaths") != sorted(contract_result.asset_paths):
        raise WorkflowError("G5 asset paths do not match the shared course contract")

    evidence = {label: hash_path(path) for label, path in relative_paths.items()}
    evidence["@toolkit/course-compiler"] = compiler_hash
    evidence["@toolkit/course-contract-snapshot"] = snapshot_hash
    return evidence


def verify_g6_validation(root: Path) -> Dict[str, str]:
    from course_toolkit.course_package_validation import (
        VALIDATION_REPORT_RELATIVE_PATH,
        build_course_validation_report,
        validation_issue_candidates,
        validator_code_hash,
    )

    root = root.resolve()
    verify_g5_compilation(root)
    report_path = root / VALIDATION_REPORT_RELATIVE_PATH
    if report_path.is_symlink() or not report_path.is_file():
        raise WorkflowError("G6 package validation report is missing")
    report = load_json(report_path)
    if report.get("status") not in {"clear", "warnings"} or report.get("issues"):
        raise WorkflowError("G6 package validation report is blocked")

    rebuilt = build_course_validation_report(root)
    if canonical_json_hash(report) != canonical_json_hash(rebuilt):
        raise WorkflowError("G6 package validation report is stale")
    if report.get("validatorHash") != validator_code_hash():
        raise WorkflowError("G6 package validation report uses stale validator code")

    store = IssueStore.load(root / ".course-work/issues.json")
    stored_by_fingerprint = {issue.fingerprint: issue for issue in store.all()}
    candidates = validation_issue_candidates(report, "verification")
    candidate_fingerprints = {candidate.fingerprint for candidate in candidates}
    for candidate in candidates:
        stored = stored_by_fingerprint.get(candidate.fingerprint)
        if stored is None or stored.status == "resolved":
            raise WorkflowError(
                "G6 validation findings are not synchronized with the issue store"
            )
        if (
            candidate.warning_policy == "acknowledgement-required"
            and stored.status != "accepted"
        ):
            raise WorkflowError(
                f"G6 warning requires acknowledgement: {stored.id}"
            )
    stale_active = next(
        (
            issue
            for issue in store.all()
            if issue.source == "validator"
            and issue.gate_id == "G6"
            and issue.status == "active"
            and issue.fingerprint not in candidate_fingerprints
        ),
        None,
    )
    if stale_active is not None:
        raise WorkflowError("G6 issue store contains stale active validation findings")

    evidence = {
        ".course-work/course-validation-report.json": hash_path(report_path),
        "@toolkit/course-package-validator": report["validatorHash"],
        "@course/asset-set": report["assetSetHash"],
    }
    for asset in report.get("assets", []):
        source = asset.get("source") if isinstance(asset, dict) else None
        asset_hash = asset.get("sha256") if isinstance(asset, dict) else None
        if not isinstance(source, str) or not isinstance(asset_hash, str):
            raise WorkflowError("G6 asset evidence is incomplete")
        evidence[f"{G6_ASSET_EVIDENCE_PREFIX}{source}"] = asset_hash
    return evidence


def verify_g9_publication_preflight(root: Path) -> Dict[str, str]:
    from course_toolkit.publication import (
        ASSET_MANIFEST_RELATIVE_PATH,
        PUBLICATION_PREFLIGHT_RELATIVE_PATH,
        PUBLICATION_REVIEW_EVIDENCE_RELATIVE_PATH,
        REMOTE_DISCOVERY_RELATIVE_PATH,
        PUBLISH_STATE_RELATIVE_PATH,
        PublicationReviewEvidence,
        publication_preflight_status,
    )
    from course_toolkit.publisher import publisher_code_hash

    root = root.resolve()
    session = load_session(root)
    if "G8" not in session.completed_gate_ids:
        raise WorkflowError("G9 publication preflight requires completed G8")
    verify_g6_validation(root)
    status = publication_preflight_status(root)
    if not status["approved"]:
        reason = ", ".join(status.get("staleReasons", [])) or status["decisionStatus"]
        raise WorkflowError(
            f"G9 publication preflight is not approved and current: {reason}"
        )
    evidence_document = PublicationReviewEvidence.from_dict(
        load_json(root / PUBLICATION_REVIEW_EVIDENCE_RELATIVE_PATH)
    )
    if not evidence_document.renderer_backed or evidence_document.status != "approved":
        raise WorkflowError("G9 requires renderer-backed G8 review evidence")
    issue_store = IssueStore.load(root / ".course-work/issues.json")
    blocker = next(
        (
            issue
            for issue in issue_store.all()
            if issue.status == "active"
            and issue.severity == "blocker"
            and GATE_INDEX[issue.gate_id] <= GATE_INDEX["G9"]
        ),
        None,
    )
    if blocker is not None:
        raise WorkflowError(f"G9 has an active blocker: {blocker.code}")
    paths = {
        ".course-work/publication-preflight.json": root
        / PUBLICATION_PREFLIGHT_RELATIVE_PATH,
        ".course-work/asset-manifest.json": root / ASSET_MANIFEST_RELATIVE_PATH,
        ".course-work/publish-state.json": root / PUBLISH_STATE_RELATIVE_PATH,
        ".course-work/publication-review-evidence.json": root
        / PUBLICATION_REVIEW_EVIDENCE_RELATIVE_PATH,
        ".course-work/remote-discovery.json": root / REMOTE_DISCOVERY_RELATIVE_PATH,
    }
    evidence = {label: hash_path(path) for label, path in paths.items()}
    evidence["@toolkit/course-publisher"] = publisher_code_hash()
    return evidence


def verify_g10_remote_publication(root: Path) -> Dict[str, str]:
    from course_toolkit.publication import (
        ASSET_MANIFEST_RELATIVE_PATH,
        PUBLICATION_PREFLIGHT_RELATIVE_PATH,
        PUBLISH_STATE_RELATIVE_PATH,
        load_publish_state,
    )
    from course_toolkit.publisher import (
        PUBLICATION_OPERATION_RELATIVE_PATH,
        load_publication_operation,
        publisher_code_hash,
    )

    root = root.resolve()
    operation = load_publication_operation(root)
    if operation.adapter_mode != "live":
        raise WorkflowError("G10 requires a live publication adapter operation")
    if operation.phase != "verified" or operation.verified_remote is None:
        raise WorkflowError("G10 requires verified remote read-back evidence")
    state = load_publish_state(root)
    remote = operation.verified_remote
    preflight = load_json(root / PUBLICATION_PREFLIGHT_RELATIVE_PATH)
    if canonical_json_hash(preflight) != operation.preflight_hash:
        raise WorkflowError("G10 operation differs from the approved publication preflight")
    if (
        state.remote_course_id != remote.remote_course_id
        or state.last_known_remote_revision != remote.revision
        or state.last_uploaded_definition_hash != remote.definition_hash
        or state.last_publish_operation_id != operation.operation_id
        or state.remote_status != remote.status
    ):
        raise WorkflowError("G10 publish state differs from verified remote read-back")
    if (
        remote.status == "published"
        and state.last_published_definition_hash != remote.definition_hash
    ):
        raise WorkflowError("G10 published definition hash is missing from publish state")
    manifest = load_json(root / ASSET_MANIFEST_RELATIVE_PATH)
    if manifest.get("courseDefinitionHash") != remote.definition_hash:
        raise WorkflowError("G10 asset manifest differs from verified remote definition")
    remote_pairs = {
        (asset["sha256"], asset["objectKey"]) for asset in remote.assets
    }
    for entry in manifest.get("entries", []):
        remote_record = entry.get("remote")
        if (
            entry.get("state") != "reusable"
            or not isinstance(remote_record, dict)
            or remote_record.get("uploadedSha256") != entry.get("sha256")
            or remote_record.get("objectKey") != entry.get("objectKey")
            or (entry.get("sha256"), entry.get("objectKey")) not in remote_pairs
        ):
            raise WorkflowError("G10 asset manifest lacks verified remote asset state")
    paths = {
        ".course-work/publication-operation.json": root
        / PUBLICATION_OPERATION_RELATIVE_PATH,
        ".course-work/asset-manifest.json": root / ASSET_MANIFEST_RELATIVE_PATH,
        ".course-work/publish-state.json": root / PUBLISH_STATE_RELATIVE_PATH,
    }
    evidence = {label: hash_path(path) for label, path in paths.items()}
    evidence["@toolkit/course-publisher"] = publisher_code_hash()
    return evidence


def _safe_course_path(root: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise WorkflowError(
            f"Course source must be a safe relative path: {relative_path}"
        )
    candidate = root
    for part in relative.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise WorkflowError(
                f"Course source must not traverse a symlink: {relative_path}"
            )
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise WorkflowError(
            f"Course source must be a safe relative path: {relative_path}"
        ) from exc
    return candidate


def _resolve_recurring_issue(
    store: IssueStore,
    candidate: CourseProductionIssue,
    now: str,
) -> None:
    existing = next(
        (
            issue
            for issue in store.all()
            if issue.fingerprint == candidate.fingerprint and issue.status == "active"
        ),
        None,
    )
    if existing is not None:
        store.resolve(existing.id, now)


def reconcile_artifacts(
    root: Path,
    session: CourseProductionSession,
    now: str,
) -> ArtifactReconciliationResult:
    root = root.resolve()
    issue_store = IssueStore.load(root / ".course-work" / "issues.json")
    changed_paths: List[str] = []
    missing_sources: List[str] = []
    changed_gate_ids: List[str] = []

    for source_path in session.source_paths:
        source = _safe_course_path(root, source_path)
        missing_issue = make_registered_issue(
            code="workflow-missing-source",
            source="workflow",
            message=f"Required source is missing: {source_path}",
            gate_id="G1",
            seen_at=now,
            target={"path": source_path},
            remediation="Restore the source file or explicitly remove it from intake.",
        )
        if not source.exists():
            missing_sources.append(source_path)
            issue_store.upsert(missing_issue)
        else:
            _resolve_recurring_issue(issue_store, missing_issue, now)

    rules = list(ARTIFACT_GATE_RULES)
    for source_path in session.source_paths:
        normalized = Path(source_path).as_posix()
        if normalized != "materials" and not normalized.startswith("materials/"):
            rules.append(ArtifactRule(normalized, "G1"))

    seen_rule_paths = set()
    for rule in rules:
        if rule.path in seen_rule_paths:
            continue
        seen_rule_paths.add(rule.path)
        artifact = _safe_course_path(root, rule.path.rstrip("/"))
        previous_hash = session.artifact_hashes.get(rule.path)
        current_hash = hash_path(artifact) if artifact.exists() else None
        if previous_hash is None:
            if current_hash is not None:
                session.artifact_hashes[rule.path] = current_hash
            continue
        if current_hash == previous_hash:
            continue

        changed_paths.append(rule.path)
        changed_gate_ids.append(rule.gate_id)
        issue_store.upsert(
            make_registered_issue(
                code="workflow-artifact-changed",
                source="workflow",
                message=f"Tracked course artifact changed: {rule.path}",
                gate_id=rule.gate_id,
                seen_at=now,
                target={"path": rule.path},
                remediation=f"Re-run workflow checks from {rule.gate_id}.",
            )
        )
        if current_hash is None:
            session.artifact_hashes.pop(rule.path, None)
        else:
            session.artifact_hashes[rule.path] = current_hash

    for artifact_id, artifact in TOOLKIT_G5_ARTIFACTS.items():
        previous_hash = session.artifact_hashes.get(artifact_id)
        if previous_hash is None:
            continue
        current_hash = hash_path(artifact)
        if current_hash == previous_hash:
            continue
        changed_paths.append(artifact_id)
        changed_gate_ids.append("G5")
        issue_store.upsert(
            make_registered_issue(
                code="workflow-artifact-changed",
                source="workflow",
                message=f"Tracked course artifact changed: {artifact_id}",
                gate_id="G5",
                seen_at=now,
                target={"path": artifact_id},
                remediation="Recompile the CourseDefinition and re-run G5 checks.",
            )
        )
        session.artifact_hashes[artifact_id] = current_hash

    for artifact_id, artifact in TOOLKIT_G9_ARTIFACTS.items():
        previous_hash = session.artifact_hashes.get(artifact_id)
        if previous_hash is None:
            continue
        current_hash = hash_path(artifact)
        if current_hash == previous_hash:
            continue
        changed_paths.append(artifact_id)
        changed_gate_ids.append("G9")
        issue_store.upsert(
            make_registered_issue(
                code="workflow-artifact-changed",
                source="workflow",
                message=f"Tracked course artifact changed: {artifact_id}",
                gate_id="G9",
                seen_at=now,
                target={"path": artifact_id},
                remediation="Prepare and approve a new publication dry run.",
            )
        )
        session.artifact_hashes[artifact_id] = current_hash

    validator_id = "@toolkit/course-package-validator"
    previous_validator_hash = session.artifact_hashes.get(validator_id)
    if previous_validator_hash is not None:
        from course_toolkit.course_package_validation import validator_code_hash

        current_validator_hash = validator_code_hash()
        if current_validator_hash != previous_validator_hash:
            changed_paths.append(validator_id)
            changed_gate_ids.append("G6")
            issue_store.upsert(
                make_registered_issue(
                    code="workflow-artifact-changed",
                    source="workflow",
                    message=f"Tracked course artifact changed: {validator_id}",
                    gate_id="G6",
                    seen_at=now,
                    target={"path": validator_id},
                    remediation="Re-run CourseDefinition 2.0 validation and G6.",
                )
            )
            session.artifact_hashes[validator_id] = current_validator_hash

    for artifact_id, previous_hash in list(session.artifact_hashes.items()):
        if not artifact_id.startswith(G6_ASSET_EVIDENCE_PREFIX):
            continue
        source = artifact_id.removeprefix(G6_ASSET_EVIDENCE_PREFIX)
        try:
            asset = _safe_course_path(root, source)
        except WorkflowError:
            current_hash = None
        else:
            current_hash = (
                hash_path(asset)
                if asset.is_file() and not asset.is_symlink()
                else None
            )
        if current_hash == previous_hash:
            continue
        changed_paths.append(artifact_id)
        changed_gate_ids.append("G6")
        issue_store.upsert(
            make_registered_issue(
                code="workflow-artifact-changed",
                source="workflow",
                message=f"Tracked course asset changed: {source}",
                gate_id="G6",
                seen_at=now,
                target={"path": source},
                remediation="Re-run CourseDefinition 2.0 validation and G6.",
            )
        )
        if current_hash is None:
            session.artifact_hashes.pop(artifact_id, None)
        else:
            session.artifact_hashes[artifact_id] = current_hash

    earliest_gate_id = None
    if changed_gate_ids:
        earliest_gate_id = min(changed_gate_ids, key=GATE_INDEX.__getitem__)
        invalidate_from_gate(session, earliest_gate_id, now)

    issue_store.save()
    active_issues = tuple(
        issue for issue in issue_store.all() if issue.status == "active"
    )
    session.active_issue_ids = [issue.id for issue in active_issues]
    session.updated_at = now
    return ArtifactReconciliationResult(
        changed_paths=tuple(changed_paths),
        missing_source_paths=tuple(missing_sources),
        earliest_invalidated_gate_id=earliest_gate_id,
        active_issues=active_issues,
    )
