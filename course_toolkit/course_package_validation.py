import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from course_toolkit.errors import ValidationIssue


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
    actual_paths = sorted({reference.source for reference in references})
    expected_paths = sorted(set(expected_asset_paths))
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
        _, path_issue = _resolve_asset(root, reference)
        if path_issue:
            issues.append(path_issue)
    return AssetValidationResult(references, tuple(issues))
