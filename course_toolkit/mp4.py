import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator, List, Optional, Tuple


Box = Tuple[bytes, int, int]


@dataclass(frozen=True)
class Mp4Profile:
    duration_seconds: float
    size_bytes: int
    brands: Tuple[str, ...]
    video_codecs: Tuple[str, ...]
    audio_codecs: Tuple[str, ...]
    faststart: bool


VIDEO_CODECS = {
    b"avc1": "h264",
    b"avc3": "h264",
    b"hvc1": "hevc",
    b"hev1": "hevc",
    b"vp09": "vp9",
}
AUDIO_CODECS = {
    b"mp4a": "aac",
    b"ac-3": "ac3",
    b"ec-3": "eac3",
    b"Opus": "opus",
}


def _boxes(handle: BinaryIO, start: int, end: int) -> Iterator[Box]:
    position = start
    while position + 8 <= end:
        handle.seek(position)
        header = handle.read(8)
        if len(header) != 8:
            return
        size, box_type = struct.unpack(">I4s", header)
        header_size = 8
        if size == 1:
            extended = handle.read(8)
            if len(extended) != 8:
                return
            size = struct.unpack(">Q", extended)[0]
            header_size = 16
        elif size == 0:
            size = end - position
        if size < header_size or position + size > end:
            return
        yield box_type, position + header_size, position + size
        position += size


def _read_mvhd(handle: BinaryIO, payload_start: int, payload_end: int) -> float:
    handle.seek(payload_start)
    payload = handle.read(payload_end - payload_start)
    if len(payload) < 20:
        raise ValueError("Invalid mvhd box")
    version = payload[0]
    if version == 0:
        if len(payload) < 20:
            raise ValueError("Invalid version 0 mvhd box")
        timescale = struct.unpack(">I", payload[12:16])[0]
        duration = struct.unpack(">I", payload[16:20])[0]
    elif version == 1:
        if len(payload) < 32:
            raise ValueError("Invalid version 1 mvhd box")
        timescale = struct.unpack(">I", payload[20:24])[0]
        duration = struct.unpack(">Q", payload[24:32])[0]
    else:
        raise ValueError(f"Unsupported mvhd version: {version}")
    if timescale == 0:
        raise ValueError("Invalid mvhd timescale: 0")
    return duration / timescale


def _read_ftyp(handle: BinaryIO, payload_start: int, payload_end: int) -> Tuple[str, ...]:
    handle.seek(payload_start)
    payload = handle.read(payload_end - payload_start)
    if len(payload) < 8 or (len(payload) - 8) % 4:
        raise ValueError("Invalid ftyp box")
    values = [payload[:4]]
    values.extend(payload[index : index + 4] for index in range(8, len(payload), 4))
    return tuple(value.decode("ascii", errors="replace") for value in values)


def _read_handler(handle: BinaryIO, payload_start: int, payload_end: int) -> bytes:
    handle.seek(payload_start)
    payload = handle.read(payload_end - payload_start)
    if len(payload) < 12:
        raise ValueError("Invalid hdlr box")
    return payload[8:12]


def _read_sample_entries(
    handle: BinaryIO,
    payload_start: int,
    payload_end: int,
) -> Tuple[bytes, ...]:
    if payload_end - payload_start < 8:
        raise ValueError("Invalid stsd box")
    handle.seek(payload_start + 4)
    entry_count_raw = handle.read(4)
    if len(entry_count_raw) != 4:
        raise ValueError("Invalid stsd entry count")
    entry_count = struct.unpack(">I", entry_count_raw)[0]
    entries = list(_boxes(handle, payload_start + 8, payload_end))
    if len(entries) != entry_count:
        raise ValueError("Invalid stsd sample entries")
    return tuple(box_type for box_type, _, _ in entries)


def _track_profile(
    handle: BinaryIO,
    payload_start: int,
    payload_end: int,
) -> Tuple[Optional[bytes], Tuple[bytes, ...]]:
    handler_type: Optional[bytes] = None
    sample_entries: Tuple[bytes, ...] = ()
    for child_type, child_start, child_end in _boxes(handle, payload_start, payload_end):
        if child_type != b"mdia":
            continue
        for media_type, media_start, media_end in _boxes(handle, child_start, child_end):
            if media_type == b"hdlr":
                handler_type = _read_handler(handle, media_start, media_end)
            elif media_type == b"minf":
                for minf_type, minf_start, minf_end in _boxes(
                    handle,
                    media_start,
                    media_end,
                ):
                    if minf_type != b"stbl":
                        continue
                    for stbl_type, stbl_start, stbl_end in _boxes(
                        handle,
                        minf_start,
                        minf_end,
                    ):
                        if stbl_type == b"stsd":
                            sample_entries = _read_sample_entries(
                                handle,
                                stbl_start,
                                stbl_end,
                            )
    return handler_type, sample_entries


def _codec_name(codec: bytes, mapping: dict) -> str:
    return mapping.get(codec, codec.decode("ascii", errors="replace").strip() or "unknown")


def inspect_mp4(path: Path) -> Mp4Profile:
    try:
        file_size = path.stat().st_size
        with path.open("rb") as handle:
            top_level = list(_boxes(handle, 0, file_size))
            top_types = [box_type for box_type, _, _ in top_level]
            if not top_level or b"ftyp" not in top_types:
                raise ValueError("MP4 container requires an ftyp box")
            if b"moov" not in top_types or b"mdat" not in top_types:
                raise ValueError("MP4 container requires moov and mdat boxes")

            ftyp_box = next(box for box in top_level if box[0] == b"ftyp")
            brands = _read_ftyp(handle, ftyp_box[1], ftyp_box[2])
            moov_box = next(box for box in top_level if box[0] == b"moov")
            duration: Optional[float] = None
            video_entries: List[bytes] = []
            audio_entries: List[bytes] = []
            for child_type, child_start, child_end in _boxes(
                handle,
                moov_box[1],
                moov_box[2],
            ):
                if child_type == b"mvhd":
                    duration = _read_mvhd(handle, child_start, child_end)
                elif child_type == b"trak":
                    handler, entries = _track_profile(handle, child_start, child_end)
                    if handler == b"vide":
                        video_entries.extend(entries)
                    elif handler == b"soun":
                        audio_entries.extend(entries)

            if duration is None:
                raise ValueError("No valid mvhd duration found")
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError("MP4 duration must be finite and greater than zero")
            if not video_entries:
                raise ValueError("MP4 requires at least one video track")
            return Mp4Profile(
                duration_seconds=duration,
                size_bytes=file_size,
                brands=brands,
                video_codecs=tuple(
                    _codec_name(codec, VIDEO_CODECS) for codec in video_entries
                ),
                audio_codecs=tuple(
                    _codec_name(codec, AUDIO_CODECS) for codec in audio_entries
                ),
                faststart=top_types.index(b"moov") < top_types.index(b"mdat"),
            )
    except OSError as exc:
        raise ValueError(f"Cannot read MP4 at {path}: {exc}") from exc


def read_mp4_duration(path: Path) -> float:
    return inspect_mp4(path).duration_seconds
