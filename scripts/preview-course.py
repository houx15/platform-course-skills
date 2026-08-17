#!/usr/bin/env python3
import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.preview_server import create_preview_server, validate_preview_prerequisites
from course_toolkit.workflow import verify_g6_validation


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an exact-renderer course preview on localhost")
    parser.add_argument("root", type=Path)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        validation = validate_preview_prerequisites(root)
        verify_g6_validation(root)
        server = create_preview_server(root, port=args.port)
        host, port = server.server_address
        url = f"http://{host}:{port}/"
        payload = {
            "ok": True,
            "url": url,
            "pid": os.getpid(),
            "courseId": validation["courseId"],
            "bind": host,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False), flush=True)
        else:
            print(f"Course preview: {url}", flush=True)
        if not args.no_open:
            webbrowser.open(url)
        server.serve_forever()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        payload = {"ok": False, "error": {"code": "preview-start-failed", "message": str(exc)}}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"Course preview failed: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
