import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from course_toolkit.course_compiler import (
    canonical_json_hash,
    file_sha256,
)
from course_toolkit.errors import ValidationIssue
from course_toolkit.html_validation import validate_interactive_html_v2
from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.pdf_validation import validate_pdf_file
from course_toolkit.video_interactions import inspect_video_file


ROLE_EXTENSIONS = {
    "opening-audio": {".mp3", ".m4a", ".aac", ".ogg", ".wav"},
    "closing-audio": {".mp3", ".m4a", ".aac", ".ogg", ".wav"},
    "narration-audio": {".mp3", ".m4a", ".aac", ".ogg", ".wav"},
    "image": {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"},
    "pdf": {".pdf"},
    "video": {".mp4"},
    "video-poster": {".png", ".jpg", ".jpeg", ".webp"},
    "captions": {".vtt"},
    "video-interaction": {".json"},
    "interactive-html": {".html"},
}
TTS_OUTPUT_ROLES = frozenset(
    {"opening-audio", "closing-audio", "narration-audio"}
)
VALIDATOR_VERSION = "1.0"
VALIDATION_REPORT_RELATIVE_PATH = Path(".course-work/course-validation-report.json")
VALIDATION_ATTEMPT_RELATIVE_PATH = Path(".course-work/course-validation-attempt.json")
ROOT = Path(__file__).resolve().parent.parent
VIDEO_INTERACTION_VALIDATOR = (
    ROOT / "course_toolkit" / "runtime_dist" / "validate-video-interaction.mjs"
)
VALIDATOR_ARTIFACTS = (
    ROOT / "course_toolkit" / "course_package_validation.py",
    ROOT / "course_toolkit" / "html_validation.py",
    ROOT / "course_toolkit" / "mp4.py",
    ROOT / "course_toolkit" / "pdf_validation.py",
    ROOT / "course_toolkit" / "video_interactions.py",
    VIDEO_INTERACTION_VALIDATOR,
)


@dataclass(frozen=True)
class AssetReference:
    runtime_path: str
    source: str
    role: str
    part_id: Optional[str] = None
    slice_id: Optional[str] = None
    block_id: Optional[str] = None
    narration_id: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "runtimePath": self.runtime_path,
            "source": self.source,
            "role": self.role,
            "partId": self.part_id,
            "sliceId": self.slice_id,
            "blockId": self.block_id,
            "narrationId": self.narration_id,
        }


@dataclass(frozen=True)
class AssetValidationResult:
    references: Tuple[AssetReference, ...]
    issues: Tuple[ValidationIssue, ...]


def _reference(
    runtime_path: str,
    source: object,
    role: str,
    *,
    part_id: Optional[str] = None,
    slice_id: Optional[str] = None,
    block_id: Optional[str] = None,
    narration_id: Optional[str] = None,
) -> Optional[AssetReference]:
    if not isinstance(source, str) or not source:
        return None
    return AssetReference(
        runtime_path=runtime_path,
        source=source,
        role=role,
        part_id=part_id,
        slice_id=slice_id,
        block_id=block_id,
        narration_id=narration_id,
    )


