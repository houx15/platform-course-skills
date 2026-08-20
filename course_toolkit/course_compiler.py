import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from course_toolkit.blueprint import (
    BlueprintIssue,
    index_blueprint_targets,
    project_course_definition,
    validate_blueprint_authoring,
)
from course_toolkit.hashing import canonical_json_hash
from course_toolkit.jsonio import dump_json


COMPILER_VERSION = "1.1"
ROOT = Path(__file__).resolve().parent.parent
CONTRACT_SNAPSHOT = ROOT / "course-contract.snapshot.json"
CONTRACT_VALIDATOR = (
    ROOT / "course_toolkit" / "runtime_dist" / "validate-course-definition.mjs"
)


@dataclass(frozen=True)
class CompilationIssue:
    path: str
    code: str
    message: str
    layer: str
    severity: str


@dataclass(frozen=True)
class SharedContractResult:
    ok: bool
    asset_paths: Sequence[str]
    issues: Sequence[CompilationIssue]


@dataclass(frozen=True)
class CompilationResult:
    document: dict
    source_map: dict
    report: dict


class CompilationBlocked(ValueError):
    def __init__(self, issues: Sequence[CompilationIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__("; ".join(f"{issue.path}: {issue.message}" for issue in issues))


class CompilationToolError(RuntimeError):
    pass


class CompilationEvidenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


ContractValidator = Callable[[dict], SharedContractResult]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _authoring_issue(issue: BlueprintIssue) -> CompilationIssue:
    return CompilationIssue(
        path=issue.path,
        code=issue.code,
        message=issue.message,
        layer="authoring",
        severity="decision-required" if issue.code == "blueprint-unconfirmed" else "blocker",
    )


def _load_contract_snapshot() -> dict:
    try:
        snapshot = json.loads(CONTRACT_SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CompilationToolError(f"Cannot read shared contract snapshot: {exc}") from exc
    required = {"upstreamCommit", "packageName", "packageVersion"}
    if not isinstance(snapshot, dict) or not required.issubset(snapshot):
        raise CompilationToolError("Shared contract snapshot is incomplete")
    return snapshot


def validate_with_shared_contract(document: dict) -> SharedContractResult:
    with tempfile.TemporaryDirectory(prefix="course-contract-") as temporary:
        input_path = Path(temporary) / "course-definition.json"
        input_path.write_text(
            json.dumps(document, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            completed = subprocess.run(
                ["node", str(CONTRACT_VALIDATOR), str(input_path), "--json"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            raise CompilationToolError(f"Cannot run shared course contract: {exc}") from exc

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        raise CompilationToolError(
            f"Shared course contract returned unreadable output: {detail}"
        ) from exc

    if completed.returncode == 0 and payload.get("ok") is True:
        asset_paths = payload.get("assetPaths")
        if not isinstance(asset_paths, list) or not all(
            isinstance(path, str) for path in asset_paths
        ):
            raise CompilationToolError("Shared course contract returned invalid asset paths")
        return SharedContractResult(ok=True, asset_paths=tuple(asset_paths), issues=())

    if completed.returncode == 2 and payload.get("ok") is False:
        raw_issues = payload.get("issues")
        if not isinstance(raw_issues, list):
            raise CompilationToolError("Shared course contract returned invalid issues")
        issues: List[CompilationIssue] = []
        for item in raw_issues:
            if not isinstance(item, dict):
                raise CompilationToolError("Shared course contract returned invalid issue")
            path = item.get("path")
            message = item.get("message")
            layer = item.get("layer")
            if not all(isinstance(value, str) for value in (path, message, layer)):
                raise CompilationToolError("Shared course contract returned incomplete issue")
            issues.append(
                CompilationIssue(
                    path=path,
                    code="course-contract-invalid",
                    message=message,
                    layer=layer,
                    severity="blocker",
                )
            )
        return SharedContractResult(ok=False, asset_paths=(), issues=tuple(issues))

    error = payload.get("error") if isinstance(payload, dict) else None
    detail = error or completed.stderr.strip() or f"exit code {completed.returncode}"
    raise CompilationToolError(f"Shared course contract failed: {detail}")


def build_runtime_source_map(data: dict, document: dict) -> dict:
    targets = index_blueprint_targets(data)
    provenance = {
        record["targetId"]: record
        for record in data.get("provenance", [])
        if isinstance(record, dict) and isinstance(record.get("targetId"), str)
    }
    mappings = []
    for target_id, blueprint_pointer in targets.items():
        record = provenance.get(target_id, {})
        mappings.append(
            {
                "targetId": target_id,
                "blueprintPointer": blueprint_pointer,
                "runtimePointer": blueprint_pointer,
                "sourceIds": list(record.get("sourceIds", [])),
                "decisionIds": list(record.get("decisionIds", [])),
            }
        )
    return {
        "schemaVersion": "1.0",
        "compilerVersion": COMPILER_VERSION,
        "blueprintHash": canonical_json_hash(data),
        "courseDefinitionHash": canonical_json_hash(document),
        "mappings": mappings,
    }


def verify_compilation_evidence(
    blueprint: object,
    document: object,
    source_map: object,
    report: object,
) -> None:
    """Verify current G5 compilation facts without reading package paths."""
    if not isinstance(blueprint, dict) or not isinstance(document, dict):
        raise CompilationEvidenceError(
            "compilation-evidence-invalid",
            "G5 Blueprint and CourseDefinition must be objects",
        )
    if not isinstance(source_map, dict) or not isinstance(report, dict):
        raise CompilationEvidenceError(
            "compilation-evidence-invalid",
            "G5 source map and compilation report must be objects",
        )

    # The report and source map are mutable package files.  Rebuild their pure
    # compiler outputs before accepting their recorded hashes as evidence.
    try:
        expected_document = project_course_definition(blueprint)
        expected_source_map = build_runtime_source_map(blueprint, expected_document)
    except (KeyError, TypeError, ValueError) as exc:
        raise CompilationEvidenceError(
            "compilation-evidence-invalid",
            "G5 Blueprint cannot be compiled into current evidence",
        ) from exc
    if document != expected_document:
        raise CompilationEvidenceError(
            "course-definition-derivation-mismatch",
            "G5 CourseDefinition does not match compilation from the current Blueprint",
        )
    if source_map != expected_source_map:
        raise CompilationEvidenceError(
            "source-map-derivation-mismatch",
            "G5 source map does not match compilation from the current Blueprint",
        )

    if report.get("status") != "compiled" or report.get("issues") != []:
        raise CompilationEvidenceError(
            "compilation-report-invalid",
            "G5 compilation report is not successful",
        )
    if report.get("compilerVersion") != COMPILER_VERSION:
        raise CompilationEvidenceError(
            "compilation-report-identity-invalid",
            "G5 compilation report uses a stale compiler version",
        )
    if source_map.get("schemaVersion") != "1.0" or source_map.get(
        "compilerVersion"
    ) != COMPILER_VERSION:
        raise CompilationEvidenceError(
            "source-map-identity-invalid",
            "G5 source map uses an invalid schema or stale compiler version",
        )

    expected_blueprint_hash = canonical_json_hash(blueprint)
    if report.get("blueprintHash") != expected_blueprint_hash:
        raise CompilationEvidenceError(
            "compilation-report-blueprint-stale",
            "G5 Blueprint hash does not match the compilation report",
        )
    if source_map.get("blueprintHash") != expected_blueprint_hash:
        raise CompilationEvidenceError(
            "source-map-blueprint-stale",
            "G5 Blueprint hash does not match the source map",
        )

    expected_document_hash = canonical_json_hash(document)
    if report.get("courseDefinitionHash") != expected_document_hash:
        raise CompilationEvidenceError(
            "compilation-report-definition-stale",
            "G5 course definition hash does not match the compilation report",
        )
    if source_map.get("courseDefinitionHash") != expected_document_hash:
        raise CompilationEvidenceError(
            "source-map-stale",
            "G5 course definition hash does not match the source map",
        )
    if report.get("sourceMapHash") != canonical_json_hash(source_map):
        raise CompilationEvidenceError(
            "compilation-report-source-map-mismatch",
            "G5 source map hash does not match the compilation report",
        )

    compiler_hash = file_sha256(Path(__file__))
    snapshot_hash = file_sha256(CONTRACT_SNAPSHOT)
    if report.get("compilerHash") != compiler_hash:
        raise CompilationEvidenceError(
            "compilation-report-compiler-mismatch",
            "G5 compilation report was produced by different compiler code",
        )
    if report.get("contractSnapshotHash") != snapshot_hash:
        raise CompilationEvidenceError(
            "compilation-report-contract-mismatch",
            "G5 compilation report uses a different contract snapshot",
        )
    snapshot = _load_contract_snapshot()
    expected_snapshot = {
        "packageName": snapshot.get("packageName"),
        "packageVersion": snapshot.get("packageVersion"),
        "upstreamCommit": snapshot.get("upstreamCommit"),
    }
    if report.get("contractSnapshot") != expected_snapshot:
        raise CompilationEvidenceError(
            "compilation-report-contract-identity-mismatch",
            "G5 shared contract identity does not match the snapshot",
        )
    contract_result = validate_with_shared_contract(document)
    if not contract_result.ok:
        first = contract_result.issues[0] if contract_result.issues else None
        detail = first.message if first else "unknown contract failure"
        raise CompilationEvidenceError(
            "course-contract-invalid",
            f"G5 shared course contract rejected the definition: {detail}",
        )
    if report.get("assetPaths") != sorted(contract_result.asset_paths):
        raise CompilationEvidenceError(
            "compilation-report-assets-mismatch",
            "G5 asset paths do not match the shared course contract",
        )


def compile_blueprint(
    data: dict,
    contract_validator: Optional[ContractValidator] = None,
) -> CompilationResult:
    # Compilation is also the bridge to the first renderer-backed preview.
    # An AI-authored draft may therefore compile before the teacher has seen it;
    # preview completion and publication approval remain separate hard gates.
    authoring_issues = validate_blueprint_authoring(data, require_approval=False)
    if authoring_issues:
        raise CompilationBlocked([_authoring_issue(issue) for issue in authoring_issues])

    document = project_course_definition(data)
    validator = contract_validator or validate_with_shared_contract
    contract_result = validator(document)
    if not contract_result.ok:
        raise CompilationBlocked(contract_result.issues)

    source_map = build_runtime_source_map(data, document)
    snapshot = _load_contract_snapshot()
    report = {
        "schemaVersion": "1.0",
        "status": "compiled",
        "authoringApproval": (
            "teacher-confirmed"
            if data.get("approval", {}).get("teacherConfirmed") is True
            else "ai-draft"
        ),
        "compilerVersion": COMPILER_VERSION,
        "blueprintHash": source_map["blueprintHash"],
        "courseDefinitionHash": source_map["courseDefinitionHash"],
        "sourceMapHash": canonical_json_hash(source_map),
        "compilerHash": file_sha256(Path(__file__)),
        "contractSnapshotHash": file_sha256(CONTRACT_SNAPSHOT),
        "assetPaths": sorted(contract_result.asset_paths),
        "contractSnapshot": {
            "packageName": snapshot["packageName"],
            "packageVersion": snapshot["packageVersion"],
            "upstreamCommit": snapshot["upstreamCommit"],
        },
        "issues": [],
    }
    return CompilationResult(document=document, source_map=source_map, report=report)


def write_compilation_outputs_atomic(
    root: Path,
    result: CompilationResult,
    *,
    replace: Callable[[Path, Path], None] = os.replace,
) -> None:
    root = root.resolve()
    outputs = (
        (root / "course" / "course.json", result.document),
        (
            root / ".course-work" / "course-runtime-source-map.json",
            result.source_map,
        ),
        (root / ".course-work" / "compilation-report.json", result.report),
    )
    staged: List[Path] = []
    backups = {}
    originally_present = {
        destination: destination.exists() for destination, _ in outputs
    }
    try:
        for destination, payload in outputs:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.parent.is_symlink() or destination.is_symlink():
                raise ValueError(f"Compilation output must not be a symlink: {destination}")
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.name}.",
                suffix=".tmp",
                dir=destination.parent,
            )
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(dump_json(payload))
                stream.flush()
                os.fsync(stream.fileno())
            staged.append(temporary)

        for destination, _ in outputs:
            if destination.exists():
                descriptor, backup_name = tempfile.mkstemp(
                    prefix=f".{destination.name}.",
                    suffix=".bak",
                    dir=destination.parent,
                )
                os.close(descriptor)
                backup = Path(backup_name)
                shutil.copy2(destination, backup)
                backups[destination] = backup

        for (destination, _), temporary in zip(outputs, staged):
            replace(temporary, destination)
    except Exception:
        for destination, _ in outputs:
            backup = backups.get(destination)
            if backup is not None and backup.exists():
                os.replace(backup, destination)
            elif not originally_present.get(destination, False) and destination.exists():
                destination.unlink()
        raise
    finally:
        for temporary in staged:
            if temporary.exists():
                temporary.unlink()
        for backup in backups.values():
            if backup.exists():
                backup.unlink()
