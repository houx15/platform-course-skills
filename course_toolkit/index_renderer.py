from typing import Callable, Dict, List


def _blocking(value: bool) -> str:
    return "是" if value else "否"


def _render_text(block: dict) -> List[str]:
    return ["[文字]", "", block["content"]]


def _render_images(block: dict) -> List[str]:
    lines = ["[图片]", ""]
    for item in block["items"]:
        lines.append(f"![{item['alt']}]({item['source']})")
    return lines


def _render_pdf(block: dict) -> List[str]:
    return [
        "[PDF]",
        "",
        f"- 标题：{block['title']}",
        f"- 文件：[查看或下载完整 PDF]({block['source']})",
    ]


def _render_video(block: dict) -> List[str]:
    lines = [
        "[视频]",
        "",
        f"- 阻塞：{_blocking(block['blocking'])}",
        f"- 内容：{block['source']}",
    ]
    interaction = block.get("interaction")
    if interaction:
        lines.extend(
            [
                f"- 交互数据：{interaction['data']}",
                f"- 交互文档：{interaction['document']}",
            ]
        )
    completion = block.get("completion")
    if completion:
        lines.append(f"- 完成规则：{completion['rule']}")
    return lines


def _render_html(block: dict) -> List[str]:
    lines = [
        "[交互]",
        "",
        f"- 阻塞：{_blocking(block['blocking'])}",
        f"- 内容：{block['source']}",
    ]
    if block.get("completion"):
        lines.append(f"- 完成规则：{block['completion']['rule']}")
    return lines


def _render_fill_blank(block: dict) -> List[str]:
    assessment = block["assessment"]
    lines = [
        "[填空]",
        "",
        f"- 阻塞：{_blocking(block['blocking'])}",
        f"- 题目：{block['prompt']}",
        f"- 评价模式：{assessment['mode']}",
    ]
    if assessment["mode"] == "graded":
        lines.append(f"- 可接受答案：{'；'.join(assessment['acceptedAnswers'])}")
        lines.append(
            f"- 区分大小写：{_blocking(assessment.get('caseSensitive', False))}"
        )
    else:
        lines.append(f"- 评价要求：{assessment['rubric']}")
    if assessment.get("correctFeedback"):
        lines.append(f"- 正确反馈：{assessment['correctFeedback']}")
    if assessment.get("incorrectFeedback"):
        lines.append(f"- 错误反馈：{assessment['incorrectFeedback']}")
    if block.get("completion"):
        lines.append(f"- 完成规则：{block['completion']['rule']}")
    return lines


def _render_single_choice(block: dict) -> List[str]:
    assessment = block["assessment"]
    lines = [
        "[选择]",
        "",
        f"- 阻塞：{_blocking(block['blocking'])}",
        f"- 题目：{block['prompt']}",
        "- 选项：",
    ]
    for option in block["options"]:
        lines.append(f"  - {option['id']}：{option['label']}")
    lines.append(f"- 评价模式：{assessment['mode']}")
    if assessment["mode"] == "graded":
        lines.append(f"- 正确选项：{assessment['correctOptionId']}")
    if assessment.get("correctFeedback"):
        lines.append(f"- 正确反馈：{assessment['correctFeedback']}")
    if assessment.get("incorrectFeedback"):
        lines.append(f"- 错误反馈：{assessment['incorrectFeedback']}")
    if block.get("completion"):
        lines.append(f"- 完成规则：{block['completion']['rule']}")
    return lines


RENDERERS: Dict[str, Callable[[dict], List[str]]] = {
    "text": _render_text,
    "images": _render_images,
    "pdf": _render_pdf,
    "video": _render_video,
    "interactiveHtml": _render_html,
    "fillBlank": _render_fill_blank,
    "singleChoice": _render_single_choice,
}


def render_index(data: dict) -> str:
    course = data["course"]
    lines: List[str] = [f"# {course['title']}", ""]
    for part in course["parts"]:
        lines.extend([f"## {part['title']}", ""])
        for piece in part["pieces"]:
            lines.extend([f"### {piece['title']}", ""])
            for block in piece["blocks"]:
                renderer = RENDERERS[block["type"]]
                lines.extend(renderer(block))
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"
