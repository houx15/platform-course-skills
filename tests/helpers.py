import struct
from pathlib import Path

from course_toolkit.course_design import (
    OVERALL_CHECKS,
    REVIEW_DIMENSIONS,
    render_review_report,
    render_storyboard,
)
from course_toolkit.jsonio import dump_json


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ROOT = ROOT


def write_test_mp4(path: Path, duration_seconds: float = 32.533333) -> Path:
    timescale = 30_000
    duration = round(duration_seconds * timescale)
    mvhd_payload = b"\x00\x00\x00\x00" + struct.pack(
        ">IIII",
        0,
        0,
        timescale,
        duration,
    )
    mvhd = struct.pack(">I4s", 8 + len(mvhd_payload), b"mvhd") + mvhd_payload
    moov = struct.pack(">I4s", 8 + len(mvhd), b"moov") + mvhd
    ftyp_payload = b"isom" + struct.pack(">I", 0x200) + b"isomiso2"
    ftyp = struct.pack(">I4s", 8 + len(ftyp_payload), b"ftyp") + ftyp_payload

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ftyp + moov)
    return path


def write_test_pdf(path: Path, *, header: bool = True, eof: bool = True) -> Path:
    content = b"%PDF-1.4\n" if header else b"not-a-pdf\n"
    content += b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    if eof:
        content += b"%%EOF\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def minimal_course():
    return {
        "schemaVersion": "1.0",
        "course": {
            "id": "sample-course",
            "title": "样例课程",
            "language": "zh-CN",
            "parts": [
                {
                    "id": "part-1",
                    "title": "第一部分",
                    "pieces": [
                        {
                            "id": "piece-1",
                            "title": "第一内容块",
                            "blocks": [
                                {
                                    "id": "intro",
                                    "type": "text",
                                    "content": "课程内容",
                                }
                            ],
                        }
                    ],
                }
            ],
        },
    }


def storyboard_for_course(course_data):
    parts = []
    piece_count = 0
    for part in course_data["course"]["parts"]:
        pieces = []
        for piece in part["pieces"]:
            piece_count += 1
            pieces.append(
                {
                    "id": piece["id"],
                    "title": piece["title"],
                    "studentSees": f"面向学生呈现《{piece['title']}》的完整学习内容",
                    "teachingFocus": "帮助学生理解并应用本 Piece 的关键内容",
                    "modalities": sorted(
                        {
                            block["type"]
                            for block in piece["blocks"]
                            if isinstance(block, dict) and "type" in block
                        }
                    ),
                    "studentAction": "阅读、观察或完成当前 Piece 的学习活动",
                    "completion": "完成规定活动并留下相应学习证据",
                    "sourceIds": ["source-1"],
                    "assetNeeds": [],
                    "pendingConfirmations": [],
                }
            )
        parts.append(
            {
                "id": part["id"],
                "title": part["title"],
                "stageGoal": f"完成《{part['title']}》对应的阶段学习目标",
                "pieces": pieces,
            }
        )
    return {
        "schemaVersion": "1.0",
        "teacherConfirmed": True,
        "summary": {
            "partCount": len(parts),
            "pieceCount": piece_count,
        },
        "parts": parts,
    }


def review_report_for_course(course_data):
    part_reviews = []
    for part in course_data["course"]["parts"]:
        part_reviews.append(
            {
                "partId": part["id"],
                "partTitle": part["title"],
                "dimensions": {
                    dimension: {
                        "status": "pass",
                        "evidence": f"{dimension} 已逐项核查",
                    }
                    for dimension in REVIEW_DIMENSIONS
                },
                "conclusion": "pass",
                "recommendations": [],
            }
        )
    return {
        "schemaVersion": "1.0",
        "partReviews": part_reviews,
        "overallChecks": {
            check: {
                "status": "pass",
                "evidence": f"{check} 已核查",
            }
            for check in OVERALL_CHECKS
        },
        "finalStatus": "uploadable",
    }


def write_valid_work_records(work_root: Path, course_data: dict) -> None:
    work_root.mkdir(parents=True, exist_ok=True)
    first_part = course_data["course"]["parts"][0]
    first_piece = first_part["pieces"][0]
    first_block = first_piece["blocks"][0]
    extracted = {
        "items": [
            {
                "sourceId": "source-1",
                "sourceFile": "lesson.docx",
                "location": "paragraph:1",
                "kind": "paragraph",
                "text": "课程原始内容",
            }
        ],
        "ignored": [],
        "unsupported": [],
        "errors": [],
    }
    coverage = {
        "schemaVersion": "1.0",
        "items": [
            {
                "sourceId": "source-1",
                "sourceFile": "lesson.docx",
                "location": "paragraph:1",
                "summary": "课程原始内容",
                "status": "mapped",
                "destinations": [
                    f"{first_part['id']}/{first_piece['id']}/{first_block['id']}"
                ],
            }
        ],
    }
    audience = {
        "schemaVersion": "1.0",
        "teacherConfirmed": True,
        "groups": [
            {
                "audience": "student-core",
                "sourceIds": ["source-1"],
                "summary": "学生需要学习的课程核心内容",
                "disposition": "storyboard",
            }
        ],
    }
    storyboard = storyboard_for_course(course_data)
    review = review_report_for_course(course_data)
    records = {
        "materials-extracted.json": extracted,
        "source-coverage.json": coverage,
        "audience-classification.json": audience,
        "course-storyboard.json": storyboard,
        "decisions.json": {"schemaVersion": "1.0", "decisions": []},
        "unresolved.json": {"schemaVersion": "1.0", "items": []},
        "session.json": {"schemaVersion": "1.0", "state": "review"},
        "review-report.json": review,
    }
    for name, data in records.items():
        (work_root / name).write_text(dump_json(data), encoding="utf-8")
    (work_root / "course-storyboard.md").write_text(
        render_storyboard(storyboard),
        encoding="utf-8",
    )
    (work_root / "review-report.md").write_text(
        render_review_report(review),
        encoding="utf-8",
    )
