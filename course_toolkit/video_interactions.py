import re
from pathlib import Path
from typing import List, Optional, Set

from .errors import ValidationIssue
from .mp4 import read_mp4_duration
from .paths import resolve_course_path


ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def format_time(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _issue(path: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(path, code, message)


def _validate_interaction(
    value: object,
    path: str,
    issues: List[ValidationIssue],
) -> None:
    if not isinstance(value, dict):
        issues.append(_issue(path, "required", "interaction must be an object"))
        return
    interaction_type = value.get("type")
    if interaction_type not in {"singleChoice", "fillBlank"}:
        issues.append(_issue(f"{path}.type", "unsupported-type", "unsupported interaction"))
    assessment = value.get("assessment")
    if not isinstance(assessment, dict) or assessment.get("mode") not in {
        "graded",
        "survey",
        "reflection",
    }:
        issues.append(_issue(f"{path}.assessment", "required", "assessment mode is required"))
    if interaction_type == "singleChoice":
        options = value.get("options")
        if not isinstance(options, list) or len(options) < 2:
            issues.append(_issue(f"{path}.options", "required", "two options are required"))


def validate_video_interactions(
    data: object,
    course_root: Path,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    if not isinstance(data, dict):
        return [_issue("$", "required", "video interaction data must be an object")]
    if data.get("schemaVersion") != "1.0":
        issues.append(_issue("schemaVersion", "invalid-version", "schemaVersion must be 1.0"))
    video = data.get("video")
    if not isinstance(video, dict):
        issues.append(_issue("video", "required", "video object is required"))
        return issues
    source = video.get("source")
    actual_duration: Optional[float] = None
    if not isinstance(source, str) or not source.strip():
        issues.append(_issue("video.source", "required", "video source is required"))
    else:
        try:
            video_path = resolve_course_path(course_root, source)
            if not video_path.is_file():
                issues.append(
                    _issue("video.source", "missing-file", f"video does not exist: {source}")
                )
            else:
                actual_duration = read_mp4_duration(video_path)
        except ValueError as exc:
            issues.append(_issue("video.source", "invalid-video", str(exc)))

    declared_duration = video.get("durationSeconds")
    if actual_duration is not None:
        if not isinstance(declared_duration, (int, float)) or isinstance(
            declared_duration,
            bool,
        ):
            issues.append(
                _issue(
                    "video.durationSeconds",
                    "required",
                    "final video requires durationSeconds",
                )
            )
        elif abs(float(declared_duration) - actual_duration) > 1:
            issues.append(
                _issue(
                    "video.durationSeconds",
                    "duration-mismatch",
                    "declared duration differs from MP4 duration",
                )
            )

    events = video.get("events")
    if not isinstance(events, list) or not events:
        issues.append(_issue("video.events", "required", "at least one event is required"))
        return issues

    seen_ids: Set[str] = set()
    seen_times: Set[float] = set()
    previous_time: Optional[float] = None
    for index, event_value in enumerate(events):
        path = f"video.events[{index}]"
        if not isinstance(event_value, dict):
            issues.append(_issue(path, "required", "event must be an object"))
            continue
        event_id = event_value.get("id")
        if not isinstance(event_id, str) or not ID_RE.fullmatch(event_id):
            issues.append(_issue(f"{path}.id", "invalid-id", "event id is invalid"))
        elif event_id in seen_ids:
            issues.append(_issue(f"{path}.id", "duplicate-id", "event id is repeated"))
        else:
            seen_ids.add(event_id)
        if not isinstance(event_value.get("prompt"), str) or not event_value["prompt"].strip():
            issues.append(_issue(f"{path}.prompt", "required", "event prompt is required"))
        if not isinstance(event_value.get("blocking"), bool):
            issues.append(_issue(f"{path}.blocking", "required", "blocking must be boolean"))
        _validate_interaction(event_value.get("interaction"), f"{path}.interaction", issues)

        if event_value.get("status") == "needs-timing":
            if event_value.get("timeSeconds") is not None:
                issues.append(
                    _issue(f"{path}.timeSeconds", "invalid-value", "provisional time must be null")
                )
            if not isinstance(event_value.get("anchor"), str) or not event_value[
                "anchor"
            ].strip():
                issues.append(_issue(f"{path}.anchor", "required", "semantic anchor is required"))
            issues.append(_issue(path, "needs-timing", "event needs final MP4 timing"))
            continue

        current_time = event_value.get("timeSeconds")
        if not isinstance(current_time, (int, float)) or isinstance(current_time, bool):
            issues.append(_issue(f"{path}.timeSeconds", "required", "event time is required"))
            continue
        current_time = float(current_time)
        if current_time < 0:
            issues.append(_issue(f"{path}.timeSeconds", "invalid-value", "time cannot be negative"))
        if current_time in seen_times:
            issues.append(_issue(f"{path}.timeSeconds", "time-conflict", "event time is repeated"))
        if previous_time is not None and current_time < previous_time:
            issues.append(
                _issue(f"{path}.timeSeconds", "time-order", "event times must increase")
            )
        if actual_duration is not None and current_time >= actual_duration:
            issues.append(
                _issue(
                    f"{path}.timeSeconds",
                    "time-out-of-range",
                    f"{current_time:g}s is outside {actual_duration:.3f}s video",
                )
            )
        seen_times.add(current_time)
        previous_time = current_time
    return issues


def _render_event(event: dict) -> List[str]:
    interaction = event["interaction"]
    assessment = interaction["assessment"]
    lines = [
        f"- 提示：{event['prompt']}",
        f"- 阻塞：{'是' if event['blocking'] else '否'}",
        f"- 类型：{interaction['type']}",
    ]
    if event.get("anchor"):
        lines.append(f"- 语义锚点：{event['anchor']}")
    if interaction.get("options"):
        lines.append("- 选项：")
        for option in interaction["options"]:
            lines.append(f"  - {option['id']}：{option['label']}")
    lines.append(f"- 评价模式：{assessment['mode']}")
    for key, label in (
        ("correctOptionId", "正确选项"),
        ("rubric", "评价要求"),
        ("correctFeedback", "正确反馈"),
        ("incorrectFeedback", "错误反馈"),
    ):
        if assessment.get(key):
            lines.append(f"- {label}：{assessment[key]}")
    if assessment.get("acceptedAnswers"):
        lines.append(f"- 可接受答案：{'；'.join(assessment['acceptedAnswers'])}")
    return lines


def render_video_interactions(data: dict) -> str:
    video = data["video"]
    lines = [f"# {video.get('title', '视频交互设计')}", ""]
    for event in video["events"]:
        label = (
            "待对齐"
            if event.get("timeSeconds") is None
            else format_time(float(event["timeSeconds"]))
        )
        lines.extend([f"## {label}", ""])
        lines.extend(_render_event(event))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
