"""Schema-aware indexes for CourseDefinition asset-bearing fields."""

from dataclasses import dataclass
from typing import Iterable, Optional


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
    """Yield asset references from the pinned CourseDefinition block fields only."""
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

    parts = course.get("parts")
    if not isinstance(parts, list):
        return
    for part_index, part in enumerate(parts):
        if not isinstance(part, dict):
            continue
        part_id = part.get("id") if isinstance(part.get("id"), str) else None
        slices = part.get("slices")
        if not isinstance(slices, list):
            continue
        for slice_index, slice_data in enumerate(slices):
            if not isinstance(slice_data, dict):
                continue
            slice_id = (
                slice_data.get("id") if isinstance(slice_data.get("id"), str) else None
            )
            slice_path = f"course.parts[{part_index}].slices[{slice_index}]"
            narrations = slice_data.get("narrations")
            if isinstance(narrations, list):
                for narration_index, narration in enumerate(narrations):
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

            blocks = slice_data.get("blocks")
            if not isinstance(blocks, list):
                continue
            for block_index, block in enumerate(blocks):
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
                    items = block.get("items")
                    if not isinstance(items, list):
                        continue
                    for item_index, item in enumerate(items):
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
