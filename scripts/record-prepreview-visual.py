#!/usr/bin/env python3
"""Record a renderer-backed pre-preview report from a confined candidate."""

import argparse
import json
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.prepreview_visual import (
    MAX_CANDIDATE_BYTES,
    VISUAL_REPORT_RELATIVE_PATH,
    VisualReportError,
    _safe_root,
    record_visual_report,
)


def _validate_candidate_name(raw: str) -> tuple[str, ...]:
    if not raw or raw.startswith("/") or "\\" in raw:
        raise VisualReportError("candidate-invalid-path", "candidate must be a relative path below .course-work/candidates", path="candidate")
    parts = tuple(raw.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise VisualReportError("candidate-invalid-path", "candidate path may not contain empty, dot, or parent components", path="candidate")
    if parts[:2] != (".course-work", "candidates") or len(parts) == 2:
        raise VisualReportError("candidate-outside-root", "candidate must stay below .course-work/candidates", path="candidate")
    return parts


def _load_candidate(root: Path, raw: str) -> dict:
    parts = _validate_candidate_name(raw)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    directory_flags = flags | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(root, directory_flags)
    except OSError as exc:
        raise VisualReportError("unsafe-evidence-root", "course root cannot be opened safely", path="candidate") from exc
    try:
        for index, component in enumerate(parts):
            child_flags = flags if index == len(parts) - 1 else directory_flags
            try:
                child = os.open(component, child_flags, dir_fd=descriptor)
            except FileNotFoundError as exc:
                raise VisualReportError("candidate-required", "candidate JSON file is required", path="candidate") from exc
            except OSError as exc:
                raise VisualReportError("candidate-symlink", "candidate path may not traverse a symlink", path="candidate") from exc
            os.close(descriptor)
            descriptor = child
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise VisualReportError("candidate-required", "candidate JSON file must be a regular file", path="candidate")
        if metadata.st_size > MAX_CANDIDATE_BYTES:
            raise VisualReportError("candidate-too-large", "candidate JSON exceeds the allowed size", path="candidate")
        chunks = []
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        document = json.loads(b"".join(chunks).decode("utf-8"))
        if not isinstance(document, dict):
            raise VisualReportError("invalid-payload", "visual report candidate must be a JSON object", path="candidate")
        return document
    except VisualReportError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VisualReportError("invalid-candidate-json", "candidate file cannot be read as JSON safely", path="candidate") from exc
    finally:
        os.close(descriptor)


def _emit(payload: dict, as_json: bool, *, error: bool = False) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    elif error:
        print(f"[{payload['error']['code']}] {payload['error']['message']}", file=sys.stderr)
    else:
        print(VISUAL_REPORT_RELATIVE_PATH)


def main() -> int:
    parser = argparse.ArgumentParser(description="Record renderer-backed pre-preview visual evidence")
    parser.add_argument("root", type=Path)
    parser.add_argument("candidate", nargs="?", help="JSON under .course-work/candidates/")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if args.candidate is None:
            raise VisualReportError("candidate-required", "candidate JSON file is required", path="candidate")
        root = _safe_root(args.root)
        report = record_visual_report(root, _load_candidate(root, args.candidate))
        _emit({"ok": True, "status": "recorded", "output": VISUAL_REPORT_RELATIVE_PATH, "report": report}, args.json)
        return 0
    except VisualReportError as exc:
        _emit({"ok": False, "status": "blocked", "error": {"code": exc.code, "message": str(exc), "path": exc.path}}, args.json, error=True)
        return 2
    except OSError:
        _emit({"ok": False, "status": "failed", "error": {"code": "filesystem-error", "message": "visual evidence files could not be read or written"}}, args.json, error=True)
        return 3
    except Exception:
        _emit({"ok": False, "status": "failed", "error": {"code": "tool-error", "message": "pre-preview visual tool failed"}}, args.json, error=True)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