def iter_asset_references(document: object) -> Iterable[AssetReference]:
    if not isinstance(document, dict):
        return
    course = document.get("course")
    if not isinstance(course, dict):
        return
    opening = course.get("opening")
    if isinstance(opening, dict) and isinstance(opening.get("fallback"), dict):
        reference = _reference(
            "course.opening.fallback.audio",
            opening["fallback"].get("audio"),
            "opening-audio",
        )
        if reference:
            yield reference
    closing = course.get("closing")
    if isinstance(closing, dict) and isinstance(closing.get("fallback"), dict):
        reference = _reference(
            "course.closing.fallback.audio",
            closing["fallback"].get("audio"),
            "closing-audio",
        )
        if reference:
            yield reference

    for part_index, part in enumerate(course.get("parts", [])):
        if not isinstance(part, dict):
            continue
        part_id = part.get("id") if isinstance(part.get("id"), str) else None
        for slice_index, slice_data in enumerate(part.get("slices", [])):
            if not isinstance(slice_data, dict):
                continue
            slice_id = (
                slice_data.get("id") if isinstance(slice_data.get("id"), str) else None
            )
            slice_path = f"course.parts[{part_index}].slices[{slice_index}]"
            for narration_index, narration in enumerate(
                slice_data.get("narrations", [])
            ):
                if not isinstance(narration, dict):
                    continue
                narration_id = (
                    narration.get("id")
                    if isinstance(narration.get("id"), str)
                    else None
                )
                reference = _reference(
                    f"{slice_path}.narrations[{narration_index}].audio",
                    narration.get("audio"),
                    "narration-audio",
                    part_id=part_id,
                    slice_id=slice_id,
                    narration_id=narration_id,
                )
                if reference:
                    yield reference

            for block_index, block in enumerate(slice_data.get("blocks", [])):
                if not isinstance(block, dict):
                    continue
                block_id = block.get("id") if isinstance(block.get("id"), str) else None
                block_path = f"{slice_path}.blocks[{block_index}]"
                block_type = block.get("type")
                common = {
                    "part_id": part_id,
                    "slice_id": slice_id,
                    "block_id": block_id,
                }
                if block_type == "images":
                    for item_index, item in enumerate(block.get("items", [])):
                        if not isinstance(item, dict):
                            continue
                        reference = _reference(
                            f"{block_path}.items[{item_index}].source",
                            item.get("source"),
                            "image",
                            **common,
                        )
                        if reference:
                            yield reference
                    continue
                role = {
                    "pdf": "pdf",
                    "video": "video",
                    "interactiveHtml": "interactive-html",
                }.get(block_type)
                if role:
                    reference = _reference(
                        f"{block_path}.source",
                        block.get("source"),
                        role,
                        **common,
                    )
                    if reference:
                        yield reference
                if block_type != "video":
                    continue
                for field, video_role in (
                    ("poster", "video-poster"),
                    ("captions", "captions"),
                ):
                    reference = _reference(
                        f"{block_path}.{field}",
                        block.get(field),
                        video_role,
                        **common,
                    )
                    if reference:
                        yield reference
                interaction = block.get("interaction")
                if isinstance(interaction, dict):
                    reference = _reference(
                        f"{block_path}.interaction.source",
                        interaction.get("source"),
                        "video-interaction",
                        **common,
                    )
                    if reference:
                        yield reference


def _unsafe_source(source: str) -> bool:
    candidate = Path(source)
    return (
        candidate.is_absolute()
        or "\\" in source
        or ".." in candidate.parts
        or "." in candidate.parts
        or any(not part for part in source.split("/"))
        or bool(re.match(r"^[a-z][a-z0-9+.-]*://", source, re.I))
    )


def _case_variant(parent: Path, name: str) -> Optional[str]:
    try:
        names = sorted(entry.name for entry in parent.iterdir())
    except OSError:
        return None
    return next(
        (candidate for candidate in names if candidate.casefold() == name.casefold()),
        None,
    )


