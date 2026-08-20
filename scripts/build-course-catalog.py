#!/usr/bin/env python3
"""Build the pinned teacher-facing 33-course catalog from its reviewed Markdown."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/2026-08-19-courses.md"
OUTPUT = ROOT / "course_toolkit/course_catalog.json"

CATEGORY_SLUGS = {
    "立场与价值": "stance-value",
    "信源核查": "source-check",
    "媒介与信息素养": "media-literacy",
    "自我认知": "self-knowledge",
    "数据素养": "data-literacy",
    "研究流程": "research-process",
    "论证写作": "argument-writing",
}

CARD_IDS = {
    "AI 边界与幻觉核查卡": "ai-boundary",
    "负责任使用 AI 决策树卡": "ai-decision-tree",
    "论证地图卡（结构 + 谬误）": "argument-map",
    "立场光谱卡": "belief-spectrum",
    "话语分析卡 CDA": "cda",
    "让步段·以退为进": "concession",
    "信源辨识卡 CRAAP/CRRAAB": "craap",
    "信源辨识卡 CRAAP": "craap",
    "数据与统计素养卡": "data-literacy",
    "情感对齐卡（内在小人·情绪电量）": "emotional-alignment",
    "情感对齐卡": "emotional-alignment",
    "伦理判断三镜头卡": "ethics-lenses",
    "事实/观点/价值判断卡": "fact-opinion-value",
    "认知者视角·自欺自审卡": "knower-perspective",
    "学习报告·AI 使用声明卡": "learning-report",
    "元认知收口卡": "metacognition",
    "资金链溯源卡": "money-trail",
    "多模态解构卡": "multimodal-decode",
    "OPCVL 史料评估卡": "opcvl",
    "PEE 写作卡": "pee",
    "视角对照矩阵": "perspective-matrix",
    "提问卡": "question-card",
    "兔子洞·兴趣雷达卡": "rabbit-hole",
    "检索方向审视": "search-plan",
    "横向核查卡 SIFT": "sift",
    "营销与否认套路卡（漂绿 + FLICC）": "spin-detector",
    "论证构建卡（图尔敏）": "toulmin",
}


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_bold(value: str) -> str:
    return clean(value.replace("**", ""))


def parse_classification(text: str) -> dict[int, dict]:
    section = text.split("## 分类", 1)[1].split("# 逐门课程", 1)[0]
    rows: dict[int, dict] = {}
    for line in section.splitlines():
        if not re.match(r"^\|\s*\d+\s*\|", line):
            continue
        cells = [clean(cell) for cell in line.strip().strip("|").split("|")]
        number = int(cells[0])
        title = cells[1]
        category_label = re.sub(r"^[^\w\u4e00-\u9fff]+", "", cells[2]).strip()
        if category_label not in CATEGORY_SLUGS:
            raise ValueError(f"unknown category for course {number}: {cells[2]}")
        card_names = [clean(name) for name in cells[3].split("、") if clean(name)]
        try:
            card_ids = [CARD_IDS[name] for name in card_names]
        except KeyError as exc:
            raise ValueError(f"unknown card name for course {number}: {exc.args[0]}") from exc
        rows[number] = {
            "catalogId": f"course-{number:02d}",
            "title": title,
            "category": CATEGORY_SLUGS[category_label],
            "cardIds": card_ids,
        }
    if set(rows) != set(range(1, 34)):
        raise ValueError("classification table must contain courses 1 through 33 exactly once")
    return rows


def labelled_value(section: str, label: str) -> str:
    pattern = rf"\*\*{re.escape(label)}(?:\*\*)?\s*[：:]\s*(.*)"
    match = re.search(pattern, section)
    if not match:
        raise ValueError(f"missing {label}")
    return strip_bold(match.group(1))


def parse_alignment(section: str) -> dict[str, list[str]]:
    alignment = {"ib": [], "otherIntl": [], "domestic": []}
    label_keys = {
        "IB": "ib",
        "其他国际": "otherIntl",
        "其他国际课程": "otherIntl",
        "国际学校": "otherIntl",
        "国内": "domestic",
    }
    for line in section.splitlines():
        plain = strip_bold(line).lstrip("· ").strip()
        match = re.match(r"(IB|其他国际课程|其他国际|国际学校|国内)\s*[：:]\s*(.+)", plain)
        if match:
            alignment[label_keys[match.group(1)]].append(clean(match.group(2)))
    return alignment


def parse_keywords(section: str) -> list[str]:
    match = re.search(r"\*\*关键词(?:\*\*)?\s*[：:]\s*(.+)", section)
    if not match:
        match = re.search(r"^关键词\s*\n\s*\n?(.+)$", section, flags=re.MULTILINE)
    if not match:
        raise ValueError("missing keywords")
    return [clean(item) for item in match.group(1).split("｜") if clean(item)]


def parse_course_sections(text: str, rows: dict[int, dict]) -> list[dict]:
    matches = list(re.finditer(r"^## (\d+)\.\s*(.+)$", text, flags=re.MULTILINE))
    if len(matches) != 33:
        raise ValueError(f"expected 33 detailed course sections, got {len(matches)}")
    courses = []
    for index, match in enumerate(matches):
        number = int(match.group(1))
        section_title = clean(match.group(2))
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end():end].strip()
        student_marker = re.search(r"\*\*学生做什么", body)
        takeaway_marker = re.search(r"^### 带走什么", body, flags=re.MULTILINE)
        alignment_marker = re.search(r"^### 学科对标(?:说明)?", body, flags=re.MULTILINE)
        if not (student_marker and takeaway_marker and alignment_marker):
            raise ValueError(f"course {number} is missing a required introduction section")
        hook = clean(body[:student_marker.start()])
        what_you_do = labelled_value(body, "学生做什么")
        takeaway_region = body[takeaway_marker.end():alignment_marker.start()]
        takeaways = [clean(line.lstrip("· ")) for line in takeaway_region.splitlines() if line.strip().startswith("·")]
        if not hook or not what_you_do or not takeaways:
            raise ValueError(f"course {number} has an incomplete introduction")

        course = dict(rows[number])
        aliases = []
        if section_title != course["title"]:
            aliases.append(section_title)
        if number == 33:
            aliases.extend(["AI伦理", "AI 伦理", "AI 公司的“焚书坑儒”：谁为 AI 付了账？"])
        course["aliases"] = list(dict.fromkeys(aliases))
        course["introduction"] = {
            "hook": hook,
            "whatYouDo": what_you_do,
            "takeaways": takeaways,
            "alignment": parse_alignment(body[alignment_marker.start():]),
            "keywords": parse_keywords(body[alignment_marker.start():]),
        }
        courses.append(course)
    return courses


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the pinned 33-course catalog from docs/2026-08-19-courses.md"
    )
    parser.parse_args()
    text = SOURCE.read_text(encoding="utf-8")
    rows = parse_classification(text)
    catalog = {
        "schemaVersion": "1.0",
        "studentAuthoringTag": "course-authoring-v1.4.0",
        "source": {
            "path": "docs/2026-08-19-courses.md",
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        },
        "courses": parse_course_sections(text, rows),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(catalog['courses'])} courses to {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
