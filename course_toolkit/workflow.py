import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from course_toolkit.issues import (
    CourseProductionIssue,
    IssueStore,
    make_registered_issue,
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
    ArtifactRule("course/assets/", "G6"),
    ArtifactRule(".course-work/preview-manifest.json", "G7"),
    ArtifactRule(".course-work/annotations.json", "G7"),
    ArtifactRule(".course-work/review-report.json", "G8"),
    ArtifactRule(".course-work/asset-manifest.json", "G9"),
    ArtifactRule(".course-work/publish-state.json", "G9"),
)


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
