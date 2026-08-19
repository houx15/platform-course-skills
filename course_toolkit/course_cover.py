"""Reviewable course-cover candidates bound to a confirmed catalog course."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .course_catalog import CourseCatalogError, load_confirmed_course_selection
from .jsonio import load_json, write_json_atomic
from .workflow import hash_path


CANDIDATE_RECORD = Path(".course-work/course-cover-candidate.json")
CONFIRMED_RECORD = Path(".course-work/course-cover.json")
DELIVERY_PATH = Path(".course-work/cover-delivery/course-cover.webp")
OSS_RELATIVE_PATH = "cover/course-cover.webp"
PROMPT_VERSION = "course-cover-v1"


COURSE_COVER_PROMPT_TEMPLATE = """Create a 16:9 conceptual course cover for high-school students.

Course title: “{course_title}”

Translate the course’s central idea into one clear technology-inspired visualisation. Use one dominant visual structure and no more than two supporting elements. The structure may use connected nodes, layered evidence, branching paths, data forms, image fragments, timelines, or geometric relationships, depending on the course description.

Use a dark navy or charcoal background, not pure black. Use one main accent colour and one supporting accent colour, with controlled light and subtle glow. Keep the colours restrained and coherent. Avoid rainbow gradients and excessive neon effects.

Fill the whole 16:9 frame without reserving space for text. The main visualisation should be large, clear, and easy to understand. Keep the composition spacious rather than crowded.

A stylized high-school student may appear as a small secondary figure at the edge of the scene, viewed from the side or from behind. The student should only observe the visualisation, with no visible hand action. Omit the character when it does not improve the concept.

The result should feel intelligent, contemporary, and cinematic, combining educational meaning with restrained technology aesthetics.

