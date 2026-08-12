#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.jsonio import load_json
from course_toolkit.video_interactions import inspect_video_interactions


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate video interaction JSON")
    parser.add_argument("course_dir", type=Path)
    parser.add_argument("interaction_json", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        data = load_json(args.interaction_json)
        result = inspect_video_interactions(data, args.course_dir)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(
            json.dumps(
                {
                    "valid": not result.issues,
                    "issues": [issue.as_dict() for issue in result.issues],
                    "warnings": [warning.as_dict() for warning in result.warnings],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif result.issues:
        for issue in result.issues:
            print(f"- [{issue.code}] {issue.path}: {issue.message}")
    else:
        print("视频交互检查通过")
    if result.warnings and not args.json:
        print("提醒：")
        for warning in result.warnings:
            print(f"- [{warning.code}] {warning.path}: {warning.message}")
    return 1 if result.issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
