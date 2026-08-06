#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.jsonio import load_json
from course_toolkit.video_interactions import validate_video_interactions


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate video interaction JSON")
    parser.add_argument("course_dir", type=Path)
    parser.add_argument("interaction_json", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        data = load_json(args.interaction_json)
        issues = validate_video_interactions(data, args.course_dir)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(
            json.dumps(
                {"valid": not issues, "issues": [issue.as_dict() for issue in issues]},
                ensure_ascii=False,
                indent=2,
            )
        )
    elif issues:
        for issue in issues:
            print(f"- [{issue.code}] {issue.path}: {issue.message}")
    else:
        print("视频交互检查通过")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
