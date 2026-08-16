#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.course_package_validation import (
    build_course_validation_report,
    write_current_validation_report,
)
from course_toolkit.workflow import WorkflowError


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate one compiled CourseDefinition 2.0 package"
    )
    parser.add_argument("root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = build_course_validation_report(args.root)
        output_path = write_current_validation_report(args.root, report)
        payload = {**report, "output": str(output_path)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"CourseDefinition 2.0 validation: {report['status']}")
            for issue in report["issues"]:
                print(f"- [{issue['code']}] {issue['path']}: {issue['message']}")
            for warning in report["warnings"]:
                print(f"- [warning:{warning['code']}] {warning['path']}: {warning['message']}")
        return {"clear": 0, "warnings": 1, "blocked": 2}[report["status"]]
    except WorkflowError as exc:
        payload = {
            "ok": False,
            "status": "blocked",
            "error": {"code": "stale-compilation", "message": str(exc)},
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"CourseDefinition 2.0 validation blocked: {exc}", file=sys.stderr)
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
            print(f"CourseDefinition 2.0 validation tool error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
