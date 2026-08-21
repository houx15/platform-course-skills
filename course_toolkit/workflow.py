from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from course_toolkit.issues import (
    CourseProductionIssue,
    IssueStore,
    make_registered_issue,
)
from course_toolkit.course_compiler import (
    CONTRACT_SNAPSHOT,
    CompilationEvidenceError,
    verify_compilation_evidence,
)
from course_toolkit.hashing import canonical_json_hash, hash_path
from course_toolkit.instructional_plan import (
    COVERAGE_RELATIVE_PATH,
    PLAN_RELATIVE_PATH,
    PlanApprovalError,
    PlanValidationError,
    plan_content_hash,
    validate_plan_at_root,
    verify_plan_approval,
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
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ArtifactRule:
    path: str
    gate_id: str


ARTIFACT_GATE_RULES = (
    ArtifactRule("materials/", "G1"),
    ArtifactRule(".course-work/course-brief.json", "G2"),
    ArtifactRule(".course-work/source-coverage.json", "G3"),
    ArtifactRule(".course-work/media/", "G4"),
    ArtifactRule(".course-work/media-design.json", "G4"),
    ArtifactRule(".course-work/course-blueprint.json", "G5"),
    ArtifactRule("course/course.json", "G5"),
    ArtifactRule(".course-work/course-runtime-source-map.json", "G5"),
    ArtifactRule(".course-work/compilation-report.json", "G5"),
    ArtifactRule("course/assets/", "G6"),
    ArtifactRule(".course-work/course-validation-report.json", "G6"),
    ArtifactRule(".course-work/preview-manifest.json", "G7"),
    ArtifactRule(".course-work/annotations.json", "G7"),
    ArtifactRule(".course-work/review-report.json", "G8"),
    ArtifactRule(".course-work/course-catalog-selection.json", "G9"),
    ArtifactRule(".course-work/asset-manifest.json", "G9"),
    ArtifactRule(".course-work/publish-state.json", "G9"),
    ArtifactRule(".course-work/publication-review-evidence.json", "G9"),
    ArtifactRule(".course-work/remote-discovery.json", "G9"),
    ArtifactRule(".course-work/publication-preflight.json", "G9"),
    ArtifactRule(".course-work/publication-operation.json", "G10"),
)

G3_EVIDENCE_KEYS = (
    ".course-work/source-coverage.json",
    ".course-work/course-storyboard.json",
)

G4_EVIDENCE_KEYS = (
    ".course-work/course-storyboard.json",
    ".course-work/media-design.json",
    "@decision/course-plan-approval",
)
G4_PREREQUISITE_COVERAGE_KEY = "@upstream/g3-source-coverage"
G4_PREREQUISITE_EVIDENCE_KEYS = (G4_PREREQUISITE_COVERAGE_KEY,)
MEDIA_DESIGN_RELATIVE_PATH = ".course-work/media-design.json"
MEDIA_DESIGN_SCHEMA_VERSION = "1.0"
MEDIA_KINDS_BY_EXTENSION = {
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".webp": "image",
    ".svg": "image",
    ".mp4": "video",
    ".webm": "video",
    ".mov": "video",
    ".html": "html",
    ".htm": "html",
    ".mp3": "audio",
    ".wav": "audio",
    ".m4a": "audio",
    ".aac": "audio",
    ".ogg": "audio",
}
# G4 confirms a design decision, not produced delivery media. A single status
# avoids implying that any source asset has already been rendered or recorded.
MEDIA_DESIGN_STATUSES = frozenset({"planned"})

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

G8_EVIDENCE_KEYS = (
    ".course-work/review-report.json",
    ".course-work/course-validation-report.json",
    ".course-work/preview-manifest.json",
)

G9_EVIDENCE_KEYS = (
    ".course-work/publication-preflight.json",
    ".course-work/asset-manifest.json",
    ".course-work/publish-state.json",
    ".course-work/publication-review-evidence.json",
    ".course-work/remote-discovery.json",
    "@toolkit/course-publisher",
)
# The live publisher additionally binds the fixed catalog selection. Older
# local publication adapters may not have that artifact, so it is known and
# hash-validated when present without becoming a fabricated requirement.
G9_OPTIONAL_EVIDENCE_KEYS = (
    ".course-work/course-catalog-selection.json",
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
    page_plan_proof_gate_id: Optional[str] = None


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
    """Deserialize the stored session without examining current course files."""
    return CourseProductionSession.from_dict(load_json(root / SESSION_RELATIVE_PATH))


def save_session(root: Path, session: CourseProductionSession) -> None:
    write_json_atomic(root / SESSION_RELATIVE_PATH, session.as_dict())


def _has_sha256_evidence(session: CourseProductionSession, key: str) -> bool:
    value = session.artifact_hashes.get(key)
    return isinstance(value, str) and SHA256_HEX.fullmatch(value) is not None


def _first_unproved_page_plan_gate(
    root: Path,
    session: CourseProductionSession,
) -> Optional[str]:
    if "G3" in session.completed_gate_ids and not all(
        _has_sha256_evidence(session, key) for key in G3_EVIDENCE_KEYS
    ):
        return "G3"
    if "G4" in session.completed_gate_ids and not all(
        _has_sha256_evidence(session, key)
        for key in (
            ".course-work/media-design.json",
            "@decision/course-plan-approval",
        )
    ):
        return "G4"
    if "G3" in session.completed_gate_ids:
        try:
            current_g3 = verify_g3_plan(root)
        except WorkflowError:
            return "G3"
        if any(
            session.artifact_hashes.get(key) != value
            for key, value in current_g3.items()
        ):
            return "G3"
    if "G4" in session.completed_gate_ids:
        try:
            current_g4 = verify_g4_media_design(root)
        except WorkflowError:
            return "G4"
        for key in (".course-work/media-design.json", "@decision/course-plan-approval"):
            if session.artifact_hashes.get(key) != current_g4[key]:
                return "G4"
    return None


def reconcile_current_session(
    root: Path,
    session: CourseProductionSession,
    now: str,
) -> ArtifactReconciliationResult:
    """Reconcile evidence that the current session already records.

    Callers that act on a completed gate must use this rather than relying on
    ``load_session``: loading is intentionally a pure deserialization operation.
    New authoring steps are required when a new course reaches them, but their
    absence never retroactively invalidates a legacy session that already
    completed later work.
    """
    result = reconcile_artifacts(root, session, now)
    save_session(root, session)
    return result


def _validate_gate_evidence(
    session: CourseProductionSession,
    gate_id: str,
    evidence: Dict[str, str],
    required_keys: Sequence[str],
    label: str,
) -> Dict[str, str]:
    missing = [key for key in required_keys if key not in evidence]
    if missing:
        raise WorkflowError(f"{gate_id} requires {label}: {missing[0]}")
    allowed_dynamic_keys = (
        {key for key in evidence if key.startswith(G6_ASSET_EVIDENCE_PREFIX)}
        if gate_id == "G6"
        else set()
    )
    allowed_optional_keys = (
        set(G9_OPTIONAL_EVIDENCE_KEYS) if gate_id == "G9" else set()
    )
    unexpected = sorted(
        set(evidence)
        .difference(required_keys)
        .difference(allowed_dynamic_keys)
        .difference(allowed_optional_keys)
    )
    if unexpected:
        raise WorkflowError(f"{gate_id} has unexpected evidence: {unexpected[0]}")
    invalid = [
        key
        for key in evidence
        if not isinstance(evidence[key], str) or not SHA256_HEX.fullmatch(evidence[key])
    ]
    if invalid:
        raise WorkflowError(f"{gate_id} evidence must be a SHA-256 hash: {invalid[0]}")
    if gate_id == "G4":
        g3_storyboard_hash = session.artifact_hashes.get(
            ".course-work/course-storyboard.json"
        )
        g3_coverage_hash = session.artifact_hashes.get(
            ".course-work/source-coverage.json"
        )
        if not isinstance(g3_storyboard_hash, str) or not SHA256_HEX.fullmatch(
            g3_storyboard_hash
        ):
            raise WorkflowError("G4 requires current G3 page-plan evidence")
        if not isinstance(g3_coverage_hash, str) or not SHA256_HEX.fullmatch(
            g3_coverage_hash
        ):
            raise WorkflowError("G4 requires current G3 source-coverage evidence")
        if evidence[".course-work/course-storyboard.json"] != g3_storyboard_hash:
            raise WorkflowError("G4 page plan differs from completed G3")
        if evidence[G4_PREREQUISITE_COVERAGE_KEY] != g3_coverage_hash:
            raise WorkflowError("G4 source coverage differs from completed G3")
        # The storyboard semantic hash belongs to G3. G4 verifies it but never
        # replaces that baseline with approval-era evidence.
        return {
            key: value
            for key, value in evidence.items()
            if key
            not in {
                ".course-work/course-storyboard.json",
                G4_PREREQUISITE_COVERAGE_KEY,
            }
        }
    return dict(evidence)


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
    evidence_requirements = {
        "G3": (G3_EVIDENCE_KEYS, "current page-plan evidence"),
        "G4": (
            (*G4_EVIDENCE_KEYS, *G4_PREREQUISITE_EVIDENCE_KEYS),
            "current approved page-plan and media-design evidence",
        ),
        "G5": (G5_EVIDENCE_KEYS, "current compilation evidence"),
        "G6": (G6_EVIDENCE_KEYS, "current package validation evidence"),
        "G7": (G7_EVIDENCE_KEYS, "current renderer preview evidence"),
        "G8": (G8_EVIDENCE_KEYS, "current independent review evidence"),
        "G9": (G9_EVIDENCE_KEYS, "current publication preflight evidence"),
        "G10": (G10_EVIDENCE_KEYS, "current remote verification evidence"),
    }
    if gate_id in evidence_requirements:
        required_keys, label = evidence_requirements[gate_id]
        evidence = gate_evidence or {}
        session.artifact_hashes.update(
            _validate_gate_evidence(
                session, gate_id, evidence, required_keys, label
            )
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


def resolve_completed_evidence_issues(
    root: Path,
    session: CourseProductionSession,
    gate_id: str,
    now: str,
) -> Tuple[CourseProductionIssue, ...]:
    """Resolve only changed-artifact issues proved current by this completion.

    Reconciliation records a new baseline before invalidating a completed gate.
    Once the matching verifier and gate completion have succeeded, retaining
    that warning would require an unnecessary second reconciliation command.
    """
    evidence_paths = {
        "G3": set(G3_EVIDENCE_KEYS),
        # G4 observes the G3 storyboard hash but does not own or replace it.
        "G4": set(G4_EVIDENCE_KEYS).difference(
            {".course-work/course-storyboard.json"}
        ).union({".course-work/media/"}),
    }.get(gate_id)
    if not evidence_paths:
        return ()
    issue_store = IssueStore.load(root / ".course-work" / "issues.json")
    for issue in issue_store.all():
        target_path = issue.target.get("path") if isinstance(issue.target, dict) else None
        if (
            issue.status == "active"
            and issue.code
            in {
                "workflow-artifact-changed",
                "workflow-page-plan-evidence-unproved",
            }
            and issue.gate_id == gate_id
            and (
                target_path in evidence_paths
                or target_path == "@workflow/unproved-page-plan-evidence"
            )
        ):
            issue_store.resolve(issue.id, now)
    issue_store.save()
    active_issues = tuple(
        issue for issue in issue_store.all() if issue.status == "active"
    )
    session.active_issue_ids = [issue.id for issue in active_issues]
    return active_issues


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


def _plan_validation_error(gate_id: str, issues: Sequence[object]) -> WorkflowError:
    first = issues[0] if issues else None
    code = getattr(first, "code", "invalid-plan")
    return WorkflowError(f"{gate_id} page plan is invalid: {code}")


def _safe_json_object(root: Path, relative_path: str, *, gate_id: str) -> Tuple[Path, dict]:
    path = _safe_course_path(root, relative_path)
    if path.is_symlink() or not path.is_file():
        raise WorkflowError(f"{gate_id} evidence is missing: {relative_path}")
    try:
        document = load_json(path)
    except ValueError as exc:
        raise WorkflowError(f"{gate_id} evidence is invalid JSON: {relative_path}") from exc
    if not isinstance(document, dict):
        raise WorkflowError(f"{gate_id} evidence must be a JSON object: {relative_path}")
    return path, document


def _media_design_error(code: str) -> WorkflowError:
    return WorkflowError(f"G4 media design is invalid: {code}")


def _plan_media_uses(plan: dict, coverage: dict) -> Tuple[set, set]:
    coverage_by_id = {
        item.get("sourceId"): item
        for item in coverage.get("items", [])
        if isinstance(item, dict) and isinstance(item.get("sourceId"), str)
    }
    media_uses = set()
    slices = set()
    for part in plan.get("parts", []):
        if not isinstance(part, dict):
            continue
        part_id = part.get("partId")
        for slice_data in part.get("slices", []):
            if not isinstance(slice_data, dict):
                continue
            slice_id = slice_data.get("sliceId")
            if not isinstance(part_id, str) or not isinstance(slice_id, str):
                continue
            slices.add((part_id, slice_id))
            for source_use in slice_data.get("sourceUses", []):
                if not isinstance(source_use, dict):
                    continue
                source_id = source_use.get("sourceId")
                source = coverage_by_id.get(source_id)
                source_path = source.get("sourceFile") if isinstance(source, dict) else None
                if not isinstance(source_id, str) or not isinstance(source_path, str):
                    continue
                kind = MEDIA_KINDS_BY_EXTENSION.get(Path(source_path).suffix.lower())
                if kind is not None:
                    media_uses.add((source_id, part_id, slice_id, source_path, kind))
    return media_uses, slices


def _validate_media_design(root: Path, document: dict, plan: dict, coverage: dict) -> None:
    """Validate lightweight G4 source-use and narration preparation evidence.

    This is deliberately a plan for media/narration work, not a delivery asset
    schema: every planned Slice names narration readiness, while every media
    source the plan exposes names how it will be prepared.
    """
    if set(document).difference({"schemaVersion", "planContentHash", "items", "narrations"}):
        raise _media_design_error("unknown-field")
    if document.get("schemaVersion") != MEDIA_DESIGN_SCHEMA_VERSION:
        raise _media_design_error("schema-version")
    if document.get("planContentHash") != plan_content_hash(plan):
        raise _media_design_error("stale-plan")
    items = document.get("items")
    narrations = document.get("narrations")
    if not isinstance(items, list) or not isinstance(narrations, list):
        raise _media_design_error("items-and-narrations-required")
    expected_media, expected_slices = _plan_media_uses(plan, coverage)
    actual_media = set()
    for item in items:
        if not isinstance(item, dict):
            raise _media_design_error("media-item-shape")
        if set(item).difference({"sourceId", "partId", "sliceId", "kind", "sourcePath", "status"}):
            raise _media_design_error("media-item-unknown-field")
        values = {field: item.get(field) for field in ("sourceId", "partId", "sliceId", "kind", "sourcePath", "status")}
        if not all(isinstance(value, str) and value.strip() for value in values.values()):
            raise _media_design_error("media-item-required-field")
        key = (values["sourceId"], values["partId"], values["sliceId"], values["sourcePath"], values["kind"])
        if key in actual_media:
            raise _media_design_error("duplicate-media-item")
        if values["status"] not in MEDIA_DESIGN_STATUSES:
            raise _media_design_error("media-status")
        if key not in expected_media:
            raise _media_design_error("media-item-mismatch")
        try:
            source_path = _safe_course_path(root, values["sourcePath"])
        except WorkflowError as exc:
            raise _media_design_error("media-path") from exc
        if source_path.is_symlink() or not source_path.is_file():
            raise _media_design_error("media-source-missing")
        actual_media.add(key)
    if actual_media != expected_media:
        raise _media_design_error("media-items-incomplete")
    actual_narrations = set()
    for narration in narrations:
        if not isinstance(narration, dict):
            raise _media_design_error("narration-shape")
        if set(narration).difference({"partId", "sliceId", "status"}):
            raise _media_design_error("narration-unknown-field")
        part_id = narration.get("partId")
        slice_id = narration.get("sliceId")
        status = narration.get("status")
        if not all(isinstance(value, str) and value.strip() for value in (part_id, slice_id, status)):
            raise _media_design_error("narration-required-field")
        key = (part_id, slice_id)
        if key in actual_narrations:
            raise _media_design_error("duplicate-narration")
        if status not in MEDIA_DESIGN_STATUSES:
            raise _media_design_error("narration-status")
        actual_narrations.add(key)
    if actual_narrations != expected_slices:
        raise _media_design_error("narrations-incomplete")


def verify_g3_plan(root: Path) -> Dict[str, str]:
    """Verify the current semantic Part/Slice plan and source coverage for G3."""
    root = Path(root).absolute()
    try:
        issues = validate_plan_at_root(root)
    except PlanValidationError as exc:
        raise _plan_validation_error("G3", exc.issues) from exc
    if issues:
        raise _plan_validation_error("G3", issues)
    _, plan = _safe_json_object(root, PLAN_RELATIVE_PATH, gate_id="G3")
    coverage_path, _ = _safe_json_object(root, COVERAGE_RELATIVE_PATH, gate_id="G3")
    return {
        ".course-work/source-coverage.json": hash_path(coverage_path),
        # Do not use the raw storyboard bytes: approval metadata is not plan content.
        ".course-work/course-storyboard.json": plan_content_hash(plan),
    }


def _approval_evidence_hash(root: Path) -> Optional[str]:
    """Return current approval identity, or None when it is absent or stale."""
    try:
        approval = verify_plan_approval(root)
    except (PlanApprovalError, PlanValidationError):
        return None
    return canonical_json_hash(approval)


def verify_g4_media_design(root: Path) -> Dict[str, str]:
    """Verify G4's approved plan identity and strict local media-design object."""
    root = Path(root).absolute()
    plan_evidence = verify_g3_plan(root)
    try:
        approval = verify_plan_approval(root)
    except PlanValidationError as exc:
        raise _plan_validation_error("G4", exc.issues) from exc
    except PlanApprovalError as exc:
        raise WorkflowError(f"G4 page-plan approval is {exc.code}: {exc}") from exc
    media_path, media_design = _safe_json_object(
        root, MEDIA_DESIGN_RELATIVE_PATH, gate_id="G4"
    )
    _, plan = _safe_json_object(root, PLAN_RELATIVE_PATH, gate_id="G4")
    _, coverage = _safe_json_object(root, COVERAGE_RELATIVE_PATH, gate_id="G4")
    _validate_media_design(root, media_design, plan, coverage)
    return {
        ".course-work/course-storyboard.json": plan_evidence[
            ".course-work/course-storyboard.json"
        ],
        MEDIA_DESIGN_RELATIVE_PATH: hash_path(media_path),
        "@decision/course-plan-approval": canonical_json_hash(approval),
        G4_PREREQUISITE_COVERAGE_KEY: plan_evidence[
            ".course-work/source-coverage.json"
        ],
    }


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
    try:
        verify_compilation_evidence(blueprint, document, source_map, report)
    except CompilationEvidenceError as exc:
        raise WorkflowError(str(exc)) from exc

    compiler_hash = hash_path(TOOLKIT_G5_ARTIFACTS["@toolkit/course-compiler"])
    snapshot_hash = hash_path(
        TOOLKIT_G5_ARTIFACTS["@toolkit/course-contract-snapshot"]
    )

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
    reconcile_current_session(
        root,
        session,
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
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
    catalog_selection_path = root / ".course-work" / "course-catalog-selection.json"
    if catalog_selection_path.exists():
        evidence[".course-work/course-catalog-selection.json"] = hash_path(
            catalog_selection_path
        )
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
    root = Path(root).absolute()
    if root.is_symlink():
        raise WorkflowError("Course root may not be a symlink")
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
    root = Path(root).absolute()
    if root.is_symlink():
        raise WorkflowError("Course root may not be a symlink")
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
        change_issue = make_registered_issue(
            code="workflow-artifact-changed",
            source="workflow",
            message=f"Tracked course artifact changed: {rule.path}",
            gate_id=rule.gate_id,
            seen_at=now,
            target={"path": rule.path},
            remediation=f"Re-run workflow checks from {rule.gate_id}.",
        )
        if previous_hash is None:
            if current_hash is not None:
                session.artifact_hashes[rule.path] = current_hash
                _resolve_recurring_issue(issue_store, change_issue, now)
            continue
        if current_hash == previous_hash:
            _resolve_recurring_issue(issue_store, change_issue, now)
            continue

        changed_paths.append(rule.path)
        changed_gate_ids.append(rule.gate_id)
        issue_store.upsert(change_issue)
        if current_hash is None:
            session.artifact_hashes.pop(rule.path, None)
        else:
            session.artifact_hashes[rule.path] = current_hash

    # The storyboard file contains approval metadata alongside the teacher's
    # plan. Track its Task 2 semantic projection instead of its raw bytes, so
    # recording or refreshing approval cannot invalidate G3.
    plan_artifact_id = ".course-work/course-storyboard.json"
    previous_plan_hash = session.artifact_hashes.get(plan_artifact_id)
    try:
        _, current_plan = _safe_json_object(root, PLAN_RELATIVE_PATH, gate_id="G3")
        current_plan_hash = plan_content_hash(current_plan)
    except WorkflowError:
        current_plan_hash = None
    plan_change_issue = make_registered_issue(
        code="workflow-artifact-changed",
        source="workflow",
        message=f"Tracked course artifact changed: {plan_artifact_id}",
        gate_id="G3",
        seen_at=now,
        target={"path": plan_artifact_id},
        remediation="Re-check the page plan and complete G3 again.",
    )
    if previous_plan_hash is None:
        if current_plan_hash is not None:
            session.artifact_hashes[plan_artifact_id] = current_plan_hash
            _resolve_recurring_issue(issue_store, plan_change_issue, now)
    elif current_plan_hash == previous_plan_hash:
        _resolve_recurring_issue(issue_store, plan_change_issue, now)
    else:
        changed_paths.append(plan_artifact_id)
        changed_gate_ids.append("G3")
        issue_store.upsert(plan_change_issue)
        if current_plan_hash is None:
            session.artifact_hashes.pop(plan_artifact_id, None)
        else:
            session.artifact_hashes[plan_artifact_id] = current_plan_hash

    approval_artifact_id = "@decision/course-plan-approval"
    previous_approval_hash = session.artifact_hashes.get(approval_artifact_id)
    current_approval_hash = _approval_evidence_hash(root)
    approval_change_issue = make_registered_issue(
        code="workflow-artifact-changed",
        source="workflow",
        message=f"Tracked course artifact changed: {approval_artifact_id}",
        gate_id="G4",
        seen_at=now,
        target={"path": approval_artifact_id},
        remediation="Confirm the current page plan again and complete G4.",
    )
    if previous_approval_hash is None:
        if current_approval_hash is not None:
            session.artifact_hashes[approval_artifact_id] = current_approval_hash
            _resolve_recurring_issue(issue_store, approval_change_issue, now)
    elif current_approval_hash == previous_approval_hash:
        _resolve_recurring_issue(issue_store, approval_change_issue, now)
    else:
        changed_paths.append(approval_artifact_id)
        changed_gate_ids.append("G4")
        issue_store.upsert(approval_change_issue)
        if current_approval_hash is None:
            session.artifact_hashes.pop(approval_artifact_id, None)
        else:
            session.artifact_hashes[approval_artifact_id] = current_approval_hash

    for artifact_id, artifact in TOOLKIT_G5_ARTIFACTS.items():
        previous_hash = session.artifact_hashes.get(artifact_id)
        if previous_hash is None:
            continue
        current_hash = hash_path(artifact)
        change_issue = make_registered_issue(
            code="workflow-artifact-changed",
            source="workflow",
            message=f"Tracked course artifact changed: {artifact_id}",
            gate_id="G5",
            seen_at=now,
            target={"path": artifact_id},
            remediation="Recompile the CourseDefinition and re-run G5 checks.",
        )
        if current_hash == previous_hash:
            _resolve_recurring_issue(issue_store, change_issue, now)
            continue
        changed_paths.append(artifact_id)
        changed_gate_ids.append("G5")
        issue_store.upsert(change_issue)
        session.artifact_hashes[artifact_id] = current_hash

    for artifact_id, artifact in TOOLKIT_G9_ARTIFACTS.items():
        previous_hash = session.artifact_hashes.get(artifact_id)
        if previous_hash is None:
            continue
        if artifact_id == "@toolkit/course-publisher":
            from course_toolkit.publisher import publisher_code_hash

            current_hash = publisher_code_hash()
        else:
            current_hash = hash_path(artifact)
        change_issue = make_registered_issue(
            code="workflow-artifact-changed",
            source="workflow",
            message=f"Tracked course artifact changed: {artifact_id}",
            gate_id="G9",
            seen_at=now,
            target={"path": artifact_id},
            remediation="Prepare and approve a new publication dry run.",
        )
        if current_hash == previous_hash:
            _resolve_recurring_issue(issue_store, change_issue, now)
            continue
        changed_paths.append(artifact_id)
        changed_gate_ids.append("G9")
        issue_store.upsert(change_issue)
        session.artifact_hashes[artifact_id] = current_hash

    validator_id = "@toolkit/course-package-validator"
    previous_validator_hash = session.artifact_hashes.get(validator_id)
    if previous_validator_hash is not None:
        from course_toolkit.course_package_validation import validator_code_hash

        current_validator_hash = validator_code_hash()
        change_issue = make_registered_issue(
            code="workflow-artifact-changed",
            source="workflow",
            message=f"Tracked course artifact changed: {validator_id}",
            gate_id="G6",
            seen_at=now,
            target={"path": validator_id},
            remediation="Re-run CourseDefinition 2.0 validation and G6.",
        )
        if current_validator_hash != previous_validator_hash:
            changed_paths.append(validator_id)
            changed_gate_ids.append("G6")
            issue_store.upsert(change_issue)
            session.artifact_hashes[validator_id] = current_validator_hash
        else:
            _resolve_recurring_issue(issue_store, change_issue, now)

    for artifact_id, previous_hash in list(session.artifact_hashes.items()):
        if not artifact_id.startswith(G6_ASSET_EVIDENCE_PREFIX):
            continue
        source = artifact_id.removeprefix(G6_ASSET_EVIDENCE_PREFIX)
        try:
            asset = _safe_course_path(root / "course", source)
        except WorkflowError:
            current_hash = None
        else:
            current_hash = (
                hash_path(asset)
                if asset.is_file() and not asset.is_symlink()
                else None
            )
        change_issue = make_registered_issue(
            code="workflow-artifact-changed",
            source="workflow",
            message=f"Tracked course asset changed: {source}",
            gate_id="G6",
            seen_at=now,
            target={"path": source},
            remediation="Re-run CourseDefinition 2.0 validation and G6.",
        )
        if current_hash == previous_hash:
            _resolve_recurring_issue(issue_store, change_issue, now)
            continue
        changed_paths.append(artifact_id)
        changed_gate_ids.append("G6")
        issue_store.upsert(change_issue)
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
        page_plan_proof_gate_id=None,
    )