def _resolve_asset(root: Path, reference: AssetReference) -> Tuple[Optional[Path], Optional[ValidationIssue]]:
    if _unsafe_source(reference.source):
        return None, ValidationIssue(
            reference.runtime_path,
            "unsafe-asset-path",
            f"asset path must be a safe relative path: {reference.source}",
        )
    current = root
    for part in Path(reference.source).parts:
        if current.is_symlink():
            return None, ValidationIssue(
                reference.runtime_path,
                "symlink-asset-path",
                f"asset path traverses a symlink: {reference.source}",
            )
        exact = current / part
        variant = _case_variant(current, part)
        if variant is not None and variant != part:
            return None, ValidationIssue(
                reference.runtime_path,
                "asset-case-mismatch",
                f"asset path case differs on disk: expected {part}, found {variant}",
            )
        if exact.exists() or exact.is_symlink():
            current = exact
            continue
        if variant is not None:
            return None, ValidationIssue(
                reference.runtime_path,
                "asset-case-mismatch",
                f"asset path case differs on disk: expected {part}, found {variant}",
            )
        return None, ValidationIssue(
            reference.runtime_path,
            "missing-asset",
            f"referenced asset does not exist: {reference.source}",
        )
    if current.is_symlink():
        return None, ValidationIssue(
            reference.runtime_path,
            "symlink-asset-path",
            f"asset path resolves to a symlink: {reference.source}",
        )
    if not current.is_file():
        return None, ValidationIssue(
            reference.runtime_path,
            "missing-asset",
            f"referenced asset is not a file: {reference.source}",
        )
    return current, None


def validate_asset_references(
    course_root: Path,
    document: object,
    expected_asset_paths: Sequence[str],
) -> AssetValidationResult:
    references = tuple(iter_asset_references(document))
    issues: List[ValidationIssue] = []
    generated_paths = {
        reference.source
        for reference in references
        if reference.role in TTS_OUTPUT_ROLES
    }
    actual_paths = sorted(
        {
            reference.source
            for reference in references
            if reference.role not in TTS_OUTPUT_ROLES
        }
    )
    expected_paths = sorted(set(expected_asset_paths).difference(generated_paths))
    for source in sorted(set(actual_paths).difference(expected_paths)):
        issues.append(
            ValidationIssue(
                "assetPaths",
                "asset-inventory-mismatch",
                f"definition asset is absent from compilation report: {source}",
            )
        )
    for source in sorted(set(expected_paths).difference(actual_paths)):
        issues.append(
            ValidationIssue(
                "assetPaths",
                "asset-inventory-mismatch",
                f"compilation report asset is not referenced by definition: {source}",
            )
        )

    if course_root.is_symlink():
        issues.append(
            ValidationIssue(
                "$",
                "symlink-asset-path",
                "course root must not be a symlink",
            )
        )
        return AssetValidationResult(references, tuple(issues))
    root = course_root.resolve()
    for reference in references:
        allowed = ROLE_EXTENSIONS[reference.role]
        suffix = Path(reference.source).suffix.lower()
        if suffix not in allowed:
            issues.append(
                ValidationIssue(
                    reference.runtime_path,
                    "asset-extension-mismatch",
                    f"{reference.role} requires one of {sorted(allowed)}: {reference.source}",
                )
            )
        if reference.role in TTS_OUTPUT_ROLES:
            path_issue = (
                ValidationIssue(
                    reference.runtime_path,
                    "unsafe-asset-path",
                    f"TTS output path must be a safe relative path: {reference.source}",
                )
                if _unsafe_source(reference.source)
                else None
            )
        else:
            _, path_issue = _resolve_asset(root, reference)
        if path_issue:
            issues.append(path_issue)
    return AssetValidationResult(references, tuple(issues))


class PackageValidationToolError(RuntimeError):
    pass


def validator_code_hash() -> str:
    files = list(VALIDATOR_ARTIFACTS)
    files.extend(
        path
        for path in (ROOT / "packages" / "course-contract" / "src").rglob("*.ts")
        if path.is_file()
    )
    evidence = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": file_sha256(path),
        }
        for path in sorted(files)
    ]
    return canonical_json_hash(evidence)


def _blocks(document: dict) -> Iterable[Tuple[str, str, dict]]:
    for part in document.get("course", {}).get("parts", []):
        if not isinstance(part, dict):
            continue
        for slice_data in part.get("slices", []):
            if not isinstance(slice_data, dict):
                continue
            slice_id = str(slice_data.get("id", "unknown"))
            for block in slice_data.get("blocks", []):
                if isinstance(block, dict):
                    yield str(block.get("id", "unknown")), slice_id, block


