#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.html_reports import build_html_report, render_html_report
from course_toolkit.jsonio import dump_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate one deterministic HTML report")
    parser.add_argument("html_file", type=Path)
    parser.add_argument("--block-id", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    report = build_html_report(args.block_id, args.source, args.html_file)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / f"{args.block_id}.json"
    markdown_path = args.output_dir / f"{args.block_id}.md"
    json_path.write_text(dump_json(report), encoding="utf-8")
    markdown_path.write_text(render_html_report(report), encoding="utf-8")
    print(f"已生成：{json_path}")
    print(f"已生成：{markdown_path}")
    return 0 if report["finalStatus"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
