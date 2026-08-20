#!/usr/bin/env python3
"""Record a source-grounded instructional audit from a confined JSON file."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.instructional_audit import (
    INSTRUCTIONAL_AUDIT_RELATIVE_PATH,
    InstructionalAuditError,
    _safe_root,
    record_instructional_audit,
)
from course_toolkit.jsonio import load_json


MAX_CANDIDATE_BYTES = 512 * 1024


def _candidate_path(root: Path, raw: str) -> Path:
    root = _safe_root(root)
    if not raw or raw.startswith("/") or "\\" in raw:
        raise InstructionalAuditError("candidate-invalid-path", "candidate must be a relative path below .course-work/candidates", path="candidate")
    raw_parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise InstructionalAuditError("candidate-invalid-path", "candidate path may not contain empty, dot, or parent components", path="candidate")
    expected_prefix = (".course-work", "candidates")
    if tuple(raw_parts[:2]) != expected_prefix or len(raw_parts) == 2:
        raise InstructionalAuditError("candidate-outside-root", "candidate must stay below .course-work/candidates", path="candidate")
    candidates = root
    for component in expected_prefix:
        candidates = candidates / component
        if candidates.is_symlink() or not candidates.is_dir():
            raise InstructionalAuditError("candidate-directory-required", "candidate must be stored under a real .course-work/candidates directory", path=".course-work/candidates")
    candidate = root
    for index, component in enumerate(raw_parts):
        candidate = candidate / component
        if candidate.is_symlink():
            raise InstructionalAuditError("candidate-symlink", "candidate path may not traverse a symlink", path="candidate")
        if index < len(raw_parts) - 1 and not candidate.is_dir():
            raise InstructionalAuditError("candidate-required", "candidate parent directory does not exist", path="candidate")
    if not candidate.is_file():
        raise InstructionalAuditError("candidate-required", "candidate JSON file is required", path="candidate")
    if candidate.stat().st_size > MAX_CANDIDATE_BYTES:
        raise InstructionalAuditError("candidate-too-large", "candidate JSON exceeds the allowed size", path="candidate")
    return candidate


def _emit(payload: dict, as_json: bool, *, error: bool = False) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    elif error:
        print(f"[{payload['error']['code']}] {payload['error']['message']}", file=sys.stderr)
    else:
        print(INSTRUCTIONAL_AUDIT_RELATIVE_PATH)


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a source-grounded instructional audit")
    parser.add_argument("root", type=Path)
    parser.add_argument("candidate", nargs="?", help="JSON under .course-work/candidates/")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if args.candidate is None:
            raise InstructionalAuditError("candidate-required", "candidate JSON file is required", path="candidate")
        root = _safe_root(args.root)
        candidate = _candidate_path(root, args.candidate)
        payload = load_json(candidate)
        report = record_instructional_audit(root, payload)
        _emit({"ok": True, "status": "recorded", "output": INSTRUCTIONAL_AUDIT_RELATIVE_PATH, "report": report}, args.json)
        return 0
    except InstructionalAuditError as exc:
        _emit({"ok": False, "status": "blocked", "error": {"code": exc.code, "message": str(exc)}}, args.json, error=True)
        return 2
    except ValueError:
        _emit({"ok": False, "status": "blocked", "error": {"code": "invalid-candidate-json", "message": "candidate JSON is invalid"}}, args.json, error=True)
        return 2
    except OSError:
        _emit({"ok": False, "status": "failed", "error": {"code": "filesystem-error", "message": "audit files could not be read or written"}}, args.json, error=True)
        return 3
    except Exception:
        _emit({"ok": False, "status": "failed", "error": {"code": "tool-error", "message": "instructional audit tool failed"}}, args.json, error=True)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