def _video_interaction_contract_issues(document: dict, owner: dict) -> List[ValidationIssue]:
    with tempfile.TemporaryDirectory(prefix="video-interaction-") as temporary:
        temporary_root = Path(temporary)
        document_path = temporary_root / "interaction.json"
        owner_path = temporary_root / "owner.json"
        document_path.write_text(json.dumps(document), encoding="utf-8")
        owner_path.write_text(json.dumps(owner), encoding="utf-8")
        try:
            completed = subprocess.run(
                [
                    "node",
                    str(VIDEO_INTERACTION_VALIDATOR),
                    str(document_path),
                    str(owner_path),
                    "--json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            raise PackageValidationToolError(
                f"Cannot run shared video interaction validator: {exc}"
            ) from exc
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        raise PackageValidationToolError(
            f"Shared video interaction validator returned unreadable output: {detail}"
        ) from exc
    if completed.returncode == 0 and payload.get("ok") is True:
        return []
    if completed.returncode == 2 and payload.get("ok") is False:
        return [
            ValidationIssue(
                str(issue.get("path", "")),
                "video-interaction-contract-invalid",
                str(issue.get("message", "invalid video interaction")),
            )
            for issue in payload.get("issues", [])
            if isinstance(issue, dict)
        ]
    detail = payload.get("error") if isinstance(payload, dict) else None
    raise PackageValidationToolError(
        f"Shared video interaction validator failed: {detail or completed.returncode}"
    )


def _prefix(prefix: str, issues: Iterable[ValidationIssue]) -> List[ValidationIssue]:
    prefixed = []
    for issue in issues:
        suffix = issue.path
        if suffix == "$" or Path(suffix).is_absolute():
            path = prefix
        else:
            path = f"{prefix}:{suffix}"
        prefixed.append(ValidationIssue(path, issue.code, issue.message))
    return prefixed


def _asset_evidence(root: Path, references: Sequence[AssetReference]) -> List[dict]:
    grouped: Dict[str, List[AssetReference]] = {}
    for reference in references:
        if reference.role in TTS_OUTPUT_ROLES:
            continue
        grouped.setdefault(reference.source, []).append(reference)
    evidence = []
    for source in sorted(grouped):
        path = root / source
        safe_file = (
            not _unsafe_source(source)
            and path.is_file()
            and not path.is_symlink()
            and not any((root / Path(*Path(source).parts[:index])).is_symlink() for index in range(1, len(Path(source).parts)))
        )
        evidence.append(
            {
                "source": source,
                "roles": sorted({item.role for item in grouped[source]}),
                "runtimePaths": sorted(item.runtime_path for item in grouped[source]),
                "sha256": file_sha256(path) if safe_file else None,
                "sizeBytes": path.stat().st_size if safe_file else None,
            }
        )
    return evidence


def _specialized_asset_findings(
    root: Path,
    document: dict,
    references: Sequence[AssetReference],
    asset_issues: Sequence[ValidationIssue],
) -> Tuple[List[ValidationIssue], List[ValidationIssue]]:
    issues: List[ValidationIssue] = []
    warnings: List[ValidationIssue] = []
    invalid_paths = {
        issue.path
        for issue in asset_issues
        if issue.code
        in {
            "unsafe-asset-path",
            "symlink-asset-path",
            "missing-asset",
            "asset-case-mismatch",
            "asset-extension-mismatch",
        }
    }
    refs_by_role: Dict[str, List[AssetReference]] = {}
    for reference in references:
        refs_by_role.setdefault(reference.role, []).append(reference)
        if reference.runtime_path in invalid_paths:
            continue
        path = root / reference.source
        if reference.role == "pdf":
            issues.extend(_prefix(reference.runtime_path, validate_pdf_file(path)))
        elif reference.role == "interactive-html":
            issues.extend(
                _prefix(reference.runtime_path, validate_interactive_html_v2(path))
            )
        elif reference.role == "captions":
            try:
                prefix = path.read_text(encoding="utf-8-sig")[:32]
            except (OSError, UnicodeError) as exc:
                issues.append(
                    ValidationIssue(
                        reference.runtime_path,
                        "unreadable-caption",
                        str(exc),
                    )
                )
            else:
                if not prefix.startswith("WEBVTT"):
                    issues.append(
                        ValidationIssue(
                            reference.runtime_path,
                            "invalid-webvtt",
                            "caption file must start with WEBVTT",
                        )
                    )

    interaction_by_block = {
        reference.block_id: reference
        for reference in refs_by_role.get("video-interaction", [])
        if reference.block_id
    }
    video_ref_by_block = {
        reference.block_id: reference
        for reference in refs_by_role.get("video", [])
        if reference.block_id
    }
    for block_id, _, block in _blocks(document):
        if block.get("type") != "video":
            continue
        video_reference = video_ref_by_block.get(block_id)
        if video_reference is None or video_reference.runtime_path in invalid_paths:
            continue
        interaction_reference = interaction_by_block.get(block_id)
        interaction_document = None
        cue_times: List[float] = []
        required_cues = []
        if interaction_reference is not None and interaction_reference.runtime_path not in invalid_paths:
            interaction_path = root / interaction_reference.source
            try:
                interaction_document = load_json(interaction_path)
            except ValueError as exc:
                issues.append(
                    ValidationIssue(
                        interaction_reference.runtime_path,
                        "invalid-video-interaction-json",
                        str(exc),
                    )
                )
            else:
                issues.extend(
                    _prefix(
                        interaction_reference.runtime_path,
                        _video_interaction_contract_issues(interaction_document, block),
                    )
                )
                video_data = interaction_document.get("video") if isinstance(interaction_document, dict) else None
                cues = video_data.get("cues", []) if isinstance(video_data, dict) else []
                if isinstance(cues, list):
                    cue_times = [
                        float(cue["atSeconds"])
                        for cue in cues
                        if isinstance(cue, dict)
                        and isinstance(cue.get("atSeconds"), (int, float))
                        and not isinstance(cue.get("atSeconds"), bool)
                    ]
                    required_cues = [
                        cue
                        for cue in cues
                        if isinstance(cue, dict) and cue.get("required") is True
                    ]
        if required_cues and block.get("completion", {}).get("rule") != "video-ended-and-interactions-completed":
            issues.append(
                ValidationIssue(
                    video_reference.runtime_path,
                    "video-completion-inconsistent",
                    "required video cues require video-ended-and-interactions-completed",
                )
            )
        media_result = inspect_video_file(
            root / video_reference.source,
            video_reference.source,
            cue_times,
        )
        issues.extend(_prefix(video_reference.runtime_path, media_result.issues))
        warnings.extend(_prefix(video_reference.runtime_path, media_result.warnings))
        if media_result.profile is None:
            continue
        actual_duration = media_result.profile.duration_seconds
        declared_duration = block.get("durationSeconds")
        if isinstance(declared_duration, (int, float)) and not isinstance(declared_duration, bool):
            if abs(float(declared_duration) - actual_duration) > 1:
                issues.append(
                    ValidationIssue(
                        video_reference.runtime_path,
                        "video-duration-mismatch",
                        "Video Block durationSeconds differs from the actual MP4 duration",
                    )
                )
        if isinstance(interaction_document, dict):
            video_data = interaction_document.get("video")
            interaction_duration = video_data.get("durationSeconds") if isinstance(video_data, dict) else None
            if isinstance(interaction_duration, (int, float)) and not isinstance(interaction_duration, bool):
                if abs(float(interaction_duration) - actual_duration) > 1:
                    issues.append(
                        ValidationIssue(
                            interaction_reference.runtime_path if interaction_reference else video_reference.runtime_path,
                            "video-interaction-duration-mismatch",
                            "interaction durationSeconds differs from the actual MP4 duration",
                        )
                    )
            for cue_time in cue_times:
                if cue_time >= actual_duration:
                    issues.append(
                        ValidationIssue(
                            interaction_reference.runtime_path if interaction_reference else video_reference.runtime_path,
                            "video-cue-out-of-range",
                            f"cue at {cue_time:g}s is outside the actual MP4 duration",
                        )
                    )
    return issues, warnings


def _completeness_findings(document: dict) -> List[ValidationIssue]:
    warnings: List[ValidationIssue] = []
    total_seconds = 0.0
    for part_index, part in enumerate(document.get("course", {}).get("parts", [])):
        for slice_index, slice_data in enumerate(part.get("slices", [])):
            total_seconds += float(slice_data.get("estimatedSeconds", 0))
            blocks = slice_data.get("blocks", [])
            if isinstance(blocks, list) and len(blocks) > 4:
                warnings.append(
                    ValidationIssue(
                        f"course.parts[{part_index}].slices[{slice_index}].blocks",
                        "dense-slice",
                        f"Slice has {len(blocks)} Blocks; review one-screen density in preview",
                    )
                )
    estimated_minutes = document.get("course", {}).get("estimatedMinutes")
    if isinstance(estimated_minutes, (int, float)) and not isinstance(estimated_minutes, bool):
        course_seconds = float(estimated_minutes) * 60
        tolerance = max(60.0, total_seconds * 0.25)
        if abs(course_seconds - total_seconds) > tolerance:
            warnings.append(
                ValidationIssue(
                    "course.estimatedMinutes",
                    "estimated-time-drift",
                    "course estimatedMinutes differs materially from the Slice total",
                )
            )
    return warnings


def _media_evidence(root: Path, document: dict) -> dict:
    evidence = {"videos": [], "html": [], "pdfs": []}
    for block_id, _, block in _blocks(document):
        block_type = block.get("type")
        source = block.get("source")
        if not isinstance(source, str):
            continue
        if block_type == "pdf":
            evidence["pdfs"].append({"blockId": block_id, "source": source})
        elif block_type == "interactiveHtml":
            evidence["html"].append(
                {
                    "blockId": block_id,
                    "source": source,
                    "protocolVersion": block.get("protocolVersion"),
                    "completionRule": block.get("completion", {}).get("rule"),
                }
            )
        elif block_type == "video":
            cues = []
            interaction = block.get("interaction")
            if isinstance(interaction, dict) and isinstance(interaction.get("source"), str):
                try:
                    interaction_document = load_json(root / interaction["source"])
                except ValueError:
                    interaction_document = None
                if isinstance(interaction_document, dict):
                    video_data = interaction_document.get("video")
                    if isinstance(video_data, dict) and isinstance(video_data.get("cues"), list):
                        cues = [cue for cue in video_data["cues"] if isinstance(cue, dict)]
            evidence["videos"].append(
                {
                    "blockId": block_id,
                    "source": source,
                    "completionRule": block.get("completion", {}).get("rule"),
                    "cueCount": len(cues),
                    "requiredCueCount": sum(cue.get("required") is True for cue in cues),
                    "autoPauseCueCount": sum(cue.get("pauseVideo") is True for cue in cues),
                }
            )
    return evidence


def build_course_validation_report(root: Path) -> dict:
    from course_toolkit.workflow import verify_g5_compilation

    root = root.resolve()
    delivery_root = root / "course"
    verify_g5_compilation(root)
    document = load_json(root / "course/course.json")
    compilation_report = load_json(root / ".course-work/compilation-report.json")
    asset_result = validate_asset_references(
        delivery_root,
        document,
        compilation_report.get("assetPaths", []),
    )
    issues = list(asset_result.issues)
    specialized_issues, warnings = _specialized_asset_findings(
        delivery_root,
        document,
        asset_result.references,
        asset_result.issues,
    )
    issues.extend(specialized_issues)
    warnings.extend(_completeness_findings(document))
    assets = _asset_evidence(delivery_root, asset_result.references)
    part_count = len(document["course"]["parts"])
    slices = [
        slice_data
        for part in document["course"]["parts"]
        for slice_data in part["slices"]
    ]
    validator_hash = validator_code_hash()
    return {
        "schemaVersion": "1.0",
        "validatorVersion": VALIDATOR_VERSION,
        "status": "blocked" if issues else "warnings" if warnings else "clear",
        "blueprintHash": compilation_report["blueprintHash"],
        "courseDefinitionHash": compilation_report["courseDefinitionHash"],
        "compilationReportHash": canonical_json_hash(compilation_report),
        "validatorHash": validator_hash,
        "assetSetHash": canonical_json_hash(assets),
        "summary": {
            "partCount": part_count,
            "sliceCount": len(slices),
            "blockCount": sum(len(slice_data["blocks"]) for slice_data in slices),
            "assetCount": len(assets),
        },
        "assets": assets,
        "mediaEvidence": _media_evidence(delivery_root, document),
        "issues": [issue.as_dict() for issue in issues],
        "warnings": [warning.as_dict() for warning in warnings],
        "browserCheckRequired": True,
    }


def write_current_validation_report(root: Path, report: dict) -> Path:
    relative = (
        VALIDATION_ATTEMPT_RELATIVE_PATH
        if report.get("status") == "blocked"
        else VALIDATION_REPORT_RELATIVE_PATH
    )
    path = root.resolve() / relative
    write_json_atomic(path, report)
    return path


def _workflow_issue_code(finding: dict, *, warning: bool) -> str:
    if not warning:
        return "course-package-invalid"
    if finding.get("code") == "dense-slice":
        return "course-package-density-warning"
    if finding.get("code") == "estimated-time-drift":
        return "course-package-estimate-warning"
    return "course-package-media-warning"


def validation_issue_candidates(report: dict, now: str):
    from course_toolkit.issues import make_registered_issue

    candidates = []
    evidence_path = (
        VALIDATION_ATTEMPT_RELATIVE_PATH
        if report.get("status") == "blocked"
        else VALIDATION_REPORT_RELATIVE_PATH
    ).as_posix()
    for field, warning in (("issues", False), ("warnings", True)):
        for finding in report.get(field, []):
            if not isinstance(finding, dict):
                continue
            target = {
                "path": str(finding.get("path", "")),
                "validationCode": str(finding.get("code", "unknown")),
            }
            candidate = make_registered_issue(
                code=_workflow_issue_code(finding, warning=warning),
                source="validator",
                message=str(finding.get("message", "Course package validation failed")),
                seen_at=now,
                target=target,
                evidence=(evidence_path,),
                remediation=(
                    "Fix the reported package problem and run validation again."
                    if not warning
                    else "Review this warning in context before completing G6."
                ),
            )
            candidates.append(candidate)
    return tuple(candidates)


def sync_validation_issues(root: Path, report: dict, now: str) -> Tuple[str, ...]:
    from course_toolkit.issues import IssueStore

    root = root.resolve()
    store = IssueStore.load(root / ".course-work/issues.json")
    candidates = validation_issue_candidates(report, now)

    candidate_fingerprints = {candidate.fingerprint for candidate in candidates}
    existing_by_fingerprint = {issue.fingerprint: issue for issue in store.all()}
    for candidate in candidates:
        existing = existing_by_fingerprint.get(candidate.fingerprint)
        if existing is not None and existing.status in {"accepted", "dismissed"}:
            continue
        store.upsert(candidate)
    for issue in store.all():
        if (
            issue.source == "validator"
            and issue.gate_id == "G6"
            and issue.fingerprint not in candidate_fingerprints
            and issue.status != "resolved"
        ):
            store.resolve(issue.id, now)
    store.save()
    return tuple(
        issue.id
        for issue in store.all()
        if issue.source == "validator" and issue.gate_id == "G6" and issue.status == "active"
    )
