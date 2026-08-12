import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Set, Tuple

from .errors import ValidationIssue
from .mp4 import Mp4Profile, inspect_mp4
from .paths import resolve_course_path


ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LONG_VIDEO_SECONDS = 600
LARGE_VIDEO_BYTES = 500 * 1024 * 1024


@dataclass(frozen=True)
class VideoInspectionResult:
    issues: Tuple[ValidationIssue, ...]
    warnings: Tuple[ValidationIssue, ...]
    profile: Optional[Mp4Profile]


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


def _probe_with_ffprobe(path: Path) -> Optional[dict]:
    executable = shutil.which("ffprobe")
    if executable is None:
        return None
    try:
        completed = subprocess.run(
            [
                executable,
                "-v",
                "error",
                "-show_entries",
                "format=format_name,duration,size:stream=codec_type,codec_name",
                "-of",
                "json",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if completed.returncode != 0:
            return None
        payload = json.loads(completed.stdout)
        format_data = payload.get("format", {})
        streams = payload.get("streams", [])
        if not isinstance(format_data, dict) or not isinstance(streams, list):
            return None
        names = tuple(
            item.strip()
            for item in str(format_data.get("format_name", "")).split(",")
            if item.strip()
        )
        videos = tuple(
            str(stream.get("codec_name", ""))
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        )
        audios = tuple(
            str(stream.get("codec_name", ""))
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "audio"
        )
        return {
            "format_names": names,
            "video_codecs": videos,
            "audio_codecs": audios,
            "duration_seconds": float(format_data["duration"]),
            "size_bytes": int(format_data["size"]),
        }
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        return None


def inspect_video_file(
    path: Path,
    source: str,
    event_times: Sequence[float] = (),
) -> VideoInspectionResult:
    issues: List[ValidationIssue] = []
    warnings: List[ValidationIssue] = []
    if path.suffix.lower() != ".mp4":
        issues.append(
            _issue(source, "invalid-video-container", "video must use the .mp4 container")
        )
        return VideoInspectionResult(tuple(issues), tuple(warnings), None)
    try:
        profile = inspect_mp4(path)
    except ValueError as exc:
        issues.append(
            _issue(source, "video-profile-unverified", f"cannot verify MP4 profile: {exc}")
        )
        return VideoInspectionResult(tuple(issues), tuple(warnings), None)

    probe = _probe_with_ffprobe(path)
    if probe is not None:
        probe_video = tuple(probe["video_codecs"])
        probe_audio = tuple(probe["audio_codecs"])
        if "mp4" not in probe["format_names"]:
            issues.append(
                _issue(
                    source,
                    "invalid-video-container",
                    "ffprobe does not identify an MP4 container",
                )
            )
        if not probe_video:
            issues.append(
                _issue(source, "video-profile-unverified", "ffprobe found no video track")
            )
        elif any(codec != "h264" for codec in probe_video) and all(
            codec == "h264" for codec in profile.video_codecs
        ):
            issues.append(
                _issue(source, "unsupported-video-codec", "ffprobe requires H.264 video")
            )
        if any(codec != "aac" for codec in probe_audio) and all(
            codec == "aac" for codec in profile.audio_codecs
        ):
            issues.append(
                _issue(source, "unsupported-audio-codec", "ffprobe requires AAC audio")
            )
        conflict_fields = []
        if "mp4" not in probe["format_names"]:
            conflict_fields.append("container")
        if probe_video != profile.video_codecs:
            conflict_fields.append("video codec")
        if probe_audio != profile.audio_codecs:
            conflict_fields.append("audio codec")
        if abs(float(probe["duration_seconds"]) - profile.duration_seconds) > 1:
            conflict_fields.append("duration")
        if int(probe["size_bytes"]) != profile.size_bytes:
            conflict_fields.append("file size")
        if conflict_fields:
            issues.append(
                _issue(
                    source,
                    "video-tool-conflict",
                    "built-in MP4 inspection conflicts with ffprobe: "
                    + ", ".join(conflict_fields),
                )
            )

    if any(codec != "h264" for codec in profile.video_codecs):
        issues.append(
            _issue(
                source,
                "unsupported-video-codec",
                "all video tracks must use H.264 (avc1 or avc3)",
            )
        )
    if any(codec != "aac" for codec in profile.audio_codecs):
        issues.append(
            _issue(
                source,
                "unsupported-audio-codec",
                "all audio tracks must use AAC (mp4a); silent video is allowed",
            )
        )
    if not profile.faststart:
        issues.append(
            _issue(source, "missing-faststart", "MP4 must place moov before mdat (faststart)")
        )
    if profile.duration_seconds > LONG_VIDEO_SECONDS:
        finalized_times = sorted(float(value) for value in event_times)
        boundaries = [0.0]
        boundaries.extend(finalized_times)
        boundaries.append(profile.duration_seconds)
        gaps = [right - left for left, right in zip(boundaries, boundaries[1:])]
        first_time = f"{finalized_times[0]:g}s" if finalized_times else "无"
        last_time = f"{finalized_times[-1]:g}s" if finalized_times else "无"
        maximum_gap = max(gaps) if gaps else profile.duration_seconds
        warnings.append(
            _issue(
                source,
                "long-video",
                "video is longer than 10 minutes: "
                f"duration={profile.duration_seconds:.3f}s, "
                f"size={profile.size_bytes} bytes, "
                f"interactionCount={len(finalized_times)}, "
                f"first={first_time}, last={last_time}, maxGap={maximum_gap:.3f}s; "
                "review whether more interaction points are needed",
            )
        )
        if maximum_gap > LONG_VIDEO_SECONDS:
            warnings.append(
                _issue(
                    source,
                    "sparse-video-interactions",
                    "a video segment longer than 10 minutes has no interaction point",
                )
            )
    if profile.size_bytes > LARGE_VIDEO_BYTES:
        warnings.append(
            _issue(
                source,
                "large-video",
                "video exceeds 500 MiB; confirm the platform upload limit before delivery",
            )
        )
    return VideoInspectionResult(tuple(issues), tuple(warnings), profile)


def inspect_video_interactions(
    data: object,
    course_root: Path,
) -> VideoInspectionResult:
    issues: List[ValidationIssue] = []
    warnings: List[ValidationIssue] = []
    profile: Optional[Mp4Profile] = None
    if not isinstance(data, dict):
        return VideoInspectionResult(
            (_issue("$", "required", "video interaction data must be an object"),),
            (),
            None,
        )
    if data.get("schemaVersion") != "1.0":
        issues.append(_issue("schemaVersion", "invalid-version", "schemaVersion must be 1.0"))
    video = data.get("video")
    if not isinstance(video, dict):
        issues.append(_issue("video", "required", "video object is required"))
        return VideoInspectionResult(tuple(issues), (), None)
    source = video.get("source")
    actual_duration: Optional[float] = None
    video_path: Optional[Path] = None
    if not isinstance(source, str) or not source.strip():
        issues.append(_issue("video.source", "required", "video source is required"))
    else:
        try:
            video_path = resolve_course_path(course_root, source)
            if not video_path.is_file():
                issues.append(
                    _issue("video.source", "missing-file", f"video does not exist: {source}")
                )
                video_path = None
        except ValueError as exc:
            issues.append(_issue("video.source", "invalid-path", str(exc)))
            video_path = None

    events = video.get("events")
    event_times: List[float] = []
    if isinstance(events, list):
        for event_value in events:
            if not isinstance(event_value, dict) or event_value.get("status") == "needs-timing":
                continue
            value = event_value.get("timeSeconds")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                event_times.append(float(value))
    if video_path is not None and isinstance(source, str):
        media_result = inspect_video_file(video_path, "video.source", event_times)
        issues.extend(media_result.issues)
        warnings.extend(media_result.warnings)
        profile = media_result.profile
        if profile is not None:
            actual_duration = profile.duration_seconds

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

    if not isinstance(events, list) or not events:
        issues.append(_issue("video.events", "required", "at least one event is required"))
        return VideoInspectionResult(tuple(issues), tuple(warnings), profile)

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
    return VideoInspectionResult(tuple(issues), tuple(warnings), profile)


def validate_video_interactions(
    data: object,
    course_root: Path,
) -> List[ValidationIssue]:
    return list(inspect_video_interactions(data, course_root).issues)


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
