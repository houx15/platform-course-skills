#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.html_validation import validate_interactive_html


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate one platform HTML interaction")
    parser.add_argument("html_file", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    issues = validate_interactive_html(args.html_file)
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
        print("HTML 静态契约检查通过")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
