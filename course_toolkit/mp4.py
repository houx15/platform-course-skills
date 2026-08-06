import struct
from pathlib import Path
from typing import BinaryIO, Iterator, Tuple


Box = Tuple[bytes, int, int]


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


def read_mp4_duration(path: Path) -> float:
    try:
        file_size = path.stat().st_size
        with path.open("rb") as handle:
            for box_type, payload_start, box_end in _boxes(handle, 0, file_size):
                if box_type != b"moov":
                    continue
                for child_type, child_start, child_end in _boxes(
                    handle,
                    payload_start,
                    box_end,
                ):
                    if child_type == b"mvhd":
                        return _read_mvhd(handle, child_start, child_end)
    except OSError as exc:
        raise ValueError(f"Cannot read MP4 at {path}: {exc}") from exc
    raise ValueError(f"No valid mvhd duration found in MP4: {path}")
