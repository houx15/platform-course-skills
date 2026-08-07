#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.course_design import render_review_report, validate_review_report
from course_toolkit.jsonio import load_json


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render the Part-level and overall course review tables"
    )
    parser.add_argument("review_json", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    data = load_json(args.review_json)
    issues = validate_review_report(data)
    if issues:
        for issue in issues:
            print(f"[{issue.code}] {issue.path}: {issue.message}", file=sys.stderr)
        return 2
    rendered = render_review_report(data)
    output = args.output or args.review_json.with_suffix(".md")
    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != rendered:
            print(f"Generated review differs: {output}", file=sys.stderr)
            return 1
        print(f"Generated review is current: {output}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
