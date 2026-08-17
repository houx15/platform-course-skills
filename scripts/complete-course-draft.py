#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.course_completion import audit_course_draft, write_completion_plan
from course_toolkit.jsonio import load_json


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit an incomplete course draft against the complete runtime authoring standard"
    )
    parser.add_argument("root", type=Path)
    parser.add_argument("--draft", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        draft_path = args.draft or root / ".course-work" / "course-blueprint.json"
        if not draft_path.is_absolute():
            draft_path = root / draft_path
        draft_path = draft_path.resolve()
        draft = load_json(draft_path)
        plan = audit_course_draft(draft, source_path=str(draft_path))
        output = write_completion_plan(root, plan)
        payload = {**plan, "output": str(output)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Course completion readiness: {'ready' if plan['summary']['ready'] else 'incomplete'}")
            for record in plan["slices"]:
                print(f"- {record['sliceId']}: {record['status']}")
                for issue in record["issues"]:
                    print(f"  [{issue['code']}] {issue['message']}")
        return 0 if plan["summary"]["ready"] else 1
    except Exception as exc:
        payload = {"ok": False, "error": {"code": "tool-error", "message": str(exc)}}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Course draft audit failed: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
