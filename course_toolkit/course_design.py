import re
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .course_validation import BLOCK_TYPES
from .errors import ValidationIssue


AUDIENCES = {
    "student-core",
    "student-evidence",
    "teacher-design",
    "ai-system",
    "reference",
    "proposed-exclusion",
}
AUDIENCE_DISPOSITIONS = {
    "student-core": "storyboard",
    "student-evidence": "storyboard",
    "teacher-design": "work-record",
    "ai-system": "work-record",
    "reference": "work-record",
    "proposed-exclusion": "exclude",
}
REVIEW_DIMENSIONS: Tuple[str, ...] = (
    "instructionalGoalStructure",
    "contentCompleteness",
    "studentFacingPresentation",
    "modalityChoice",
    "practiceFeedback",
    "resourcesFormat",
)
OVERALL_CHECKS: Tuple[str, ...] = (
    "allPartsPass",
    "sourceClassificationCoverage",
    "resourcesPresent",
    "courseJsonSchema",
    "indexConsistency",
    "courseIntroduction",
    "courseConclusion",
    "images",
    "pdf",
    "video",
    "html",
    "assessments",
    "unresolved",
)
REVIEW_STATUSES = {"pass", "revise"}
NON_LEARNER_PATTERNS = (
    re.compile(r"设计思路"),
    re.compile(r"AI\s*角色", re.IGNORECASE),
    re.compile(r"老师\s*(?:vs\.?|VS\.?|与)\s*系统", re.IGNORECASE),
    re.compile(r"教师(?:备注|说明|操作指南)"),
    re.compile(r"(?:系统|后台)(?:实现|规则|字段|处理逻辑)"),
)


