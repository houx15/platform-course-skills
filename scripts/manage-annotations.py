#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.annotations import (
    AnnotationStore,
    CourseAnnotation,
    reconcile_annotations,
)
from course_toolkit.jsonio import load_json
from course_toolkit.workflow import WorkflowError


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def course_root(path: Path) -> Path:
    if not path.exists() or not path.is_dir():
        raise WorkflowError(f"Course root is not a directory: {path}")
    root = path.resolve()
    if (root / ".course-work").is_symlink():
        raise WorkflowError(".course-work must not be a symlink")
    return root


def payload(root: Path, reconciliation=None) -> dict:
    store = AnnotationStore.load(root / ".course-work/annotations.json")
    result = {
        "ok": True,
        "annotations": [annotation.as_dict() for annotation in store.all()],
    }
    if reconciliation is not None:
        result["reconciliation"] = {
            "resolvedIds": list(reconciliation.resolved_ids),
            "reboundIds": list(reconciliation.rebound_ids),
            "orphanedIds": list(reconciliation.orphaned_ids),
            "restoredIds": list(reconciliation.restored_ids),
            "activeIssueIds": list(reconciliation.active_issue_ids),
        }
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage local course annotations")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("list", "reconcile"):
        child = commands.add_parser(command)
        child.add_argument("root", type=Path)
        child.add_argument("--json", action="store_true")
    add = commands.add_parser("add")
    add.add_argument("root", type=Path)
    add.add_argument("annotation", type=Path)
    add.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        root = course_root(args.root)
        reconciliation = None
        if args.command == "add":
            annotation = CourseAnnotation.from_dict(load_json(args.annotation))
            store = AnnotationStore.load(root / ".course-work/annotations.json")
            store.add(annotation)
            store.save()
            reconciliation = reconcile_annotations(root, utc_now())
        elif args.command == "reconcile":
            reconciliation = reconcile_annotations(root, utc_now())
        result = payload(root, reconciliation)
        if getattr(args, "json", False):
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"Course annotations: {len(result['annotations'])}")
            for annotation in result["annotations"]:
                print(
                    f"- [{annotation['status']}] {annotation['id']}: {annotation['text']}"
                )
        return 0
    except (WorkflowError, ValueError) as exc:
        result = {"ok": False, "error": {"code": "annotation-blocked", "message": str(exc)}}
        if getattr(args, "json", False):
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"Annotation workflow blocked: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        result = {"ok": False, "error": {"code": "tool-error", "message": str(exc)}}
        if getattr(args, "json", False):
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"Annotation tool error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
