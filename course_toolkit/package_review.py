import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .course_validation import validate_course_data
from .course_design import (
    extracted_source_ids,
    render_review_report,
    render_storyboard,
    validate_audience_classification,
    validate_learner_facing_course,
    validate_review_report,
    validate_storyboard,
)
from .coverage import (
    validate_coverage,
    validate_coverage_inventory,
    validate_decisions,
    validate_session,
    validate_unresolved,
)
from .errors import ValidationIssue
from .html_validation import validate_interactive_html
from .html_reports import render_html_report, validate_html_report
from .index_renderer import render_index
from .jsonio import load_json, write_json_atomic
from .paths import resolve_course_path, validate_referenced_paths
from .video_interactions import (
    inspect_video_file,
    inspect_video_interactions,
    render_video_interactions,
)


REPAIRABLE_CODES = {"generated-view-drift"}


@dataclass(frozen=True)
class ReviewResult:
    status: str
    issues: Tuple[ValidationIssue, ...]
    warnings: Tuple[ValidationIssue, ...]
    media_evidence: dict

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "issues": [issue.as_dict() for issue in self.issues],
            "warnings": [warning.as_dict() for warning in self.warnings],
            "mediaEvidence": self.media_evidence,
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


def _validate_linked_media(
    course_root: Path,
    data: dict,
) -> Tuple[List[ValidationIssue], List[ValidationIssue]]:
    issues: List[ValidationIssue] = []
    warnings: List[ValidationIssue] = []
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
        source = block.get("source")
        if not isinstance(interaction, dict) and isinstance(source, str):
            try:
                video_path = resolve_course_path(course_root, source)
            except ValueError:
                video_path = None
            if video_path is not None and video_path.is_file():
                result = inspect_video_file(video_path, source)
                issues.extend(_prefixed(f"video[{block_id}]", result.issues))
                warnings.extend(_prefixed(f"video[{block_id}]", result.warnings))
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
        interaction_source = None
        if isinstance(interaction_data, dict):
            video_data = interaction_data.get("video")
            if isinstance(video_data, dict) and isinstance(video_data.get("source"), str):
                interaction_source = video_data["source"]
        if isinstance(source, str) and isinstance(interaction_source, str):
            try:
                block_video_path = resolve_course_path(course_root, source)
                interaction_video_path = resolve_course_path(
                    course_root,
                    interaction_source,
                )
            except ValueError:
                pass
            else:
                if block_video_path != interaction_video_path:
                    issues.append(
                        ValidationIssue(
                            f"video[{block_id}].source",
                            "video-source-mismatch",
                            "video Block source differs from interaction JSON video.source",
                        )
                    )
                    if block_video_path.is_file():
                        block_result = inspect_video_file(block_video_path, source)
                        issues.extend(
                            _prefixed(f"video[{block_id}]", block_result.issues)
                        )
                        warnings.extend(
                            _prefixed(f"video[{block_id}]", block_result.warnings)
                        )
        result = inspect_video_interactions(interaction_data, course_root)
        issues.extend(_prefixed(f"video[{block_id}]", result.issues))
        warnings.extend(_prefixed(f"video[{block_id}]", result.warnings))
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
    deduplicated_warnings = {
        (warning.path, warning.code, warning.message): warning for warning in warnings
    }
    return issues, list(deduplicated_warnings.values())


