#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.jsonio import load_json
from course_toolkit.publication import (
    PublicationReviewEvidence,
    RemoteDiscoverySnapshot,
    build_asset_manifest,
    load_publish_state,
    new_publish_state,
    prepare_publication_preflight,
    publication_preflight_status,
    write_asset_manifest,
    write_publish_state,
)
from course_toolkit.workflow import WorkflowError, load_session


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare local publication evidence")
    commands = parser.add_subparsers(dest="command", required=True)
    manifest_parser = commands.add_parser("manifest")
    manifest_parser.add_argument("root", type=Path)
    manifest_parser.add_argument("--json", action="store_true")
    preflight_parser = commands.add_parser("preflight")
    preflight_parser.add_argument("root", type=Path)
    preflight_parser.add_argument("--discovery", type=Path, required=True)
    preflight_parser.add_argument("--review-evidence", type=Path, required=True)
    preflight_parser.add_argument(
        "--intended-status", choices=("preview", "published"), required=True
    )
    preflight_parser.add_argument(
        "--visibility", choices=("private", "unlisted", "public"), required=True
    )
    preflight_parser.add_argument("--json", action="store_true")
    status_parser = commands.add_parser("status")
    status_parser.add_argument("root", type=Path)
    status_parser.add_argument("--json", action="store_true")
    init_parser = commands.add_parser("init-state")
    init_parser.add_argument("root", type=Path)
    init_parser.add_argument("--slug", required=True)
    init_parser.add_argument("--json", action="store_true")
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
        elif args.command == "preflight":
            discovery = RemoteDiscoverySnapshot.from_dict(load_json(args.discovery))
            review_evidence = PublicationReviewEvidence.from_dict(
                load_json(args.review_evidence)
            )
            preflight = prepare_publication_preflight(
                root=root,
                discovery=discovery,
                review_evidence=review_evidence,
                intended_status=args.intended_status,
                visibility=args.visibility,
                now=utc_now(),
            )
            output = root / ".course-work/publication-preflight.json"
            payload = {"ok": True, "preflight": preflight, "output": str(output)}
        elif args.command == "status":
            output = root / ".course-work/publication-preflight.json"
            payload = {"ok": True, "status": publication_preflight_status(root)}
        elif args.command == "init-state":
            session = load_session(root)
            state_path = root / ".course-work/publish-state.json"
            if state_path.exists():
                state = load_publish_state(root)
                if state.course_local_id != session.course_local_id or state.slug != args.slug:
                    raise WorkflowError(
                        "Existing publish state identity differs; refusing to replace it"
                    )
            else:
                state = new_publish_state(session.course_local_id, args.slug)
                write_publish_state(root, state)
            output = state_path
            payload = {"ok": True, "publishState": state.as_dict(), "output": str(output)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Publication preparation complete: {output}")
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
