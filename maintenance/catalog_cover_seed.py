"""One-time, auditable seeding of the 33 fixed catalog covers."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


class CatalogCoverSeedBlocked(ValueError):
    pass


def _load_catalog(repository_root: Path) -> dict:
    path = repository_root / "course_toolkit/course_catalog.json"
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogCoverSeedBlocked("the fixed course catalog could not be read") from exc
    if not isinstance(catalog, dict) or catalog.get("schemaVersion") != "2.0":
        raise CatalogCoverSeedBlocked("the fixed course catalog schema is unsupported")
    courses = catalog.get("courses")
    if not isinstance(courses, list) or len(courses) != 33:
        raise CatalogCoverSeedBlocked("the fixed course catalog must contain exactly 33 courses")
    return catalog


def build_cover_seed_plan(repository_root: Path) -> dict:
    repository_root = Path(repository_root).resolve()
    entries = []
    for course in _load_catalog(repository_root)["courses"]:
        slug = course.get("slug")
        cover = course.get("cover")
        if not isinstance(slug, str) or not isinstance(cover, dict):
            raise CatalogCoverSeedBlocked("a catalog course has invalid fixed-cover metadata")
        expected_key = f"courses/{slug}/cover/course-cover.webp"
        source = cover.get("sourcePath")
        if not isinstance(source, str):
            raise CatalogCoverSeedBlocked(f"{slug} has no fixed cover source")
        relative_source = Path(source)
        if relative_source.is_absolute() or ".." in relative_source.parts:
            raise CatalogCoverSeedBlocked(f"{slug} has an unsafe fixed cover source")
        local_path = repository_root / relative_source
        if local_path.is_symlink() or not local_path.is_file():
            raise CatalogCoverSeedBlocked(f"{slug} fixed cover is missing or changed")
        raw = local_path.read_bytes()
        sha256 = hashlib.sha256(raw).hexdigest()
        if (
            cover.get("relativePath") != "cover/course-cover.webp"
            or cover.get("objectKey") != expected_key
            or cover.get("contentType") != "image/webp"
            or cover.get("sha256") != sha256
            or cover.get("sizeBytes") != len(raw)
            or re.fullmatch(r"[0-9a-f]{64}", sha256) is None
            or not raw.startswith(b"RIFF")
            or raw[8:12] != b"WEBP"
        ):
            raise CatalogCoverSeedBlocked(f"{slug} fixed cover is missing or changed")
        entries.append(
            {
                "slug": slug,
                "sourcePath": source,
                "relativePath": cover["relativePath"],
                "objectKey": expected_key,
                "contentType": cover["contentType"],
                "sha256": sha256,
                "sizeBytes": len(raw),
            }
        )
    if [entry["slug"] for entry in entries] != [f"course-{number:02d}" for number in range(1, 34)]:
        raise CatalogCoverSeedBlocked("fixed cover slugs must be course-01 through course-33 in order")
    return {"schemaVersion": "1.0", "entries": entries}


def execute_cover_seed_plan(repository_root: Path, api: Any) -> dict:
    repository_root = Path(repository_root).resolve()
    plan = build_cover_seed_plan(repository_root)
    approved_uploads = []
    for entry in plan["entries"]:
        upload = api.plan_asset_upload(
            entry["slug"],
            entry["relativePath"],
            entry["contentType"],
            entry["sizeBytes"],
        )
        if (
            not isinstance(upload, dict)
            or not isinstance(upload.get("putUrl"), str)
            or upload.get("objectKey") != entry["objectKey"]
            or upload.get("requiredContentType") != entry["contentType"]
            or not isinstance(upload.get("maxBytes"), int)
            or isinstance(upload.get("maxBytes"), bool)
            or upload["maxBytes"] < entry["sizeBytes"]
        ):
            raise CatalogCoverSeedBlocked(
                f"{entry['slug']} server upload plan changed the fixed object key, content type, or size limit"
            )
        approved_uploads.append((entry, upload))
    for entry, upload in approved_uploads:
        api.upload_asset(
            upload["putUrl"],
            repository_root / entry["sourcePath"],
            upload["requiredContentType"],
        )
    return {"planned": len(plan["entries"]), "uploaded": len(approved_uploads)}