def _issue(path: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(path, code, message)


def _non_empty_string(
    value: object,
    path: str,
    issues: List[ValidationIssue],
) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        issues.append(_issue(path, "required", f"{path} must be a non-empty string"))
        return None
    return value


def _course_parts(course_data: Optional[dict]) -> Dict[str, dict]:
    if not isinstance(course_data, dict):
        return {}
    course = course_data.get("course")
    if not isinstance(course, dict):
        return {}
    parts: Dict[str, dict] = {}
    for part in course.get("parts", []):
        if isinstance(part, dict) and isinstance(part.get("id"), str):
            parts[part["id"]] = part
    return parts


def _course_pieces(course_data: Optional[dict]) -> Dict[Tuple[str, str], dict]:
    pieces: Dict[Tuple[str, str], dict] = {}
    for part_id, part in _course_parts(course_data).items():
        for piece in part.get("pieces", []):
            if isinstance(piece, dict) and isinstance(piece.get("id"), str):
                pieces[(part_id, piece["id"])] = piece
    return pieces


def _course_root(course_data: Optional[dict]) -> Dict[str, object]:
    if not isinstance(course_data, dict):
        return {}
    course = course_data.get("course")
    return course if isinstance(course, dict) else {}


def _course_objectives(course_data: Optional[dict]) -> Dict[str, dict]:
    introduction = _course_root(course_data).get("introduction")
    if not isinstance(introduction, dict):
        return {}
    objectives: Dict[str, dict] = {}
    for objective in introduction.get("objectives", []):
        if isinstance(objective, dict) and isinstance(objective.get("id"), str):
            objectives[objective["id"]] = objective
    return objectives


def _course_blocks(course_data: Optional[dict]) -> Dict[str, dict]:
    blocks: Dict[str, dict] = {}
    for part in _course_parts(course_data).values():
        for piece in part.get("pieces", []):
            if not isinstance(piece, dict):
                continue
            for block in piece.get("blocks", []):
                if isinstance(block, dict) and isinstance(block.get("id"), str):
                    blocks[block["id"]] = block
    return blocks


def _course_block_parts(course_data: Optional[dict]) -> Dict[str, str]:
    locations: Dict[str, str] = {}
    for part_id, part in _course_parts(course_data).items():
        for piece in part.get("pieces", []):
            if not isinstance(piece, dict):
                continue
            for block in piece.get("blocks", []):
                if isinstance(block, dict) and isinstance(block.get("id"), str):
                    locations[block["id"]] = part_id
    return locations


def _is_evidence_block(block: dict) -> bool:
    block_type = block.get("type")
    if block_type in {"fillBlank", "singleChoice", "interactiveHtml"}:
        return True
    return block_type == "video" and isinstance(block.get("interaction"), dict)


def _validate_course_frame(
    frame: object,
    course_data: Optional[dict],
    valid_source_ids: Optional[Set[str]],
) -> List[ValidationIssue]:
    if not isinstance(frame, dict):
        return [_issue("courseFrame", "required", "courseFrame is required")]

    issues: List[ValidationIssue] = []
    if frame.get("teacherConfirmed") is not True:
        issues.append(
            _issue(
                "courseFrame.teacherConfirmed",
                "teacher-confirmation-required",
                "the course introduction and conclusion need teacher confirmation",
            )
        )

    for field in ("introduction", "conclusion"):
        value = frame.get(field)
        if not isinstance(value, dict):
            issues.append(
                _issue(f"courseFrame.{field}", "required", f"{field} is required")
            )
            continue
        course_value = _course_root(course_data).get(field)
        if course_data is not None and value != course_value:
            issues.append(
                _issue(
                    f"courseFrame.{field}",
                    "course-frame-drift",
                    f"courseFrame {field} does not match course.json",
                )
            )

    source_ids = frame.get("sourceIds")
    if not isinstance(source_ids, list) or not source_ids:
        issues.append(
            _issue(
                "courseFrame.sourceIds",
                "required",
                "courseFrame sourceIds must not be empty",
            )
        )
    else:
        for index, source_id in enumerate(source_ids):
            path = f"courseFrame.sourceIds[{index}]"
            if not isinstance(source_id, str) or not source_id.strip():
                issues.append(_issue(path, "required", "sourceId is required"))
            elif valid_source_ids is not None and source_id not in valid_source_ids:
                issues.append(
                    _issue(
                        path,
                        "unknown-course-frame-source",
                        f"courseFrame source was not extracted: {source_id}",
                    )
                )

    pending = frame.get("pendingConfirmations")
    if not isinstance(pending, list):
        issues.append(
            _issue(
                "courseFrame.pendingConfirmations",
                "required",
                "pendingConfirmations must be a list",
            )
        )
    elif pending:
        issues.append(
            _issue(
                "courseFrame.pendingConfirmations",
                "pending-confirmation",
                "courseFrame still contains unresolved teacher confirmations",
            )
        )

    alignments = frame.get("objectiveAlignment")
    if not isinstance(alignments, list):
        return issues + [
            _issue(
                "courseFrame.objectiveAlignment",
                "required",
                "objectiveAlignment must be a list",
            )
        ]

    objectives = _course_objectives(course_data)
    parts = _course_parts(course_data)
    blocks = _course_blocks(course_data)
    block_parts = _course_block_parts(course_data)
    seen: Set[str] = set()
    for index, alignment in enumerate(alignments):
        path = f"courseFrame.objectiveAlignment[{index}]"
        if not isinstance(alignment, dict):
            issues.append(_issue(path, "required", "alignment must be an object"))
            continue
        objective_id = _non_empty_string(
            alignment.get("objectiveId"), f"{path}.objectiveId", issues
        )
        if objective_id is not None:
            if objective_id in seen:
                issues.append(
                    _issue(
                        f"{path}.objectiveId",
                        "duplicate-objective-alignment",
                        f"objective {objective_id} is aligned more than once",
                    )
                )
            seen.add(objective_id)
            if course_data is not None and objective_id not in objectives:
                issues.append(
                    _issue(
                        f"{path}.objectiveId",
                        "unknown-objective",
                        f"unknown course objective: {objective_id}",
                    )
                )

        part_ids = alignment.get("partIds")
        aligned_part_ids: Set[str] = set()
        if not isinstance(part_ids, list) or not part_ids:
            issues.append(
                _issue(f"{path}.partIds", "required", "partIds must not be empty")
            )
        else:
            for part_index, part_id in enumerate(part_ids):
                if not isinstance(part_id, str) or not part_id.strip():
                    issues.append(
                        _issue(
                            f"{path}.partIds[{part_index}]",
                            "required",
                            "partId is required",
                        )
                    )
                elif course_data is not None and part_id not in parts:
                    issues.append(
                        _issue(
                            f"{path}.partIds[{part_index}]",
                            "unknown-objective-part",
                            f"objective points to unknown Part: {part_id}",
                        )
                    )
                else:
                    aligned_part_ids.add(part_id)

        evidence_ids = alignment.get("evidenceBlockIds")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            issues.append(
                _issue(
                    f"{path}.evidenceBlockIds",
                    "required",
                    "evidenceBlockIds must not be empty",
                )
            )
        else:
            for block_index, block_id in enumerate(evidence_ids):
                block_path = f"{path}.evidenceBlockIds[{block_index}]"
                if not isinstance(block_id, str) or not block_id.strip():
                    issues.append(_issue(block_path, "required", "Block id is required"))
                    continue
                block = blocks.get(block_id)
                if course_data is not None and block is None:
                    issues.append(
                        _issue(
                            block_path,
                            "unknown-objective-evidence",
                            f"objective points to unknown Block: {block_id}",
                        )
                    )
                elif block is not None and not _is_evidence_block(block):
                    issues.append(
                        _issue(
                            block_path,
                            "invalid-objective-evidence",
                            f"Block {block_id} does not collect learning evidence",
                        )
                    )
                elif (
                    block is not None
                    and block_parts.get(block_id) not in aligned_part_ids
                ):
                    issues.append(
                        _issue(
                            block_path,
                            "objective-evidence-part-mismatch",
                            f"evidence Block {block_id} is outside the objective's aligned Parts",
                        )
                    )

    if course_data is not None:
        for objective_id in sorted(set(objectives) - seen):
            issues.append(
                _issue(
                    f"courseFrame.objectiveAlignment:{objective_id}",
                    "missing-objective-alignment",
                    "every course objective needs exactly one alignment",
                )
            )
    return issues


def _source_ids(extracted_data: object) -> Set[str]:
    if not isinstance(extracted_data, dict):
        return set()
    result = set()
    for item in extracted_data.get("items", []):
        if isinstance(item, dict) and isinstance(item.get("sourceId"), str):
            result.add(item["sourceId"])
    return result


def validate_audience_classification(
    data: object,
    valid_source_ids: Optional[Set[str]] = None,
) -> List[ValidationIssue]:
    if not isinstance(data, dict):
        return [_issue("$", "required", "audience classification must be an object")]
    issues: List[ValidationIssue] = []
    if data.get("schemaVersion") != "1.0":
        issues.append(
            _issue("schemaVersion", "invalid-version", "schemaVersion must be 1.0")
        )
    if data.get("teacherConfirmed") is not True:
        issues.append(
            _issue(
                "teacherConfirmed",
                "teacher-confirmation-required",
                "the grouped audience classification needs teacher confirmation",
            )
        )
    groups = data.get("groups")
    if not isinstance(groups, list) or not groups:
        return issues + [_issue("groups", "required", "classification groups are required")]

    seen: Dict[str, str] = {}
    for index, group in enumerate(groups):
        path = f"groups[{index}]"
        if not isinstance(group, dict):
            issues.append(_issue(path, "required", "classification group must be an object"))
            continue
        audience = group.get("audience")
        if audience not in AUDIENCES:
            issues.append(
                _issue(
                    f"{path}.audience",
                    "invalid-audience",
                    f"unsupported audience: {audience}",
                )
            )
        _non_empty_string(group.get("summary"), f"{path}.summary", issues)
        expected_disposition = AUDIENCE_DISPOSITIONS.get(audience)
        if expected_disposition is not None and group.get("disposition") != expected_disposition:
            issues.append(
                _issue(
                    f"{path}.disposition",
                    "invalid-disposition",
                    f"{audience} must use disposition {expected_disposition}",
                )
            )
        source_ids = group.get("sourceIds")
        if not isinstance(source_ids, list) or not source_ids:
            issues.append(
                _issue(f"{path}.sourceIds", "required", "sourceIds must not be empty")
            )
            continue
        for source_index, source_id in enumerate(source_ids):
            source_path = f"{path}.sourceIds[{source_index}]"
            if not isinstance(source_id, str) or not source_id.strip():
                issues.append(_issue(source_path, "required", "sourceId is required"))
                continue
            if source_id in seen:
                issues.append(
                    _issue(
                        source_path,
                        "duplicate-source",
                        f"{source_id} is already classified at {seen[source_id]}",
                    )
                )
            else:
                seen[source_id] = source_path

    if valid_source_ids is not None:
        for source_id in sorted(valid_source_ids - set(seen)):
            issues.append(
                _issue(
                    f"source:{source_id}",
                    "missing-source-classification",
                    "extracted source item is not classified",
                )
            )
        for source_id in sorted(set(seen) - valid_source_ids):
            issues.append(
                _issue(
                    seen[source_id],
                    "unknown-source",
                    f"sourceId was not found in extracted materials: {source_id}",
                )
            )
    return issues


def validate_storyboard(
    data: object,
    course_data: Optional[dict] = None,
    valid_source_ids: Optional[Set[str]] = None,
) -> List[ValidationIssue]:
    if not isinstance(data, dict):
        return [_issue("$", "required", "course storyboard must be an object")]
    issues: List[ValidationIssue] = []
    if data.get("schemaVersion") != "1.0":
        issues.append(
            _issue("schemaVersion", "invalid-version", "schemaVersion must be 1.0")
        )
    if data.get("teacherConfirmed") is not True:
        issues.append(
            _issue(
                "teacherConfirmed",
                "teacher-confirmation-required",
                "the complete Part/Piece storyboard needs teacher confirmation",
            )
        )
    issues.extend(
        _validate_course_frame(
            data.get("courseFrame"),
            course_data,
            valid_source_ids,
        )
    )
    parts = data.get("parts")
    if not isinstance(parts, list) or not parts:
        return issues + [_issue("parts", "required", "storyboard parts are required")]

    part_count = len(parts)
    piece_count = 0
    seen_parts: Set[str] = set()
    seen_pieces: Set[Tuple[str, str]] = set()
    course_parts = _course_parts(course_data)
    course_pieces = _course_pieces(course_data)

    for part_index, part in enumerate(parts):
        part_path = f"parts[{part_index}]"
        if not isinstance(part, dict):
            issues.append(_issue(part_path, "required", "storyboard part must be an object"))
            continue
        part_id = _non_empty_string(part.get("id"), f"{part_path}.id", issues)
        _non_empty_string(part.get("title"), f"{part_path}.title", issues)
        _non_empty_string(part.get("stageGoal"), f"{part_path}.stageGoal", issues)
        if part_id is not None:
            if part_id in seen_parts:
                issues.append(
                    _issue(f"{part_path}.id", "duplicate-id", f"duplicate Part: {part_id}")
                )
            seen_parts.add(part_id)
        pieces = part.get("pieces")
        if not isinstance(pieces, list) or not pieces:
            issues.append(
                _issue(f"{part_path}.pieces", "required", "storyboard pieces are required")
            )
            continue
        piece_count += len(pieces)
        for piece_index, piece in enumerate(pieces):
            piece_path = f"{part_path}.pieces[{piece_index}]"
            if not isinstance(piece, dict):
                issues.append(
                    _issue(piece_path, "required", "storyboard piece must be an object")
                )
                continue
            piece_id = _non_empty_string(piece.get("id"), f"{piece_path}.id", issues)
            for field in (
                "title",
                "studentSees",
                "teachingFocus",
                "studentAction",
                "completion",
            ):
                _non_empty_string(piece.get(field), f"{piece_path}.{field}", issues)
            for field in ("sourceIds", "assetNeeds", "pendingConfirmations"):
                if not isinstance(piece.get(field), list):
                    issues.append(
                        _issue(
                            f"{piece_path}.{field}",
                            "required",
                            f"{field} must be a list",
                        )
                    )
            modalities = piece.get("modalities")
            if not isinstance(modalities, list) or not modalities:
                issues.append(
                    _issue(
                        f"{piece_path}.modalities",
                        "required",
                        "every Piece needs at least one presentation modality",
                    )
                )
                modalities = []
            else:
                for modality_index, modality in enumerate(modalities):
                    if modality not in BLOCK_TYPES:
                        issues.append(
                            _issue(
                                f"{piece_path}.modalities[{modality_index}]",
                                "unsupported-modality",
                                f"unsupported modality: {modality}",
                            )
                        )
            if part_id is None or piece_id is None:
                continue
            key = (part_id, piece_id)
            if key in seen_pieces:
                issues.append(
                    _issue(f"{piece_path}.id", "duplicate-id", f"duplicate Piece: {key}")
                )
            seen_pieces.add(key)
            course_piece = course_pieces.get(key)
            if course_data is not None and course_piece is None:
                issues.append(
                    _issue(
                        piece_path,
                        "unknown-piece",
                        f"storyboard Piece does not exist in course: {part_id}/{piece_id}",
                    )
                )
            elif course_piece is not None:
                actual = {
                    block.get("type")
                    for block in course_piece.get("blocks", [])
                    if isinstance(block, dict)
                }
                if set(modalities) != actual:
                    issues.append(
                        _issue(
                            f"{piece_path}.modalities",
                            "modality-mismatch",
                            f"storyboard {sorted(set(modalities))} does not match course {sorted(actual)}",
                        )
                    )

    summary = data.get("summary")
    if not isinstance(summary, dict):
        issues.append(_issue("summary", "required", "storyboard summary is required"))
    else:
        if summary.get("partCount") != part_count:
            issues.append(
                _issue("summary.partCount", "count-mismatch", "partCount is incorrect")
            )
        if summary.get("pieceCount") != piece_count:
            issues.append(
                _issue("summary.pieceCount", "count-mismatch", "pieceCount is incorrect")
            )

    if course_data is not None:
        missing_parts = set(course_parts) - seen_parts
        extra_parts = seen_parts - set(course_parts)
        missing_pieces = set(course_pieces) - seen_pieces
        for part_id in sorted(missing_parts):
            issues.append(
                _issue(
                    f"course:{part_id}",
                    "missing-storyboard-part",
                    "course Part is absent from storyboard",
                )
            )
        for part_id in sorted(extra_parts):
            issues.append(
                _issue(
                    f"storyboard:{part_id}",
                    "unknown-part",
                    "storyboard Part is absent from course",
                )
            )
        for part_id, piece_id in sorted(missing_pieces):
            issues.append(
                _issue(
                    f"course:{part_id}/{piece_id}",
                    "missing-storyboard-piece",
                    "course Piece is absent from storyboard",
                )
            )
    return issues


def _markdown(value: object) -> str:
    if isinstance(value, list):
        value = "、".join(str(item) for item in value) if value else "无"
    text = str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def _source_summary(source_ids: object) -> object:
    if not isinstance(source_ids, list) or len(source_ids) <= 4:
        return source_ids
    return f"共 {len(source_ids)} 项来源：{'、'.join(str(item) for item in source_ids[:3])}…"


def render_storyboard(data: dict) -> str:
    summary = data["summary"]
    frame = data["courseFrame"]
    introduction = frame["introduction"]
    conclusion = frame["conclusion"]
    objectives = [item["text"] for item in introduction["objectives"]]
    sources = _source_summary(frame.get("sourceIds", []))
    pending = frame.get("pendingConfirmations", [])
    lines = [
        "# 课程设计确认表",
        "",
        "## 课程首尾设计",
        "",
        "| 区域 | 学生最终会看到的内容 | 来源与判断依据 | 待确认 |",
        "| --- | --- | --- | --- |",
        f"| 课程介绍 | {_markdown(introduction['overview'])} | {_markdown(sources)} | {_markdown(pending)} |",
        f"| 课程目标 | {_markdown(objectives)} | {_markdown(sources)} | {_markdown(pending)} |",
        f"| 学习关键点 | {_markdown(introduction['keyPoints'])} | {_markdown(sources)} | {_markdown(pending)} |",
        f"| 课程总结 | {_markdown(conclusion['summary'])} | {_markdown(sources)} | {_markdown(pending)} |",
        f"| 学生带走什么 | {_markdown(conclusion['takeaways'])} | {_markdown(sources)} | {_markdown(pending)} |",
        f"| 可以迁移到哪里 | {_markdown(conclusion['transferApplications'])} | {_markdown(sources)} | {_markdown(pending)} |",
        "",
        "## Part/Piece 设计",
        "",
        f"共 {summary['partCount']} 个 Part、{summary['pieceCount']} 个 Piece。",
        "",
        "| Part / Piece | Part 阶段目标 | 学生看到什么 | 教学重点 | 呈现方式 | 学生行动 | 完成标准 | 资源与待确认项 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for part in data["parts"]:
        for piece in part["pieces"]:
            resources = list(piece.get("assetNeeds", [])) + list(
                piece.get("pendingConfirmations", [])
            )
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown(f"{part['id']} / {piece['id']}"),
                        _markdown(part["stageGoal"]),
                        _markdown(piece["studentSees"]),
                        _markdown(piece["teachingFocus"]),
                        _markdown(piece["modalities"]),
                        _markdown(piece["studentAction"]),
                        _markdown(piece["completion"]),
                        _markdown(resources),
                    ]
                )
                + " |"
            )
    return "\n".join(lines) + "\n"


