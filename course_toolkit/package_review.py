from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .course_validation import validate_course_data
from .coverage import (
    validate_coverage,
    validate_coverage_inventory,
    validate_decisions,
    validate_session,
    validate_unresolved,
)
from .errors import ValidationIssue
from .html_validation import validate_interactive_html
from .index_renderer import render_index
from .jsonio import load_json
from .paths import resolve_course_path, validate_referenced_paths
from .video_interactions import (
    render_video_interactions,
    validate_video_interactions,
)


REPAIRABLE_CODES = {"generated-view-drift"}


@dataclass(frozen=True)
class ReviewResult:
    status: str
    issues: Tuple[ValidationIssue, ...]
    warnings: Tuple[ValidationIssue, ...]

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "issues": [issue.as_dict() for issue in self.issues],
            "warnings": [warning.as_dict() for warning in self.warnings],
        }


def _prefixed(prefix: str, issues: Iterable[ValidationIssue]) -> List[ValidationIssue]:
    return [
        ValidationIssue(
            f"{prefix}:{issue.path}",
            issue.code,
            issue.message,
        )
        for issue in issues
    ]


def _blocks(data: dict) -> Iterable[dict]:
    for part in data.get("course", {}).get("parts", []):
        if not isinstance(part, dict):
            continue
        for piece in part.get("pieces", []):
            if not isinstance(piece, dict):
                continue
            for block in piece.get("blocks", []):
                if isinstance(block, dict):
                    yield block


def _compare_generated(
    path: Path,
    expected: str,
    label: str,
) -> List[ValidationIssue]:
    if not path.is_file():
        return [ValidationIssue(label, "missing-file", f"generated file is missing: {path}")]
    try:
        actual = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [ValidationIssue(label, "unreadable-file", str(exc))]
    if actual != expected:
        return [
            ValidationIssue(
                label,
                "generated-view-drift",
                f"{path.name} differs from canonical JSON",
            )
        ]
    return []


def _validate_linked_media(course_root: Path, data: dict) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    for block in _blocks(data):
        block_id = str(block.get("id", "unknown"))
        if block.get("type") == "interactiveHtml" and isinstance(block.get("source"), str):
            try:
                path = resolve_course_path(course_root, block["source"])
            except ValueError:
                continue
            if path.is_file():
                issues.extend(
                    _prefixed(
                        f"html[{block_id}]",
                        validate_interactive_html(path),
                    )
                )
        if block.get("type") != "video":
            continue
        interaction = block.get("interaction")
        if not isinstance(interaction, dict):
            continue
        data_path_raw = interaction.get("data")
        document_path_raw = interaction.get("document")
        if not isinstance(data_path_raw, str) or not isinstance(document_path_raw, str):
            continue
        try:
            data_path = resolve_course_path(course_root, data_path_raw)
            document_path = resolve_course_path(course_root, document_path_raw)
        except ValueError:
            continue
        if not data_path.is_file():
            continue
        try:
            interaction_data = load_json(data_path)
        except ValueError as exc:
            issues.append(
                ValidationIssue(
                    data_path_raw,
                    "invalid-json",
                    str(exc),
                )
            )
            continue
        issues.extend(
            _prefixed(
                f"video[{block_id}]",
                validate_video_interactions(interaction_data, course_root),
            )
        )
        if isinstance(interaction_data, dict):
            try:
                expected = render_video_interactions(interaction_data)
            except (KeyError, TypeError, ValueError):
                continue
            issues.extend(
                _compare_generated(
                    document_path,
                    expected,
                    document_path_raw,
                )
            )
    return issues


def _course_destinations(data: Optional[dict]) -> Optional[set]:
    if data is None:
        return None
    destinations = set()
    for part in data.get("course", {}).get("parts", []):
        if not isinstance(part, dict):
            continue
        part_id = part.get("id")
        for piece in part.get("pieces", []):
            if not isinstance(piece, dict):
                continue
            piece_id = piece.get("id")
            for block in piece.get("blocks", []):
                if (
                    isinstance(block, dict)
                    and isinstance(part_id, str)
                    and isinstance(piece_id, str)
                    and isinstance(block.get("id"), str)
                ):
                    destinations.add(f"{part_id}/{piece_id}/{block['id']}")
    return destinations


def _validate_work_records(
    work_root: Path,
    course_data: Optional[dict],
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    extracted_path = work_root / "materials-extracted.json"
    coverage_path = work_root / "source-coverage.json"
    decisions_path = work_root / "decisions.json"
    unresolved_path = work_root / "unresolved.json"
    session_path = work_root / "session.json"
    loaded_records = {}
    for path in (
        extracted_path,
        coverage_path,
        decisions_path,
        unresolved_path,
        session_path,
    ):
        if not path.is_file():
            issues.append(
                ValidationIssue(
                    path.name,
                    "missing-file",
                    f"work record is required: {path.name}",
                )
            )
            continue
        try:
            loaded_records[path.name] = load_json(path)
        except ValueError as exc:
            issues.append(ValidationIssue(path.name, "invalid-json", str(exc)))
    coverage = loaded_records.get("source-coverage.json")
    if coverage is not None:
        issues.extend(
            _prefixed(
                "source-coverage.json",
                validate_coverage(
                    coverage,
                    _course_destinations(course_data),
                ),
            )
        )
    decisions = loaded_records.get("decisions.json")
    if decisions is not None:
        issues.extend(
            _prefixed(
                "decisions.json",
                validate_decisions(decisions),
            )
        )
    unresolved = loaded_records.get("unresolved.json")
    if unresolved is not None:
        issues.extend(
            _prefixed(
                "unresolved.json",
                validate_unresolved(unresolved),
            )
        )
    session = loaded_records.get("session.json")
    if session is not None:
        issues.extend(
            _prefixed(
                "session.json",
                validate_session(session),
            )
        )
    extracted = loaded_records.get("materials-extracted.json")
    if extracted is not None and coverage is not None:
        issues.extend(validate_coverage_inventory(extracted, coverage))
    return issues


def _classify(issues: List[ValidationIssue]) -> str:
    if not issues:
        return "uploadable"
    if all(issue.code in REPAIRABLE_CODES for issue in issues):
        return "uploadable-after-fixes"
    return "blocked"


def review_package(
    course_root: Path,
    work_root: Optional[Path] = None,
) -> ReviewResult:
    issues: List[ValidationIssue] = []
    course_path = course_root / "course.json"
    data: Optional[dict] = None
    if not course_path.is_file():
        issues.append(
            ValidationIssue(
                "course.json",
                "missing-file",
                "course.json is required",
            )
        )
    else:
        try:
            loaded = load_json(course_path)
        except ValueError as exc:
            issues.append(ValidationIssue("course.json", "invalid-json", str(exc)))
        else:
            structure_issues = validate_course_data(loaded)
            issues.extend(structure_issues)
            if isinstance(loaded, dict):
                data = loaded
                issues.extend(validate_referenced_paths(course_root, data))
                if not structure_issues:
                    issues.extend(
                        _compare_generated(
                            course_root / "index.md",
                            render_index(data),
                            "index.md",
                        )
                    )
                    issues.extend(_validate_linked_media(course_root, data))
    if work_root is not None:
        issues.extend(_validate_work_records(work_root, data))

    ordered = tuple(
        sorted(issues, key=lambda issue: (issue.path, issue.code, issue.message))
    )
    return ReviewResult(
        status=_classify(list(ordered)),
        issues=ordered,
        warnings=(),
    )
