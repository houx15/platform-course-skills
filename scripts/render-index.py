#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.index_renderer import render_index
from course_toolkit.jsonio import load_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Render index.md from course.json")
    parser.add_argument("course_json", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    output = args.output or args.course_json.with_name("index.md")
    rendered = render_index(load_json(args.course_json))
    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != rendered:
            print(f"Generated Markdown differs: {output}", file=sys.stderr)
            return 1
        print(f"Generated Markdown is current: {output}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
