from pathlib import Path
from typing import Iterable, List, Tuple

from .errors import ValidationIssue


def resolve_course_path(course_root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Unsafe course path: {raw_path}")
    resolved = (course_root / candidate).resolve()
    root = course_root.resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError(f"Unsafe course path: {raw_path}")
    return resolved


def iter_references(data: object) -> Iterable[Tuple[str, str]]:
    if not isinstance(data, dict):
        return
    course = data.get("course")
    if not isinstance(course, dict):
        return
    for part_index, part in enumerate(course.get("parts", [])):
        if not isinstance(part, dict):
            continue
        for piece_index, piece in enumerate(part.get("pieces", [])):
            if not isinstance(piece, dict):
                continue
            for block_index, block in enumerate(piece.get("blocks", [])):
                if not isinstance(block, dict):
                    continue
                base = (
                    f"course.parts[{part_index}].pieces[{piece_index}]"
                    f".blocks[{block_index}]"
                )
                block_type = block.get("type")
                if block_type == "images":
                    for item_index, item in enumerate(block.get("items", [])):
                        if isinstance(item, dict) and isinstance(item.get("source"), str):
                            yield f"{base}.items[{item_index}].source", item["source"]
                elif block_type in {"video", "interactiveHtml"}:
                    if isinstance(block.get("source"), str):
                        yield f"{base}.source", block["source"]
                    interaction = block.get("interaction")
                    if block_type == "video" and isinstance(interaction, dict):
                        for key in ("data", "document"):
                            if isinstance(interaction.get(key), str):
                                yield f"{base}.interaction.{key}", interaction[key]


def validate_referenced_paths(
    course_root: Path,
    data: object,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    for path, raw in iter_references(data):
        try:
            resolved = resolve_course_path(course_root, raw)
        except ValueError as exc:
            issues.append(ValidationIssue(path, "unsafe-path", str(exc)))
            continue
        if not resolved.is_file():
            issues.append(
                ValidationIssue(path, "missing-file", f"referenced file does not exist: {raw}")
            )
    return issues