def _review_entry_issues(
    entry: object,
    path: str,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    if not isinstance(entry, dict):
        return [_issue(path, "required", "review entry must be an object")]
    if entry.get("status") not in REVIEW_STATUSES:
        issues.append(
            _issue(f"{path}.status", "invalid-status", "status must be pass or revise")
        )
    _non_empty_string(entry.get("evidence"), f"{path}.evidence", issues)
    return issues


def validate_review_report(
    data: object,
    course_data: Optional[dict] = None,
) -> List[ValidationIssue]:
    if not isinstance(data, dict):
        return [_issue("$", "required", "review report must be an object")]
    issues: List[ValidationIssue] = []
    if data.get("schemaVersion") != "1.0":
        issues.append(
            _issue("schemaVersion", "invalid-version", "schemaVersion must be 1.0")
        )
    part_reviews = data.get("partReviews")
    if not isinstance(part_reviews, list) or not part_reviews:
        part_reviews = []
        issues.append(_issue("partReviews", "required", "Part reviews are required"))

    course_parts = _course_parts(course_data)
    reviewed: Set[str] = set()
    all_parts_pass = True
    for index, review in enumerate(part_reviews):
        path = f"partReviews[{index}]"
        if not isinstance(review, dict):
            issues.append(_issue(path, "required", "Part review must be an object"))
            all_parts_pass = False
            continue
        part_id = _non_empty_string(review.get("partId"), f"{path}.partId", issues)
        _non_empty_string(review.get("partTitle"), f"{path}.partTitle", issues)
        if part_id is not None:
            if part_id in reviewed:
                issues.append(
                    _issue(f"{path}.partId", "duplicate-id", f"duplicate review: {part_id}")
                )
            reviewed.add(part_id)
            if course_data is not None and part_id not in course_parts:
                issues.append(
                    _issue(f"{path}.partId", "unknown-part", f"unknown Part: {part_id}")
                )
        dimensions = review.get("dimensions")
        statuses = []
        if not isinstance(dimensions, dict):
            issues.append(
                _issue(f"{path}.dimensions", "required", "review dimensions are required")
            )
            all_parts_pass = False
            dimensions = {}
        for dimension in REVIEW_DIMENSIONS:
            if dimension not in dimensions:
                issues.append(
                    _issue(
                        f"{path}.dimensions.{dimension}",
                        "missing-review-dimension",
                        f"Part review is missing {dimension}",
                    )
                )
                statuses.append("missing")
                continue
            issues.extend(
                _review_entry_issues(
                    dimensions[dimension],
                    f"{path}.dimensions.{dimension}",
                )
            )
            if isinstance(dimensions[dimension], dict):
                statuses.append(dimensions[dimension].get("status"))
        expected_conclusion = (
            "pass"
            if len(statuses) == len(REVIEW_DIMENSIONS)
            and all(status == "pass" for status in statuses)
            else "revise"
        )
        if review.get("conclusion") != expected_conclusion:
            issues.append(
                _issue(
                    f"{path}.conclusion",
                    "invalid-part-conclusion",
                    f"Part conclusion must be {expected_conclusion}",
                )
            )
        if expected_conclusion != "pass":
            all_parts_pass = False
        if not isinstance(review.get("recommendations"), list):
            issues.append(
                _issue(
                    f"{path}.recommendations",
                    "required",
                    "recommendations must be a list",
                )
            )

    if course_data is not None:
        for part_id in sorted(set(course_parts) - reviewed):
            issues.append(
                _issue(
                    f"course:{part_id}",
                    "missing-part-review",
                    "course Part has no review",
                )
            )
            all_parts_pass = False

    overall_checks = data.get("overallChecks")
    all_overall_pass = True
    if not isinstance(overall_checks, dict):
        overall_checks = {}
        issues.append(
            _issue("overallChecks", "required", "overall review checks are required")
        )
    for check in OVERALL_CHECKS:
        if check not in overall_checks:
            issues.append(
                _issue(
                    f"overallChecks.{check}",
                    "missing-overall-check",
                    f"overall review is missing {check}",
                )
            )
            all_overall_pass = False
            continue
        issues.extend(
            _review_entry_issues(overall_checks[check], f"overallChecks.{check}")
        )
        if (
            not isinstance(overall_checks[check], dict)
            or overall_checks[check].get("status") != "pass"
        ):
            all_overall_pass = False
    all_parts_entry = overall_checks.get("allPartsPass")
    if isinstance(all_parts_entry, dict):
        expected = "pass" if all_parts_pass else "revise"
        if all_parts_entry.get("status") != expected:
            issues.append(
                _issue(
                    "overallChecks.allPartsPass.status",
                    "part-summary-mismatch",
                    f"allPartsPass must be {expected}",
                )
            )
            all_overall_pass = False

    final_status = data.get("finalStatus")
    if final_status not in {"uploadable", "blocked"}:
        issues.append(
            _issue(
                "finalStatus",
                "invalid-status",
                "finalStatus must be uploadable or blocked",
            )
        )
    if final_status == "uploadable" and not (all_parts_pass and all_overall_pass):
        issues.append(
            _issue(
                "finalStatus",
                "invalid-uploadable-claim",
                "uploadable requires every Part dimension and overall check to pass",
            )
        )
    if final_status == "blocked" and all_parts_pass and all_overall_pass:
        issues.append(
            _issue(
                "finalStatus",
                "status-mismatch",
                "a fully passing report must be uploadable",
            )
        )
    return issues


def render_review_report(data: dict) -> str:
    status_label = "可上传" if data["finalStatus"] == "uploadable" else "缺少必要材料，暂不可上传"
    lines = [
        f"# {status_label}",
        "",
        "## Part 逐项 Review",
        "",
        "| Part | 标题 | 教学目标与结构 | 内容完整性 | 学生呈现 | 模态选择 | 练习与反馈 | 资源与格式 | 结论 | 修改建议 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for review in data["partReviews"]:
        dimensions = review["dimensions"]
        values = []
        for name in REVIEW_DIMENSIONS:
            entry = dimensions[name]
            values.append(f"{entry['status']}: {entry['evidence']}")
        recommendations = review.get("recommendations", [])
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown(review["partId"]),
                    _markdown(review["partTitle"]),
                    *[_markdown(value) for value in values],
                    _markdown(review["conclusion"]),
                    _markdown(recommendations),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 整体 Review",
            "",
            "| 检查项 | 结果 | 证据 |",
            "| --- | --- | --- |",
        ]
    )
    for check in OVERALL_CHECKS:
        entry = data["overallChecks"][check]
        lines.append(
            f"| {_markdown(check)} | {_markdown(entry['status'])} | {_markdown(entry['evidence'])} |"
        )
    return "\n".join(lines) + "\n"


def _iter_learner_strings(data: object, path: str = "$") -> Iterable[Tuple[str, str]]:
    if isinstance(data, dict):
        for key, value in data.items():
            child = f"{path}.{key}"
            if key in {"title", "content", "prompt", "label", "alt"} and isinstance(
                value, str
            ):
                yield child, value
            else:
                yield from _iter_learner_strings(value, child)
    elif isinstance(data, list):
        for index, value in enumerate(data):
            yield from _iter_learner_strings(value, f"{path}[{index}]")


def validate_learner_facing_course(data: object) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    for path, value in _iter_learner_strings(data):
        for pattern in NON_LEARNER_PATTERNS:
            if pattern.search(value):
                issues.append(
                    _issue(
                        path,
                        "non-learner-content",
                        "course.json and index.md may contain learner-facing content only",
                    )
                )
                break
    return issues


def extracted_source_ids(data: object) -> Set[str]:
    return _source_ids(data)
