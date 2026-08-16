#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.publication import build_asset_manifest, write_asset_manifest
from course_toolkit.workflow import WorkflowError, load_session


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare local publication evidence")
    commands = parser.add_subparsers(dest="command", required=True)
    manifest_parser = commands.add_parser("manifest")
    manifest_parser.add_argument("root", type=Path)
    manifest_parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        if not root.is_dir() or (root / ".course-work").is_symlink():
            raise WorkflowError("Course root is missing or unsafe")
        if args.command == "manifest":
            session = load_session(root)
            manifest = build_asset_manifest(root, session.course_local_id)
            output = write_asset_manifest(root, manifest)
            payload = {"ok": True, "manifest": manifest, "output": str(output)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Prepared publication asset manifest: {output}")
        return 0
    except (WorkflowError, ValueError) as exc:
        payload = {"ok": False, "error": {"code": "publication-blocked", "message": str(exc)}}
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Publication preparation blocked: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": {"code": "tool-error", "message": str(exc)}}, ensure_ascii=False, indent=2))
        else:
            print(f"Publication tool error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
