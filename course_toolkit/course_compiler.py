import hashlib
import json
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


COMPILER_VERSION = "1.0"
ROOT = Path(__file__).resolve().parent.parent
CONTRACT_SNAPSHOT = ROOT / "course-contract.snapshot.json"
CONTRACT_VALIDATOR = ROOT / "scripts" / "validate-course-definition.ts"


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


ContractValidator = Callable[[dict], SharedContractResult]


def canonical_json_hash(data: object) -> str:
    encoded = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
                [
                    "node",
                    "--import",
                    "tsx",
                    str(CONTRACT_VALIDATOR),
                    str(input_path),
                    "--json",
                ],
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


def compile_blueprint(
    data: dict,
    contract_validator: Optional[ContractValidator] = None,
) -> CompilationResult:
    authoring_issues = validate_blueprint_authoring(data, require_approval=True)
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
        "compilerVersion": COMPILER_VERSION,
        "blueprintHash": source_map["blueprintHash"],
        "courseDefinitionHash": source_map["courseDefinitionHash"],
        "sourceMapHash": canonical_json_hash(source_map),
        "assetPaths": sorted(contract_result.asset_paths),
        "contractSnapshot": {
            "packageName": snapshot["packageName"],
            "packageVersion": snapshot["packageVersion"],
            "upstreamCommit": snapshot["upstreamCommit"],
        },
        "issues": [],
    }
    return CompilationResult(document=document, source_map=source_map, report=report)
