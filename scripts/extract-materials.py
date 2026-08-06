#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.jsonio import dump_json
from course_toolkit.materials import extract_paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract teacher course materials")
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".course-work/extracted-materials.json"),
    )
    args = parser.parse_args()

    result = extract_paths(args.inputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(dump_json(result.as_dict()), encoding="utf-8")
    print(f"提取内容点：{len(result.items)}")
    print(f"忽略 ZIP：{len(result.ignored)}")
    print(f"不支持文件：{len(result.unsupported)}")
    print(f"读取错误：{len(result.errors)}")
    print(args.output)
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
