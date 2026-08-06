import re
from typing import Dict, List, Optional, Set

from .errors import ValidationIssue


ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
BLOCK_TYPES = {
    "text",
    "images",
    "video",
    "interactiveHtml",
    "fillBlank",
    "singleChoice",
}


def _issue(path: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(path, code, message)


def _mapping(value: object, path: str, issues: List[ValidationIssue]) -> Optional[dict]:
    if not isinstance(value, dict):
        issues.append(_issue(path, "required", f"{path} must be an object"))
        return None
    return value


def _string(
    value: object,
    path: str,
    issues: List[ValidationIssue],
) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        issues.append(_issue(path, "required", f"{path} must be a non-empty string"))
        return None
    return value


def _boolean(value: object, path: str, issues: List[ValidationIssue]) -> None:
    if not isinstance(value, bool):
        issues.append(_issue(path, "required", f"{path} must be a boolean"))


def _register_id(
    value: object,
    path: str,
    issues: List[ValidationIssue],
    seen: Dict[str, str],
) -> None:
    identifier = _string(value, path, issues)
    if identifier is None:
        return
    if not ID_RE.fullmatch(identifier):
        issues.append(_issue(path, "invalid-id", f"invalid id: {identifier}"))
    if identifier in seen:
        issues.append(
            _issue(
                path,
                "duplicate-id",
                f"id {identifier} already used at {seen[identifier]}",
            )
        )
    else:
        seen[identifier] = path


def _list(
    value: object,
    path: str,
    issues: List[ValidationIssue],
    minimum: int = 1,
) -> Optional[list]:
    if not isinstance(value, list) or len(value) < minimum:
        issues.append(
            _issue(path, "required", f"{path} must contain at least {minimum} item(s)")
        )
        return None
    return value


def _validate_completion(
    value: object,
    path: str,
    issues: List[ValidationIssue],
) -> None:
    if value is None:
        return
    completion = _mapping(value, path, issues)
    if completion is None:
        return
    allowed = {
        "submit-any",
        "submit-correct",
        "video-ended",
        "interaction-complete",
    }
    if completion.get("rule") not in allowed:
        issues.append(_issue(f"{path}.rule", "invalid-value", "unsupported completion rule"))
    attempts = completion.get("maxAttempts")
    if attempts is not None and (
        not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 1
    ):
        issues.append(
            _issue(f"{path}.maxAttempts", "invalid-value", "maxAttempts must be positive")
        )


def _validate_assessment(
    assessment_value: object,
    path: str,
    block_type: str,
    option_ids: Set[str],
    issues: List[ValidationIssue],
) -> None:
    assessment = _mapping(assessment_value, path, issues)
    if assessment is None:
        return
    mode = assessment.get("mode")
    if block_type == "fillBlank":
        if mode == "graded":
            answers = assessment.get("acceptedAnswers")
            if not isinstance(answers, list) or not answers or not all(
                isinstance(answer, str) and answer.strip() for answer in answers
            ):
                issues.append(
                    _issue(
                        f"{path}.acceptedAnswers",
                        "required",
                        "graded fillBlank requires acceptedAnswers",
                    )
                )
        elif mode == "reflection":
            _string(assessment.get("rubric"), f"{path}.rubric", issues)
        else:
            issues.append(
                _issue(f"{path}.mode", "invalid-value", "unsupported fillBlank mode")
            )
        return

    if mode == "graded":
        correct = _string(
            assessment.get("correctOptionId"),
            f"{path}.correctOptionId",
            issues,
        )
        if correct is not None and correct not in option_ids:
            issues.append(
                _issue(
                    f"{path}.correctOptionId",
                    "invalid-value",
                    "correctOptionId must name an option",
                )
            )
    elif mode == "survey":
        if "correctOptionId" in assessment:
            issues.append(
                _issue(
                    f"{path}.correctOptionId",
                    "forbidden",
                    "survey questions cannot have a correct answer",
                )
            )
    else:
        issues.append(
            _issue(f"{path}.mode", "invalid-value", "unsupported singleChoice mode")
        )


def _validate_block(
    value: object,
    path: str,
    issues: List[ValidationIssue],
    seen: Dict[str, str],
) -> None:
    block = _mapping(value, path, issues)
    if block is None:
        return
    _register_id(block.get("id"), f"{path}.id", issues, seen)
    block_type = block.get("type")
    if block_type not in BLOCK_TYPES:
        issues.append(
            _issue(f"{path}.type", "unsupported-type", f"unsupported block type: {block_type}")
        )
        return

    if block_type == "text":
        _string(block.get("content"), f"{path}.content", issues)
        return

    if block_type == "images":
        items = _list(block.get("items"), f"{path}.items", issues)
        if items is not None:
            for index, item_value in enumerate(items):
                item_path = f"{path}.items[{index}]"
                item = _mapping(item_value, item_path, issues)
                if item is not None:
                    _string(item.get("source"), f"{item_path}.source", issues)
                    _string(item.get("alt"), f"{item_path}.alt", issues)
        return

    _boolean(block.get("blocking"), f"{path}.blocking", issues)
    _validate_completion(block.get("completion"), f"{path}.completion", issues)

    if block_type in {"video", "interactiveHtml"}:
        _string(block.get("source"), f"{path}.source", issues)
        if block_type == "video" and "interaction" in block:
            interaction = _mapping(
                block.get("interaction"),
                f"{path}.interaction",
                issues,
            )
            if interaction is not None:
                _string(
                    interaction.get("data"),
                    f"{path}.interaction.data",
                    issues,
                )
                _string(
                    interaction.get("document"),
                    f"{path}.interaction.document",
                    issues,
                )
        return

    _string(block.get("prompt"), f"{path}.prompt", issues)
    option_ids: Set[str] = set()
    if block_type == "singleChoice":
        options = _list(block.get("options"), f"{path}.options", issues, minimum=2)
        if options is not None:
            for index, option_value in enumerate(options):
                option_path = f"{path}.options[{index}]"
                option = _mapping(option_value, option_path, issues)
                if option is None:
                    continue
                option_id = option.get("id")
                _register_id(option_id, f"{option_path}.id", issues, seen)
                if isinstance(option_id, str):
                    option_ids.add(option_id)
                _string(option.get("label"), f"{option_path}.label", issues)
    _validate_assessment(
        block.get("assessment"),
        f"{path}.assessment",
        block_type,
        option_ids,
        issues,
    )


def validate_course_data(data: object) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    root = _mapping(data, "$", issues)
    if root is None:
        return issues
    if root.get("schemaVersion") != "1.0":
        issues.append(
            _issue("schemaVersion", "invalid-version", "schemaVersion must be 1.0")
        )
    course = _mapping(root.get("course"), "course", issues)
    if course is None:
        return issues

    seen: Dict[str, str] = {}
    _register_id(course.get("id"), "course.id", issues, seen)
    _string(course.get("title"), "course.title", issues)
    _string(course.get("language"), "course.language", issues)
    parts = _list(course.get("parts"), "course.parts", issues)
    if parts is None:
        return issues

    for part_index, part_value in enumerate(parts):
        part_path = f"course.parts[{part_index}]"
        part = _mapping(part_value, part_path, issues)
        if part is None:
            continue
        _register_id(part.get("id"), f"{part_path}.id", issues, seen)
        _string(part.get("title"), f"{part_path}.title", issues)
        pieces = _list(part.get("pieces"), f"{part_path}.pieces", issues)
        if pieces is None:
            continue
        for piece_index, piece_value in enumerate(pieces):
            piece_path = f"{part_path}.pieces[{piece_index}]"
            piece = _mapping(piece_value, piece_path, issues)
            if piece is None:
                continue
            _register_id(piece.get("id"), f"{piece_path}.id", issues, seen)
            _string(piece.get("title"), f"{piece_path}.title", issues)
            blocks = _list(piece.get("blocks"), f"{piece_path}.blocks", issues)
            if blocks is None:
                continue
            for block_index, block in enumerate(blocks):
                _validate_block(
                    block,
                    f"{piece_path}.blocks[{block_index}]",
                    issues,
                    seen,
                )
    return issues
