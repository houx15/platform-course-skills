#!/usr/bin/env python3
"""Dry-run or execute the one-time upload of all fixed catalog covers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from course_toolkit.mind_imprint_api import DEFAULT_API_BASE, MindImprintAuthoringApi, MindImprintApiError
from course_toolkit.local_env import load_local_env
from maintenance.catalog_cover_seed import CatalogCoverSeedBlocked, build_cover_seed_plan, execute_cover_seed_plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the 33 fixed catalog WebP covers to their canonical OSS keys")
    parser.add_argument("--execute", action="store_true", help="perform the 33 OSS uploads; default is dry-run")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    args = parser.parse_args()
    try:
        if not args.execute:
            plan = build_cover_seed_plan(ROOT)
            print(json.dumps({"mode": "dry-run", **plan}, ensure_ascii=False, indent=2))
            return 0
        load_local_env(ROOT / ".env")
        api = MindImprintAuthoringApi.from_environment(api_base=args.api_base)
        result = execute_cover_seed_plan(ROOT, api)
        print(json.dumps({"mode": "executed", **result}, ensure_ascii=False, indent=2))
        return 0
    except (CatalogCoverSeedBlocked, MindImprintApiError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
