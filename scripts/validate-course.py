#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.package_review import review_package


STATUS_LABELS = {
    "uploadable": "可上传",
    "uploadable-after-fixes": "修改后可上传",
    "blocked": "缺少必要材料，暂不可上传",
}
EXIT_CODES = {
    "uploadable": 0,
    "uploadable-after-fixes": 1,
    "blocked": 2,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a platform course package")
    parser.add_argument("course_dir", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        result = review_package(args.course_dir, args.work_dir)
    except Exception as exc:
        print(f"校验工具错误：{exc}", file=sys.stderr)
        return 3

    if args.json:
        payload = result.as_dict()
        payload["label"] = STATUS_LABELS[result.status]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(STATUS_LABELS[result.status])
        for issue in result.issues:
            print(f"- [{issue.code}] {issue.path}: {issue.message}")
    return EXIT_CODES[result.status]


if __name__ == "__main__":
    raise SystemExit(main())
