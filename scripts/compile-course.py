#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.course_compiler import (
    CompilationBlocked,
    compile_blueprint,
    write_compilation_outputs_atomic,
)
from course_toolkit.jsonio import load_json


def emit(payload: dict, as_json: bool, *, error: bool = False) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif error:
        print(payload["error"]["message"], file=sys.stderr)
    else:
        print("CourseDefinition 2.0 compiled successfully")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compile an approved CourseBlueprint to CourseDefinition 2.0"
    )
    parser.add_argument("root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if not args.root.exists() or not args.root.is_dir():
            raise ValueError(f"Course root is not a directory: {args.root}")
        root = args.root.resolve()
        work_dir = root / ".course-work"
        if work_dir.is_symlink():
            raise ValueError(".course-work must not be a symlink")
        blueprint_path = work_dir / "course-blueprint.json"
        result = compile_blueprint(load_json(blueprint_path))
        write_compilation_outputs_atomic(root, result)
        emit(
            {
                "ok": True,
                "status": "compiled",
                "courseId": result.document["course"]["id"],
                "outputs": [
                    "course/course.json",
                    ".course-work/course-runtime-source-map.json",
                    ".course-work/compilation-report.json",
                ],
                "assetPaths": result.report["assetPaths"],
            },
            args.json,
        )
        return 0
    except CompilationBlocked as exc:
        issues = [
            {
                "path": issue.path,
                "code": issue.code,
                "message": issue.message,
                "layer": issue.layer,
                "severity": issue.severity,
            }
            for issue in exc.issues
        ]
        emit(
            {
                "ok": False,
                "status": "blocked",
                "issues": issues,
                "error": {
                    "code": "compilation-blocked",
                    "message": str(exc),
                },
            },
            args.json,
            error=True,
        )
        return 2
    except Exception as exc:
        emit(
            {
                "ok": False,
                "status": "failed",
                "issues": [],
                "error": {"code": "tool-error", "message": str(exc)},
            },
            args.json,
            error=True,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
