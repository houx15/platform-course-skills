#!/usr/bin/env python3
"""Propose, confirm, and verify a teacher's 33-course catalog binding."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.course_catalog import (  # noqa: E402
    CourseCatalogError,
    confirm_course_selection,
    load_confirmed_course_selection,
    load_course_catalog,
    propose_course_matches,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Manage the reviewed 33-course catalog binding")
    commands = root.add_subparsers(dest="command", required=True)
    list_command = commands.add_parser("list")
    list_command.add_argument("--json", action="store_true")
    propose = commands.add_parser("propose")
    propose.add_argument("query")
    propose.add_argument("--json", action="store_true")
    confirm = commands.add_parser("confirm")
    confirm.add_argument("root", type=Path)
    confirm.add_argument("--catalog-id", required=True)
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
        if args.command == "list":
            payload = {"ok": True, "courses": load_course_catalog()["courses"]}
        elif args.command == "propose":
            payload = {"ok": True, "query": args.query, "proposals": propose_course_matches(args.query)}
        elif args.command == "confirm":
            selection = confirm_course_selection(
                args.root,
                args.catalog_id,
                teacher_response=args.teacher_response,
                confirmed_at=args.confirmed_at or utc_now(),
            )
            payload = {"ok": True, "selection": selection}
        else:
            payload = {"ok": True, "selection": load_confirmed_course_selection(args.root)}
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif args.command == "propose":
            for item in payload["proposals"]:
                print(f"{item['catalogId']}\t{item['title']}\t{item['matchKind']}")
        elif args.command == "list":
            for item in payload["courses"]:
                print(f"{item['catalogId']}\t{item['title']}")
        else:
            print(f"Course catalog selection: {payload['selection']['catalogId']} {payload['selection']['title']}")
        return 0
    except (CourseCatalogError, ValueError) as exc:
        payload = {"ok": False, "status": "blocked", "error": {"code": "catalog-binding-blocked", "message": str(exc)}}
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Course catalog binding blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