Do not include readable text, logos, or watermarks. Avoid photorealistic people, childish characters, generic sci-fi interfaces, crowded dashboards, excessive detail, and decorative technology elements unrelated to the course."""


class CourseCoverError(ValueError):
    pass


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _probe_webp(path: Path) -> dict[str, int]:
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,width,height",
                "-of",
                "json",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CourseCoverError("ffprobe is required to validate the generated WebP cover") from exc
    if completed.returncode != 0:
        raise CourseCoverError("the generated cover is not a readable WebP image")
    try:
        streams = json.loads(completed.stdout).get("streams", [])
        stream = streams[0]
        width = int(stream["width"])
        height = int(stream["height"])
    except (ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
        raise CourseCoverError("the generated cover has no readable image dimensions") from exc
    if stream.get("codec_name") != "webp":
        raise CourseCoverError("the generated course cover must be WebP")
    return {"width": width, "height": height}


def _probe_image_dimensions(path: Path) -> dict[str, int]:
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CourseCoverError("ffprobe is required to inspect the preserved imagegen2 cover source") from exc
    if completed.returncode != 0:
        raise CourseCoverError("the preserved imagegen2 cover source is not a readable image")
    try:
        stream = json.loads(completed.stdout).get("streams", [])[0]
        width = int(stream["width"])
        height = int(stream["height"])
    except (ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
        raise CourseCoverError("the preserved imagegen2 cover source has no readable dimensions") from exc
    if width <= 0 or height <= 0:
        raise CourseCoverError("the preserved imagegen2 cover source has invalid dimensions")
    return {"width": width, "height": height}


def _load_catalog_selection(root: Path) -> dict:
    try:
        return load_confirmed_course_selection(root)
    except CourseCatalogError as exc:
        raise CourseCoverError(str(exc)) from exc


def build_cover_prompt(root: Path) -> str:
    """Return the pinned imagegen2 prompt for the teacher-confirmed course."""
    selection = _load_catalog_selection(Path(root).resolve())
    return COURSE_COVER_PROMPT_TEMPLATE.format(course_title=selection["title"])


def prepare_cover_candidate(
    root: Path,
    source_path: Path,
    candidate_path: Path,
    *,
    prompt: str,
    created_at: str,
) -> dict:
    """Encode a preserved imagegen2 source through the fixed quality-100 path."""
    root = Path(root).resolve()
    source_path = Path(source_path).resolve()
    candidate_path = Path(candidate_path).resolve()
    source_parent = (root / ".course-work/cover-sources").resolve()
    candidate_parent = (root / ".course-work/cover-candidates").resolve()
    if not _inside(source_path, source_parent):
        raise CourseCoverError("preserve the imagegen2 source under .course-work/cover-sources/ before encoding")
    if source_path.is_symlink() or not source_path.is_file():
        raise CourseCoverError("the preserved imagegen2 source is missing or unsafe")
    if not _inside(candidate_path, candidate_parent) or candidate_path.suffix.lower() != ".webp":
        raise CourseCoverError("the encoded cover must be a .webp under .course-work/cover-candidates/")
    if candidate_path.exists() or candidate_path.is_symlink():
        raise CourseCoverError("the cover candidate path already exists; choose a new no-clobber path")
    expected_prompt = build_cover_prompt(root)
    if not isinstance(prompt, str) or prompt.strip() != expected_prompt:
        raise CourseCoverError(
            "use the pinned course-cover prompt returned by manage-course-cover.py prompt without rewriting it"
        )
    source_dimensions = _probe_image_dimensions(source_path)
    target_ratio = 16 / 9
    source_ratio = source_dimensions["width"] / source_dimensions["height"]
    ratio_error = abs(source_ratio - target_ratio) / target_ratio
    if ratio_error > 0.02:
        raise CourseCoverError(
            "the imagegen2 source is not close enough to 16:9 for safe normalization; generate a new cover"
        )
    normalize_dimensions = source_dimensions["width"] * 9 != source_dimensions["height"] * 16
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "cwebp",
        "-quiet",
        "-q",
        "100",
        "-metadata",
        "none",
    ]
    if normalize_dimensions:
        command.extend(["-resize", "1600", "900"])
    command.extend([str(source_path), "-o", str(candidate_path)])
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CourseCoverError("cwebp is required to create the quality-100 WebP cover") from exc
    if completed.returncode != 0 or not candidate_path.is_file():
        if candidate_path.is_file():
            candidate_path.unlink()
        raise CourseCoverError("quality-100 WebP cover encoding failed")
    try:
        record = register_cover_candidate(
            root,
            candidate_path,
            prompt=prompt,
            generator="imagegen2-subagent",
            quality=100,
            created_at=created_at,
        )
    except Exception:
        if candidate_path.is_file():
            candidate_path.unlink()
        raise
    record.update(
        sourceWidth=source_dimensions["width"],
        sourceHeight=source_dimensions["height"],
        aspectNormalization=("resize-1600x900" if normalize_dimensions else "not-needed"),
    )
    write_json_atomic(root / CANDIDATE_RECORD, record)
    return record


def register_cover_candidate(
    root: Path,
    candidate_path: Path,
    *,
    prompt: str,
    generator: str,
    quality: int,
    created_at: str,
) -> dict:
    root = Path(root).resolve()
    candidate_path = Path(candidate_path).resolve()
    allowed = (root / ".course-work/cover-candidates").resolve()
    if not _inside(candidate_path, allowed):
        raise CourseCoverError("cover candidates must stay under .course-work/cover-candidates/")
    if candidate_path.is_symlink() or not candidate_path.is_file():
        raise CourseCoverError("the generated cover candidate is missing or unsafe")
    if candidate_path.suffix.lower() != ".webp":
        raise CourseCoverError("the generated course cover must use a .webp filename")
    with candidate_path.open("rb") as source:
        header = source.read(12)
    if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WEBP":
        raise CourseCoverError("the generated course cover must contain WebP bytes")
    if quality != 100:
        raise CourseCoverError("the delivery cover must be encoded as quality-100 WebP")
    expected_prompt = build_cover_prompt(root)
    if not isinstance(prompt, str) or prompt.strip() != expected_prompt:
        raise CourseCoverError(
            "use the pinned course-cover prompt returned by manage-course-cover.py prompt without rewriting it"
        )
    if generator != "imagegen2-subagent":
        raise CourseCoverError("the cover must be generated by the required imagegen2 subagent workflow")
    dimensions = _probe_webp(candidate_path)
    if dimensions["width"] <= 0 or dimensions["height"] <= 0:
        raise CourseCoverError("the generated cover dimensions are invalid")
    if dimensions["width"] * 9 != dimensions["height"] * 16:
        raise CourseCoverError("the generated course cover must be exactly 16:9")
    selection = _load_catalog_selection(root)
    record = {
        "schemaVersion": "1.0",
        "catalogId": selection["catalogId"],
        "catalogHash": selection["catalogHash"],
        "candidatePath": candidate_path.relative_to(root).as_posix(),
        "sha256": hash_path(candidate_path),
        "width": dimensions["width"],
        "height": dimensions["height"],
        "format": "webp",
        "qualitySetting": quality,
        "generator": generator,
        "promptVersion": PROMPT_VERSION,
        "prompt": expected_prompt,
        "teacherConfirmed": False,
        "createdAt": created_at,
    }
    write_json_atomic(root / CANDIDATE_RECORD, record)
    return record


def _load_current_candidate(root: Path) -> dict[str, Any]:
    path = root / CANDIDATE_RECORD
    if path.is_symlink() or not path.is_file():
        raise CourseCoverError("a generated course-cover candidate is required")
    try:
        record = load_json(path)
    except ValueError as exc:
        raise CourseCoverError(str(exc)) from exc
    candidate_path = root / record.get("candidatePath", "")
    selection = _load_catalog_selection(root)
    if record.get("catalogHash") != selection["catalogHash"]:
        raise CourseCoverError("the selected catalog course changed after cover generation")
    if candidate_path.is_symlink() or not candidate_path.is_file() or hash_path(candidate_path) != record.get("sha256"):
        raise CourseCoverError("the generated cover candidate changed after review preparation")
    return record


def confirm_cover_candidate(root: Path, *, teacher_response: str, confirmed_at: str) -> dict:
    root = Path(root).resolve()
    if not isinstance(teacher_response, str) or not teacher_response.strip():
        raise CourseCoverError("the teacher must preview and explicitly confirm the generated cover")
    candidate = _load_current_candidate(root)
    source = root / candidate["candidatePath"]
    delivery = root / DELIVERY_PATH
    delivery.parent.mkdir(parents=True, exist_ok=True)
    if delivery.exists():
        if delivery.is_symlink() or not delivery.is_file() or hash_path(delivery) != candidate["sha256"]:
            raise CourseCoverError("a different course cover already exists; keep it and choose a new delivery filename")
    else:
        shutil.copyfile(source, delivery)
    confirmed = {
        **candidate,
        "relativePath": OSS_RELATIVE_PATH,
        "localPath": DELIVERY_PATH.as_posix(),
        "teacherConfirmed": True,
        "teacherResponse": teacher_response.strip(),
        "confirmedAt": confirmed_at,
    }
    write_json_atomic(root / CONFIRMED_RECORD, confirmed)
    return confirmed


def load_confirmed_cover(root: Path) -> dict:
    root = Path(root).resolve()
    path = root / CONFIRMED_RECORD
    if path.is_symlink() or not path.is_file():
        raise CourseCoverError("publication requires a teacher-confirmed generated course cover")
    try:
        record = load_json(path)
    except ValueError as exc:
        raise CourseCoverError(str(exc)) from exc
    if record.get("teacherConfirmed") is not True:
        raise CourseCoverError("the generated course cover is not teacher-confirmed")
    selection = _load_catalog_selection(root)
    if record.get("catalogHash") != selection["catalogHash"]:
        raise CourseCoverError("the selected catalog course changed after cover confirmation")
    delivery = root / record.get("localPath", "")
    if delivery.is_symlink() or not delivery.is_file() or hash_path(delivery) != record.get("sha256"):
        raise CourseCoverError("the confirmed generated course cover changed")
    if record.get("format") != "webp" or record.get("qualitySetting") != 100:
        raise CourseCoverError("the confirmed generated cover no longer matches the quality-100 WebP contract")
    if record.get("promptVersion") != PROMPT_VERSION or record.get("prompt") != build_cover_prompt(root):
        raise CourseCoverError("the confirmed generated cover no longer matches the pinned course-cover prompt")
    if record.get("width", 0) * 9 != record.get("height", 0) * 16:
        raise CourseCoverError("the confirmed generated course cover is no longer 16:9")
    return record
