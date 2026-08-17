#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.package_review import (
    V2ReviewBlocked,
    prepare_v2_review,
    verify_g8_review,
    write_v2_review_markdown,
    write_v2_review_report,
)
from course_toolkit.jsonio import load_json


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare or verify an independent CourseDefinition 2.0 review"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "verify"):
        command = commands.add_parser(name)
        command.add_argument("root", type=Path)
        command.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        if args.command == "prepare":
            report = prepare_v2_review(root)
            output = write_v2_review_report(root, report)
            markdown = write_v2_review_markdown(root, report)
            payload = {
                "ok": True,
                "status": report["status"],
                "output": str(output),
                "markdown": str(markdown),
                "report": report,
            }
        else:
            evidence = verify_g8_review(root)
            report = load_json(root / ".course-work/review-report.json")
            markdown = write_v2_review_markdown(root, report)
            payload = {
                "ok": True,
                "status": "publishable",
                "evidence": evidence,
                "markdown": str(markdown),
            }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"CourseDefinition 2.0 review: {payload['status']}")
            print(f"Review Markdown: {payload['markdown']}")
        return 0
    except (V2ReviewBlocked, ValueError) as exc:
        payload = {
            "ok": False,
            "status": "blocked",
            "error": {"code": "review-blocked", "message": str(exc)},
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Course review blocked: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        payload = {
            "ok": False,
            "status": "failed",
            "error": {"code": "tool-error", "message": str(exc)},
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Course review failed: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