def _summarize_media(
    course_root: Path,
    data: Optional[dict],
    work_root: Optional[Path],
) -> dict:
    evidence = {"videos": [], "html": []}
    if data is None:
        return evidence
    for block in _blocks(data):
        block_id = block.get("id")
        source = block.get("source")
        if not isinstance(block_id, str) or not isinstance(source, str):
            continue
        try:
            path = resolve_course_path(course_root, source)
        except ValueError:
            continue
        if block.get("type") == "video" and path.is_file():
            event_times: List[float] = []
            interaction = block.get("interaction")
            if isinstance(interaction, dict) and isinstance(interaction.get("data"), str):
                try:
                    interaction_path = resolve_course_path(
                        course_root,
                        interaction["data"],
                    )
                    interaction_data = load_json(interaction_path)
                except ValueError:
                    interaction_data = None
                if isinstance(interaction_data, dict):
                    video_data = interaction_data.get("video")
                    if isinstance(video_data, dict):
                        for event in video_data.get("events", []):
                            if not isinstance(event, dict):
                                continue
                            event_time = event.get("timeSeconds")
                            if isinstance(event_time, (int, float)) and not isinstance(
                                event_time,
                                bool,
                            ):
                                event_times.append(float(event_time))
            result = inspect_video_file(path, source, event_times)
            profile = result.profile
            sorted_times = sorted(event_times)
            boundaries = [0.0] + sorted_times
            if profile is not None:
                boundaries.append(profile.duration_seconds)
            gaps = [right - left for left, right in zip(boundaries, boundaries[1:])]
            evidence["videos"].append(
                {
                    "blockId": block_id,
                    "source": source,
                    "container": "mp4" if profile is not None else "unverified",
                    "videoCodecs": list(profile.video_codecs) if profile else [],
                    "audioCodecs": list(profile.audio_codecs) if profile else [],
                    "faststart": profile.faststart if profile else None,
                    "durationSeconds": profile.duration_seconds if profile else None,
                    "sizeBytes": profile.size_bytes if profile else None,
                    "interactionCount": len(sorted_times),
                    "firstInteractionSeconds": sorted_times[0] if sorted_times else None,
                    "lastInteractionSeconds": sorted_times[-1] if sorted_times else None,
                    "maximumGapSeconds": max(gaps) if gaps else None,
                    "issues": [issue.code for issue in result.issues],
                    "warnings": [warning.code for warning in result.warnings],
                }
            )
        elif block.get("type") == "interactiveHtml" and path.is_file():
            report_json = (
                f"html-reports/{block_id}.json" if work_root is not None else None
            )
            report_markdown = (
                f"html-reports/{block_id}.md" if work_root is not None else None
            )
            report_status = None
            report_sha_matches = None
            if work_root is not None:
                report_path = work_root / "html-reports" / f"{block_id}.json"
                if report_path.is_file():
                    try:
                        report = load_json(report_path)
                    except ValueError:
                        report = None
                    if isinstance(report, dict):
                        report_status = report.get("finalStatus")
                        report_sha_matches = report.get("sha256") == hashlib.sha256(
                            path.read_bytes()
                        ).hexdigest()
            evidence["html"].append(
                {
                    "blockId": block_id,
                    "source": source,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "reportJson": report_json,
                    "reportMarkdown": report_markdown,
                    "reportStatus": report_status,
                    "reportShaMatches": report_sha_matches,
                    "staticIssueCodes": [
                        issue.code for issue in validate_interactive_html(path)
                    ],
                    "browserCheckRequired": True,
                }
            )
    return evidence


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
    course_root: Path,
    course_data: Optional[dict],
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    extracted_path = work_root / "materials-extracted.json"
    coverage_path = work_root / "source-coverage.json"
    decisions_path = work_root / "decisions.json"
    unresolved_path = work_root / "unresolved.json"
    session_path = work_root / "session.json"
    audience_path = work_root / "audience-classification.json"
    storyboard_path = work_root / "course-storyboard.json"
    storyboard_markdown_path = work_root / "course-storyboard.md"
    review_report_path = work_root / "review-report.json"
    review_markdown_path = work_root / "review-report.md"
    loaded_records = {}
    for path in (
        extracted_path,
        coverage_path,
        audience_path,
        storyboard_path,
        decisions_path,
        unresolved_path,
        session_path,
        review_report_path,
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
    audience = loaded_records.get("audience-classification.json")
    if audience is not None:
        audience_issues = validate_audience_classification(
            audience,
            extracted_source_ids(extracted),
        )
        issues.extend(_prefixed("audience-classification.json", audience_issues))
    storyboard = loaded_records.get("course-storyboard.json")
    if storyboard is not None:
        storyboard_issues = validate_storyboard(
            storyboard,
            course_data,
            extracted_source_ids(extracted) if extracted is not None else None,
        )
        issues.extend(_prefixed("course-storyboard.json", storyboard_issues))
        if not storyboard_issues:
            issues.extend(
                _compare_generated(
                    storyboard_markdown_path,
                    render_storyboard(storyboard),
                    storyboard_markdown_path.name,
                )
            )
    elif not storyboard_markdown_path.is_file():
        issues.append(
            ValidationIssue(
                storyboard_markdown_path.name,
                "missing-file",
                f"work record is required: {storyboard_markdown_path.name}",
            )
        )
    review_report = loaded_records.get("review-report.json")
    if review_report is not None:
        review_issues = validate_review_report(review_report, course_data)
        issues.extend(_prefixed("review-report.json", review_issues))
        if (
            isinstance(review_report, dict)
            and review_report.get("finalStatus") == "blocked"
            and not review_issues
        ):
            issues.append(
                ValidationIssue(
                    "review-report.json.finalStatus",
                    "part-review-blocked",
                    "the Part-level review report blocks upload",
                )
            )
        if not review_issues:
            issues.extend(
                _compare_generated(
                    review_markdown_path,
                    render_review_report(review_report),
                    review_markdown_path.name,
                )
            )
    elif not review_markdown_path.is_file():
        issues.append(
            ValidationIssue(
                review_markdown_path.name,
                "missing-file",
                f"work record is required: {review_markdown_path.name}",
            )
        )
    if course_data is not None:
        report_root = work_root / "html-reports"
        for block in _blocks(course_data):
            if block.get("type") != "interactiveHtml":
                continue
            block_id = block.get("id")
            source = block.get("source")
            if not isinstance(block_id, str) or not isinstance(source, str):
                continue
            json_path = report_root / f"{block_id}.json"
            markdown_path = report_root / f"{block_id}.md"
            if not json_path.is_file():
                issues.append(
                    ValidationIssue(
                        f"html-reports/{block_id}.json",
                        "missing-html-report",
                        f"full Review requires an HTML report for Block {block_id}",
                    )
                )
                if not markdown_path.is_file():
                    issues.append(
                        ValidationIssue(
                            f"html-reports/{block_id}.md",
                            "missing-html-report",
                            "full Review requires readable HTML report Markdown "
                            f"for Block {block_id}",
                        )
                    )
                continue
            try:
                report = load_json(json_path)
            except ValueError as exc:
                issues.append(
                    ValidationIssue(
                        f"html-reports/{block_id}.json",
                        "invalid-html-report",
                        str(exc),
                    )
                )
                continue
            try:
                html_path = resolve_course_path(course_root, source)
            except ValueError:
                continue
            issues.extend(
                _prefixed(
                    f"html-reports/{block_id}.json",
                    validate_html_report(report, block_id, source, html_path),
                )
            )
            if not markdown_path.is_file():
                issues.append(
                    ValidationIssue(
                        f"html-reports/{block_id}.md",
                        "missing-html-report",
                        f"full Review requires readable HTML report Markdown for Block {block_id}",
                    )
                )
            else:
                try:
                    markdown = markdown_path.read_text(encoding="utf-8")
                except (OSError, UnicodeError) as exc:
                    issues.append(
                        ValidationIssue(
                            f"html-reports/{block_id}.md",
                            "invalid-html-report",
                            str(exc),
                        )
                    )
                else:
                    if isinstance(report, dict) and markdown != render_html_report(report):
                        issues.append(
                            ValidationIssue(
                                f"html-reports/{block_id}.md",
                                "stale-html-report",
                                "HTML report Markdown differs from its JSON report",
                            )
                        )
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
    warnings: List[ValidationIssue] = []
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
                issues.extend(validate_learner_facing_course(data))
                issues.extend(validate_referenced_paths(course_root, data))
                if not structure_issues:
                    issues.extend(
                        _compare_generated(
                            course_root / "index.md",
                            render_index(data),
                            "index.md",
                        )
                    )
                    media_issues, media_warnings = _validate_linked_media(course_root, data)
                    issues.extend(media_issues)
                    warnings.extend(media_warnings)
                    if work_root is None and any(
                        block.get("type") == "interactiveHtml" for block in _blocks(data)
                    ):
                        warnings.append(
                            ValidationIssue(
                                "html-reports",
                                "html-report-unavailable",
                                "未提供作者工作区，无法核对持久化 HTML 报告；"
                                "静态合同已重新检查",
                            )
                        )
    if work_root is not None:
        issues.extend(_validate_work_records(work_root, course_root, data))

    ordered = tuple(
        sorted(issues, key=lambda issue: (issue.path, issue.code, issue.message))
    )
    ordered_warnings = tuple(
        sorted(warnings, key=lambda issue: (issue.path, issue.code, issue.message))
    )
    return ReviewResult(
        status=_classify(list(ordered)),
        issues=ordered,
        warnings=ordered_warnings,
        media_evidence=_summarize_media(course_root, data, work_root),
    )


# CourseDefinition 2.0 independent review. The legacy functions above remain
# available only for importing/reviewing older 1.1 packages.
V2_REVIEW_SCHEMA_VERSION = "2.0"
V2_REVIEW_RELATIVE_PATH = Path(".course-work/review-report.json")
V2_REVIEW_MARKDOWN_RELATIVE_PATH = Path(".course-work/review-report.md")
V2_PART_DIMENSIONS = (
    "instructionalGoalStructure",
    "contentCompleteness",
    "studentFacingPresentation",
    "modalityChoice",
    "practiceFeedback",
    "resourcesFormat",
)
V2_SLICE_CHECKS = (
    "contentPurpose",
    "layoutOneScreen",
    "workflowReachability",
    "interactionCompletion",
    "mediaBehavior",
)
V2_OVERALL_CHECKS = (
    "allPartsPass",
    "sourceClassificationCoverage",
    "teacherDecisions",
    "resourcesPresent",
    "courseContract",
    "objectiveEvidence",
    "layoutWorkflow",
    "pdf",
    "video",
    "html",
    "previewRuntime",
    "unresolved",
)
V2_WORK_EVIDENCE = (
    ".course-work/course-blueprint.json",
    ".course-work/source-coverage.json",
    ".course-work/decisions.json",
    ".course-work/unresolved.json",
)


class V2ReviewBlocked(ValueError):
    pass


def _review_item() -> dict:
    return {"status": "pending", "evidence": ""}


def _v2_definition_index(document: dict) -> tuple:
    parts = []
    blocks = {}
    for part in document["course"]["parts"]:
        slices = []
        for slice_data in part["slices"]:
            slices.append(slice_data)
            for block in slice_data["blocks"]:
                blocks[block["id"]] = {
                    "block": block,
                    "partId": part["id"],
                    "sliceId": slice_data["id"],
                }
        parts.append((part, slices))
    return parts, blocks


def _objective_records(document: dict, blocks: dict) -> List[dict]:
    records = []
    parts_by_objective = {}
    for part in document["course"]["parts"]:
        for objective_id in part["objectiveIds"]:
            parts_by_objective.setdefault(objective_id, set()).add(part["id"])
    for objective in document["course"]["objectives"]:
        evidence_ids = list(objective["evidenceBlockIds"])
        aligned_parts = parts_by_objective.get(objective["id"], set())
        if not evidence_ids:
            raise V2ReviewBlocked(f"objective has no learning evidence: {objective['id']}")
        for block_id in evidence_ids:
            record = blocks.get(block_id)
            if record is None or record["partId"] not in aligned_parts:
                raise V2ReviewBlocked(
                    f"objective evidence is outside its aligned Parts: {objective['id']}/{block_id}"
                )
            block = record["block"]
            result_bearing = block.get("type") in {"fillBlank", "singleChoice", "interactiveHtml"} or (
                block.get("type") == "video" and isinstance(block.get("interaction"), dict)
            )
            if not result_bearing:
                raise V2ReviewBlocked(
                    f"objective evidence does not collect a result: {objective['id']}/{block_id}"
                )
        records.append(
            {
                "objectiveId": objective["id"],
                "evidenceBlockIds": evidence_ids,
                "status": "pending",
                "evidence": "",
            }
        )
    return records


def _v2_work_hashes(root: Path) -> dict:
    from course_toolkit.course_compiler import canonical_json_hash
    from course_toolkit.workflow import hash_path

    hashes = {}
    for relative in V2_WORK_EVIDENCE:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise V2ReviewBlocked(f"independent review evidence is missing: {relative}")
        if relative == ".course-work/decisions.json":
            document = load_json(path)
            decisions = [
                item
                for item in document.get("decisions", [])
                if isinstance(item, dict) and item.get("id") != "decision-publication-preflight"
            ]
            hashes[relative] = canonical_json_hash(
                {"schemaVersion": document.get("schemaVersion"), "decisions": decisions}
            )
        else:
            hashes[relative] = hash_path(path)
    return hashes


def _pending_decision_or_unresolved(root: Path) -> Optional[str]:
    decisions = load_json(root / ".course-work/decisions.json")
    for decision in decisions.get("decisions", []):
        if isinstance(decision, dict) and decision.get("status") in {"pending", "invalidated"}:
            return f"pending teacher decision: {decision.get('id', 'unknown')}"
    unresolved = load_json(root / ".course-work/unresolved.json")
    for item in unresolved.get("items", []):
        if not isinstance(item, dict):
            continue
        if item.get("status", "open") not in {"resolved", "dismissed"} and item.get("blocking", True):
            return f"blocking unresolved item: {item.get('id', 'unknown')}"
    return None


def prepare_v2_review(root: Path) -> dict:
    from course_toolkit.course_compiler import canonical_json_hash
    from course_toolkit.preview_evidence import verify_g7_preview
    from course_toolkit.workflow import hash_path, verify_g6_validation

    root = root.resolve()
    verify_g6_validation(root)
    verify_g7_preview(root)
    document = load_json(root / "course/course.json")
    if document.get("schemaVersion") != "2.0":
        raise V2ReviewBlocked("independent review requires CourseDefinition schemaVersion 2.0")
    pending = _pending_decision_or_unresolved(root)
    if pending:
        raise V2ReviewBlocked(pending)
    parts, blocks = _v2_definition_index(document)
    validation_path = root / ".course-work/course-validation-report.json"
    preview_path = root / ".course-work/preview-manifest.json"
    return {
        "schemaVersion": V2_REVIEW_SCHEMA_VERSION,
        "courseDefinitionSchemaVersion": "2.0",
        "status": "needs-review",
        "courseId": document["course"]["id"],
        "definitionHash": canonical_json_hash(document),
        "validationReportHash": hash_path(validation_path),
        "previewManifestHash": hash_path(preview_path),
        "workEvidence": _v2_work_hashes(root),
        "parts": [
            {
                "partId": part["id"],
                "title": part["title"],
                "status": "pending",
                "dimensions": {name: _review_item() for name in V2_PART_DIMENSIONS},
                "slices": [
                    {
                        "sliceId": slice_data["id"],
                        "title": slice_data["title"],
                        "status": "pending",
                        "checks": {name: _review_item() for name in V2_SLICE_CHECKS},
                    }
                    for slice_data in slices
                ],
            }
            for part, slices in parts
        ],
        "objectives": _objective_records(document, blocks),
        "mediaEvidence": load_json(validation_path).get("mediaEvidence", {}),
        "overallChecks": {name: _review_item() for name in V2_OVERALL_CHECKS},
        "reviewedAt": None,
    }


def write_v2_review_report(root: Path, report: dict) -> Path:
    path = root.resolve() / V2_REVIEW_RELATIVE_PATH
    write_json_atomic(path, report)
    return path


def render_v2_review_report(report: dict) -> str:
    lines = [
        "# CourseDefinition 2.0 independent review",
        "",
        f"Status: **{report.get('status', 'unknown')}**",
        "",
        "## Part review",
        "",
        "| Part | Status | Dimensions |",
        "| --- | --- | --- |",
    ]
    for part in report.get("parts", []):
        dimensions = part.get("dimensions", {})
        summary = "; ".join(
            f"{name}: {record.get('status', 'missing')}"
            for name, record in dimensions.items()
        )
        lines.append(
            f"| {part.get('partId', 'unknown')} | {part.get('status', 'unknown')} | {summary} |"
        )
    lines.extend(
        [
            "",
            "## Objective evidence",
            "",
            "| Objective | Evidence Blocks | Status | Evidence |",
            "| --- | --- | --- | --- |",
        ]
    )
    for objective in report.get("objectives", []):
        lines.append(
            "| {objective} | {blocks} | {status} | {evidence} |".format(
                objective=objective.get("objectiveId", "unknown"),
                blocks=", ".join(objective.get("evidenceBlockIds", [])),
                status=objective.get("status", "unknown"),
                evidence=str(objective.get("evidence", "")).replace("|", "\\|"),
            )
        )
    lines.extend(["", "## Overall checks", "", "| Check | Status | Evidence |", "| --- | --- | --- |"])
    for name, record in report.get("overallChecks", {}).items():
        lines.append(
            f"| {name} | {record.get('status', 'unknown')} | {str(record.get('evidence', '')).replace('|', chr(92) + '|')} |"
        )
    return "\n".join(lines) + "\n"


def write_v2_review_markdown(root: Path, report: dict) -> Path:
    path = root.resolve() / V2_REVIEW_MARKDOWN_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_v2_review_report(report), encoding="utf-8")
    return path


