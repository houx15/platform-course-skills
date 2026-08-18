#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.live_publication import (
    LivePublicationBlocked,
    execute_live_publication,
    init_live_publish_state,
    live_preflight_status,
    prepare_live_preflight,
)
from course_toolkit.local_env import load_publication_env
from course_toolkit.mind_imprint_api import (
    DEFAULT_API_BASE,
    MindImprintApiError,
    MindImprintAuthoringApi,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare and execute a Mind Imprint course publication")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init-state")
    init.add_argument("root", type=Path)
    init.add_argument("--slug", required=True)
    init.add_argument("--json", action="store_true")
    preflight = commands.add_parser("preflight")
    preflight.add_argument("root", type=Path)
    preflight.add_argument("--action", choices=("save-preview", "publish"), required=True)
    preflight.add_argument("--blurb", default="")
    preflight.add_argument("--card-id", action="append", default=[])
    preflight.add_argument("--cover", default="")
    preflight.add_argument("--api-base", default=DEFAULT_API_BASE)
    preflight.add_argument("--json", action="store_true")
    status = commands.add_parser("status")
    status.add_argument("root", type=Path)
    status.add_argument("--json", action="store_true")
    execute = commands.add_parser("execute")
    execute.add_argument("root", type=Path)
    execute.add_argument("--api-base", default=DEFAULT_API_BASE)
    execute.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    as_json = args.json
    try:
        load_publication_env(args.root)
        if args.command == "init-state":
            state = init_live_publish_state(args.root, args.slug)
            payload = {"ok": True, "status": "initialized", "slug": state["slug"]}
        elif args.command == "status":
            payload = {"ok": True, **live_preflight_status(args.root)}
        elif args.command == "preflight":
            api = MindImprintAuthoringApi.from_environment(api_base=args.api_base)
            preflight = prepare_live_preflight(
                args.root,
                api,
                action=args.action,
                blurb=args.blurb,
                card_ids=args.card_id,
                cover=args.cover,
                now=utc_now(),
            )
            payload = {
                "ok": True,
                "status": "approval-required",
                "summary": {
                    "slug": preflight["slug"],
                    "mode": preflight["mode"],
                    "action": preflight["action"],
                    "uploadCount": len(preflight["assets"]["upload"]),
                    "reuseCount": len(preflight["assets"]["reuse"]),
                    "risks": preflight["risks"],
                },
            }
        else:
            api = MindImprintAuthoringApi.from_environment(api_base=args.api_base)
            operation = execute_live_publication(args.root, api, now=utc_now())
            payload = {
                "ok": True,
                "status": operation["status"],
                "slug": operation["slug"],
                "definitionHash": operation["remoteDefinitionHash"],
                "uploadedCount": len(operation["uploadedPaths"]),
                "reusedCount": len(operation["reusedPaths"]),
            }
        if as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Course publication: {payload['status']}")
            if "slug" in payload:
                print(f"Slug: {payload['slug']}")
        return 0
    except (LivePublicationBlocked, MindImprintApiError, ValueError) as exc:
        payload = {
            "ok": False,
            "status": "blocked",
            "error": {"code": "publication-blocked", "message": str(exc)},
        }
        if as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Course publication blocked: {exc}", file=sys.stderr)
        return 2
    except Exception:
        payload = {
            "ok": False,
            "status": "failed",
            "error": {"code": "tool-error", "message": "publication failed; inspect local operation state"},
        }
        if as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("Course publication failed; inspect local operation state", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
