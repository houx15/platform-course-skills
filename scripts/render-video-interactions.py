#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.jsonio import load_json
from course_toolkit.video_interactions import render_video_interactions


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render video interaction Markdown from JSON"
    )
    parser.add_argument("interactions_json", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    output = args.output or args.interactions_json.with_suffix(".md")
    rendered = render_video_interactions(load_json(args.interactions_json))
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
