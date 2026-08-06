import struct
from pathlib import Path


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
