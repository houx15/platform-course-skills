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
    record_instructional_audit,
)
from course_toolkit.jsonio import load_json


MAX_CANDIDATE_BYTES = 512 * 1024


def _candidate_path(root: Path, raw: Path) -> Path:
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise InstructionalAuditError("invalid-root", "course root must be a real directory", path=".")
    candidates = root / ".course-work" / "candidates"
    if candidates.is_symlink() or not candidates.is_dir():
        raise InstructionalAuditError("candidate-directory-required", "candidate must be stored under .course-work/candidates", path=".course-work/candidates")
    candidate = raw if raw.is_absolute() else root / raw
    try:
        candidate.relative_to(candidates)
    except ValueError as exc:
        raise InstructionalAuditError("candidate-outside-root", "candidate must stay under .course-work/candidates", path="candidate") from exc
    current = root
    for component in candidate.relative_to(root).parts:
        current = current / component
        if current.is_symlink():
            raise InstructionalAuditError("candidate-symlink", "candidate path may not traverse a symlink", path="candidate")
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
    parser.add_argument("candidate", type=Path, nargs="?", help="JSON under .course-work/candidates/")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if args.candidate is None:
            raise InstructionalAuditError("candidate-required", "candidate JSON file is required", path="candidate")
        candidate = _candidate_path(args.root, args.candidate)
        payload = load_json(candidate)
        report = record_instructional_audit(args.root, payload)
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
