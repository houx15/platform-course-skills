import copy
import struct
from pathlib import Path
from typing import Optional

from course_toolkit.course_design import (
    OVERALL_CHECKS,
    REVIEW_DIMENSIONS,
    render_review_report,
    render_storyboard,
)
from course_toolkit.jsonio import dump_json
from course_toolkit.html_reports import build_html_report, render_html_report


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ROOT = ROOT


def _mp4_box(box_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), box_type) + payload


def _mp4_track(handler_type: bytes, codec: bytes) -> bytes:
    handler = _mp4_box(
        b"hdlr",
        b"\x00\x00\x00\x00" + struct.pack(">I", 0) + handler_type + b"\x00" * 12,
    )
    sample_entry = _mp4_box(codec, b"")
    sample_description = _mp4_box(
        b"stsd",
        b"\x00\x00\x00\x00" + struct.pack(">I", 1) + sample_entry,
    )
    sample_table = _mp4_box(b"stbl", sample_description)
    media_information = _mp4_box(b"minf", sample_table)
    media = _mp4_box(b"mdia", handler + media_information)
    return _mp4_box(b"trak", media)


def write_test_mp4(
    path: Path,
    duration_seconds: float = 32.533333,
    *,
    video_codec: bytes = b"avc1",
    audio_codec: Optional[bytes] = b"mp4a",
    faststart: bool = True,
) -> Path:
    timescale = 30_000
    duration = round(duration_seconds * timescale)
    mvhd_payload = b"\x00\x00\x00\x00" + struct.pack(
        ">IIII",
        0,
        0,
        timescale,
        duration,
    )
    mvhd = _mp4_box(b"mvhd", mvhd_payload)
    tracks = _mp4_track(b"vide", video_codec)
    if audio_codec is not None:
        tracks += _mp4_track(b"soun", audio_codec)
    moov = _mp4_box(b"moov", mvhd + tracks)
    ftyp_payload = b"isom" + struct.pack(">I", 0x200) + b"isomiso2"
    ftyp = _mp4_box(b"ftyp", ftyp_payload)
    mdat = _mp4_box(b"mdat", b"\x00")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ftyp + (moov + mdat if faststart else mdat + moov))
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
        "schemaVersion": "1.1",
        "course": {
            "id": "sample-course",
            "title": "样例课程",
            "language": "zh-CN",
            "introduction": {
                "overview": "这门课帮助你理解课程内容，并用一个练习检查自己的理解。",
                "objectives": [
                    {
                        "id": "explain-course-content",
                        "text": "解释课程的关键内容，并用自己的话完成一次应用",
                    }
                ],
                "keyPoints": ["识别关键内容", "用自己的话进行应用"],
            },
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
                                },
                                {
                                    "id": "course-content-response",
                                    "type": "fillBlank",
                                    "blocking": True,
                                    "prompt": "请用自己的话说明课程内容。",
                                    "assessment": {
                                        "mode": "reflection",
                                        "rubric": "回答应准确说明课程的关键内容。",
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
            "conclusion": {
                "summary": "本课介绍课程内容，并安排一次应用练习来检查理解。",
                "takeaways": ["先识别关键内容", "再用自己的话应用所学"],
                "transferApplications": ["后续课程学习"],
            },
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
    evidence_blocks = []
    part_ids = []
    for part in course_data["course"]["parts"]:
        part_ids.append(part["id"])
        for piece in part["pieces"]:
            for block in piece["blocks"]:
                if block.get("type") in {"fillBlank", "singleChoice", "interactiveHtml"}:
                    evidence_blocks.append(block["id"])
                elif block.get("type") == "video" and isinstance(block.get("interaction"), dict):
                    evidence_blocks.append(block["id"])
    first_evidence = evidence_blocks[0] if evidence_blocks else "missing-evidence"
    return {
        "schemaVersion": "1.0",
        "teacherConfirmed": True,
        "courseFrame": {
            "teacherConfirmed": True,
            "introduction": copy.deepcopy(course_data["course"]["introduction"]),
            "conclusion": copy.deepcopy(course_data["course"]["conclusion"]),
            "sourceIds": ["source-1"],
            "objectiveAlignment": [
                {
                    "objectiveId": objective["id"],
                    "partIds": part_ids,
                    "evidenceBlockIds": [first_evidence],
                }
                for objective in course_data["course"]["introduction"]["objectives"]
            ],
            "pendingConfirmations": [],
        },
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


def write_html_reports_for_course(
    course_root: Path,
    work_root: Path,
    course_data: dict,
) -> None:
    report_root = work_root / "html-reports"
    for part in course_data["course"]["parts"]:
        for piece in part["pieces"]:
            for block in piece["blocks"]:
                if block.get("type") != "interactiveHtml":
                    continue
                block_id = block["id"]
                source = block["source"]
                html_path = course_root / source
                report = build_html_report(block_id, source, html_path)
                report_root.mkdir(parents=True, exist_ok=True)
                (report_root / f"{block_id}.json").write_text(
                    dump_json(report),
                    encoding="utf-8",
                )
                (report_root / f"{block_id}.md").write_text(
                    render_html_report(report),
                    encoding="utf-8",
                )
