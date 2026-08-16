#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.legacy_course_import import LegacyImportError, import_legacy_course


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import a schemaVersion 1.1 course into CourseBlueprint 1.0"
    )
    parser.add_argument("legacy_course", type=Path)
    parser.add_argument("storyboard", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--replace-unconfirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if args.output.exists():
            existing = load_json(args.output)
            confirmed = existing.get("approval", {}).get("teacherConfirmed") is True
            if confirmed:
                raise LegacyImportError("A confirmed Blueprint can never be overwritten")
            if not args.replace_unconfirmed:
                raise LegacyImportError(
                    "Output already exists; use --replace-unconfirmed only after review"
                )
        blueprint = import_legacy_course(
            load_json(args.legacy_course),
            load_json(args.storyboard),
        )
        write_json_atomic(args.output, blueprint)
        payload = {
            "ok": True,
            "output": str(args.output),
            "teacherConfirmed": False,
            "assumptions": [
                assumption["id"]
                for assumption in blueprint["migration"]["assumptions"]
            ],
            "nextAction": "review migration assumptions with the teacher",
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Imported unconfirmed Blueprint: {args.output}")
        return 0
    except LegacyImportError as exc:
        payload = {"ok": False, "error": {"code": "import-blocked", "message": str(exc)}}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Legacy import blocked: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        if args.json:
            print(
                json.dumps(
                    {"ok": False, "error": {"code": "tool-error", "message": str(exc)}},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(f"Legacy import tool error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
