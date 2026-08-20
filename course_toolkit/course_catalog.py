"""Deterministic binding between a teacher course and the reviewed 33-course catalog."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from copy import deepcopy
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .jsonio import load_json, write_json_atomic


CATALOG_PATH = Path(__file__).with_name("course_catalog.json")
SELECTION_PATH = Path(".course-work/course-catalog-selection.json")
VALID_CATEGORIES = {
    "stance-value",
    "source-check",
    "media-literacy",
    "self-knowledge",
    "data-literacy",
    "research-process",
    "argument-writing",
}


class CourseCatalogError(ValueError):
    pass


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _entry_hash(course: dict) -> str:
    return hashlib.sha256(_canonical_json(course)).hexdigest()


def _normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = value.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "—": "-", "–": "-"}))
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value)


def _validate_introduction(value: Any, *, catalog_id: str) -> None:
    if not isinstance(value, dict) or set(value) != {"hook", "whatYouDo", "takeaways", "alignment", "keywords"}:
        raise CourseCatalogError(f"{catalog_id} has an invalid introduction")
    if not isinstance(value["hook"], str) or not value["hook"].strip():
        raise CourseCatalogError(f"{catalog_id} has an empty introduction hook")
    if not isinstance(value["whatYouDo"], str) or not value["whatYouDo"].strip():
        raise CourseCatalogError(f"{catalog_id} has an empty whatYouDo")
    for key in ("takeaways", "keywords"):
        if not isinstance(value[key], list) or not value[key] or not all(isinstance(item, str) and item.strip() for item in value[key]):
            raise CourseCatalogError(f"{catalog_id} has invalid {key}")
    alignment = value["alignment"]
    if not isinstance(alignment, dict) or set(alignment) != {"ib", "otherIntl", "domestic"}:
        raise CourseCatalogError(f"{catalog_id} has invalid alignment")
    if not all(isinstance(items, list) and all(isinstance(item, str) and item.strip() for item in items) for items in alignment.values()):
        raise CourseCatalogError(f"{catalog_id} has invalid alignment entries")


def load_course_catalog() -> dict:
    try:
        catalog = load_json(CATALOG_PATH)
    except ValueError as exc:
        raise CourseCatalogError(str(exc)) from exc
    if not isinstance(catalog, dict) or catalog.get("schemaVersion") != "1.0":
        raise CourseCatalogError("the 33-course catalog has an unsupported schema")
    if catalog.get("studentAuthoringTag") != "course-authoring-v1.4.0":
        raise CourseCatalogError("the 33-course catalog is not pinned to course-authoring-v1.4.0")
    courses = catalog.get("courses")
    if not isinstance(courses, list) or len(courses) != 33:
        raise CourseCatalogError("the 33-course catalog must contain exactly 33 courses")
    seen_ids: set[str] = set()
    for course in courses:
        if not isinstance(course, dict):
            raise CourseCatalogError("the 33-course catalog contains an invalid course")
        catalog_id = course.get("catalogId")
        if not isinstance(catalog_id, str) or catalog_id in seen_ids:
            raise CourseCatalogError("the 33-course catalog contains a duplicate or invalid catalogId")
        seen_ids.add(catalog_id)
        if course.get("category") not in VALID_CATEGORIES:
            raise CourseCatalogError(f"{catalog_id} has an invalid category")
        if not isinstance(course.get("title"), str) or not course["title"].strip():
            raise CourseCatalogError(f"{catalog_id} has an invalid title")
        if not isinstance(course.get("aliases"), list) or not all(isinstance(item, str) for item in course["aliases"]):
            raise CourseCatalogError(f"{catalog_id} has invalid aliases")
        if not isinstance(course.get("cardIds"), list) or not course["cardIds"] or not all(isinstance(item, str) for item in course["cardIds"]):
            raise CourseCatalogError(f"{catalog_id} has invalid cardIds")
        _validate_introduction(course.get("introduction"), catalog_id=catalog_id)
    return catalog


def propose_course_matches(query: str, *, limit: int = 5) -> list[dict]:
    if not isinstance(query, str) or not query.strip():
        raise CourseCatalogError("a course name is required before proposing catalog matches")
    normalized_query = _normalize_title(query)
    proposals = []
    for course in load_course_catalog()["courses"]:
        names = [course["title"], *course["aliases"]]
        if query.strip() in names:
            match_kind = "exact"
            score = 1.0
        elif normalized_query in {_normalize_title(name) for name in names}:
            match_kind = "normalized"
            score = 0.99
        else:
            score = max(SequenceMatcher(None, normalized_query, _normalize_title(name)).ratio() for name in names)
            match_kind = "fuzzy"
        proposals.append({
            "catalogId": course["catalogId"],
            "title": course["title"],
            "category": course["category"],
            "matchKind": match_kind,
            "score": round(score, 4),
            "teacherConfirmed": False,
        })
    proposals.sort(key=lambda item: (-item["score"], item["catalogId"]))
    return proposals[:limit]


def _find_course(catalog_id: str) -> dict:
    for course in load_course_catalog()["courses"]:
        if course["catalogId"] == catalog_id:
            return course
    raise CourseCatalogError(f"unknown 33-course catalog selection: {catalog_id}")


def confirm_course_selection(
    root: Path,
    catalog_id: str,
    *,
    teacher_response: str,
    confirmed_at: str,
) -> dict:
    if not isinstance(teacher_response, str) or not teacher_response.strip():
        raise CourseCatalogError("teacher confirmation is required for the 33-course catalog selection")
    if not isinstance(confirmed_at, str) or not confirmed_at.strip():
        raise CourseCatalogError("confirmed_at is required")
    course = _find_course(catalog_id)
    selection = {
        "schemaVersion": "1.0",
        "catalogId": course["catalogId"],
        "title": course["title"],
        "category": course["category"],
        "cardIds": deepcopy(course["cardIds"]),
        "introduction": deepcopy(course["introduction"]),
        "catalogHash": _entry_hash(course),
        "teacherConfirmed": True,
        "teacherResponse": teacher_response.strip(),
        "confirmedAt": confirmed_at,
    }
    write_json_atomic(Path(root) / SELECTION_PATH, selection)
    return selection


def load_confirmed_course_selection(root: Path) -> dict:
    path = Path(root) / SELECTION_PATH
    if not path.is_file():
        raise CourseCatalogError("publication requires a teacher-confirmed selection from the 33-course catalog")
    try:
        selection = load_json(path)
    except ValueError as exc:
        raise CourseCatalogError(str(exc)) from exc
    if not isinstance(selection, dict) or selection.get("teacherConfirmed") is not True:
        raise CourseCatalogError("the 33-course catalog selection is not teacher-confirmed")
    course = _find_course(selection.get("catalogId"))
    expected = {
        "title": course["title"],
        "category": course["category"],
        "cardIds": course["cardIds"],
        "introduction": course["introduction"],
        "catalogHash": _entry_hash(course),
    }
    if any(selection.get(key) != value for key, value in expected.items()):
        raise CourseCatalogError("the confirmed catalog course changed; ask the teacher to review and confirm it again")
    return selection