def _require_pass(item: object, label: str) -> None:
    if not isinstance(item, dict) or item.get("status") != "pass":
        raise V2ReviewBlocked(f"{label} did not pass independent review")
    if not isinstance(item.get("evidence"), str) or not item["evidence"].strip():
        raise V2ReviewBlocked(f"{label} lacks concrete review evidence")


def verify_g8_review(root: Path) -> dict:
    from course_toolkit.annotations import AnnotationStore
    from course_toolkit.course_compiler import canonical_json_hash
    from course_toolkit.preview_evidence import verify_g7_preview
    from course_toolkit.workflow import hash_path, verify_g6_validation

    root = root.resolve()
    verify_g6_validation(root)
    verify_g7_preview(root)
    path = root / V2_REVIEW_RELATIVE_PATH
    if path.is_symlink() or not path.is_file():
        raise V2ReviewBlocked("G8 independent review report is missing")
    report = load_json(path)
    if report.get("schemaVersion") != V2_REVIEW_SCHEMA_VERSION:
        raise V2ReviewBlocked("G8 requires review-report schemaVersion 2.0")
    if report.get("courseDefinitionSchemaVersion") != "2.0":
        raise V2ReviewBlocked("legacy review cannot certify CourseDefinition 2.0")
    document = load_json(root / "course/course.json")
    if report.get("definitionHash") != canonical_json_hash(document):
        raise V2ReviewBlocked("G8 review definition hash is stale")
    validation_hash = hash_path(root / ".course-work/course-validation-report.json")
    preview_hash = hash_path(root / ".course-work/preview-manifest.json")
    if report.get("validationReportHash") != validation_hash:
        raise V2ReviewBlocked("G8 validation report hash is stale")
    if report.get("previewManifestHash") != preview_hash:
        raise V2ReviewBlocked("G8 preview manifest hash is stale")
    if report.get("workEvidence") != _v2_work_hashes(root):
        raise V2ReviewBlocked("G8 authoring evidence is stale")
    if report.get("status") != "publishable":
        raise V2ReviewBlocked("G8 independent review is not publishable")
    if not isinstance(report.get("reviewedAt"), str) or not report["reviewedAt"]:
        raise V2ReviewBlocked("G8 review time is missing")
    parts, blocks = _v2_definition_index(document)
    expected_part_ids = [part["id"] for part, _ in parts]
    actual_parts = report.get("parts")
    if not isinstance(actual_parts, list) or [part.get("partId") for part in actual_parts] != expected_part_ids:
        raise V2ReviewBlocked("G8 Part review does not match the current definition")
    for (definition_part, slices), part_review in zip(parts, actual_parts):
        if part_review.get("status") != "pass":
            raise V2ReviewBlocked(f"Part did not pass review: {definition_part['id']}")
        dimensions = part_review.get("dimensions")
        if not isinstance(dimensions, dict) or set(dimensions) != set(V2_PART_DIMENSIONS):
            raise V2ReviewBlocked(f"Part dimensions are incomplete: {definition_part['id']}")
        for name in V2_PART_DIMENSIONS:
            _require_pass(dimensions[name], f"Part dimension {definition_part['id']}/{name}")
        slice_reviews = part_review.get("slices")
        expected_slice_ids = [slice_data["id"] for slice_data in slices]
        if not isinstance(slice_reviews, list) or [item.get("sliceId") for item in slice_reviews] != expected_slice_ids:
            raise V2ReviewBlocked(f"Slice reviews are incomplete: {definition_part['id']}")
        for slice_review in slice_reviews:
            if slice_review.get("status") != "pass":
                raise V2ReviewBlocked(f"Slice did not pass review: {slice_review.get('sliceId')}")
            checks = slice_review.get("checks")
            if not isinstance(checks, dict) or set(checks) != set(V2_SLICE_CHECKS):
                raise V2ReviewBlocked(f"Slice checks are incomplete: {slice_review.get('sliceId')}")
            for name in V2_SLICE_CHECKS:
                _require_pass(checks[name], f"Slice check {slice_review['sliceId']}/{name}")
    expected_objectives = _objective_records(document, blocks)
    objectives = report.get("objectives")
    if not isinstance(objectives, list) or [item.get("objectiveId") for item in objectives] != [item["objectiveId"] for item in expected_objectives]:
        raise V2ReviewBlocked("G8 objective review does not match the current definition")
    for expected, actual in zip(expected_objectives, objectives):
        if actual.get("evidenceBlockIds") != expected["evidenceBlockIds"]:
            raise V2ReviewBlocked(f"G8 objective evidence is stale: {expected['objectiveId']}")
        _require_pass(actual, f"Objective {expected['objectiveId']}")
    overall = report.get("overallChecks")
    if not isinstance(overall, dict) or set(overall) != set(V2_OVERALL_CHECKS):
        raise V2ReviewBlocked("G8 overall checks are incomplete")
    for name in V2_OVERALL_CHECKS:
        _require_pass(overall[name], f"Overall check {name}")
    pending = _pending_decision_or_unresolved(root)
    if pending:
        raise V2ReviewBlocked(pending)
    runtime_bug = next(
        (
            annotation
            for annotation in AnnotationStore.load(root / ".course-work/annotations.json").all()
            if annotation.classification == "runtime-bug"
            and annotation.status not in {"verified", "dismissed"}
        ),
        None,
    )
    if runtime_bug:
        raise V2ReviewBlocked(f"G8 has an unresolved runtime bug: {runtime_bug.id}")
    return {
        ".course-work/review-report.json": hash_path(path),
        ".course-work/course-validation-report.json": validation_hash,
        ".course-work/preview-manifest.json": preview_hash,
    }


def write_publication_review_evidence_v2(root: Path) -> Path:
    from course_toolkit.publication import (
        PUBLICATION_REVIEW_EVIDENCE_RELATIVE_PATH,
        PublicationReviewEvidence,
    )
    from course_toolkit.workflow import hash_path

    root = root.resolve()
    verify_g8_review(root)
    report = load_json(root / V2_REVIEW_RELATIVE_PATH)
    evidence = PublicationReviewEvidence(
        schema_version="1.0",
        status="approved",
        renderer_backed=True,
        course_definition_hash=report["definitionHash"],
        validation_report_hash=report["validationReportHash"],
        preview_manifest_hash=report["previewManifestHash"],
        review_report_hash=hash_path(root / V2_REVIEW_RELATIVE_PATH),
        reviewed_at=report["reviewedAt"],
    )
    path = root / PUBLICATION_REVIEW_EVIDENCE_RELATIVE_PATH
    write_json_atomic(path, evidence.as_dict())
    return path
