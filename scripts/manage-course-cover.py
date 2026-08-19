#!/usr/bin/env python3
"""Register and confirm an imagegen2 course-cover candidate."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.course_cover import (  # noqa: E402
    CourseCoverError,
    confirm_cover_candidate,
    load_confirmed_cover,
    prepare_cover_candidate,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Manage a generated 16:9 course cover")
    commands = root.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("root", type=Path)
    prepare.add_argument("source", type=Path)
    prepare.add_argument("candidate", type=Path)
    prepare.add_argument("--prompt", required=True)
    prepare.add_argument("--created-at", default=None)
    prepare.add_argument("--json", action="store_true")
    confirm = commands.add_parser("confirm")
    confirm.add_argument("root", type=Path)
    confirm.add_argument("--teacher-response", required=True)
    confirm.add_argument("--confirmed-at", default=None)
    confirm.add_argument("--json", action="store_true")
    status = commands.add_parser("status")
    status.add_argument("root", type=Path)
    status.add_argument("--json", action="store_true")
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "prepare":
            record = prepare_cover_candidate(
                args.root,
                args.source,
                args.candidate,
                prompt=args.prompt,
                created_at=args.created_at or utc_now(),
            )
            payload = {"ok": True, "status": "teacher-review-required", "cover": record}
        elif args.command == "confirm":
            record = confirm_cover_candidate(
                args.root,
                teacher_response=args.teacher_response,
                confirmed_at=args.confirmed_at or utc_now(),
            )
            payload = {"ok": True, "status": "confirmed", "cover": record}
        else:
            record = load_confirmed_cover(args.root)
            payload = {"ok": True, "status": "confirmed", "cover": record}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Course cover: {payload['status']}")
        return 0
    except (CourseCoverError, ValueError) as exc:
        payload = {"ok": False, "status": "blocked", "error": {"code": "cover-blocked", "message": str(exc)}}
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Course cover blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
