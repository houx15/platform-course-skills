#!/usr/bin/env python3
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.jsonio import load_json


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "course-contract.snapshot.json"
VENDORED_PACKAGE = ROOT / "packages" / "course-contract"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compare_tree(base: Path, expected: dict, scope: str) -> list:
    mismatches = []
    actual_paths = {
        path.relative_to(base).as_posix()
        for path in (base / "src").rglob("*.ts")
        if path.is_file()
    }
    for relative_path in sorted(set(expected).union(actual_paths)):
        path = base / relative_path
        if relative_path not in expected:
            mismatches.append(
                {"scope": scope, "path": relative_path, "kind": "unexpected-file"}
            )
        elif not path.is_file():
            mismatches.append(
                {"scope": scope, "path": relative_path, "kind": "missing-file"}
            )
        else:
            actual = file_hash(path)
            if actual != expected[relative_path]:
                mismatches.append(
                    {
                        "scope": scope,
                        "path": relative_path,
                        "kind": "hash-mismatch",
                        "expected": expected[relative_path],
                        "actual": actual,
                    }
                )
    return mismatches


def upstream_commit(root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(completed.stderr.strip() or "cannot read upstream commit")
    return completed.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Check vendored course contract")
    parser.add_argument("--upstream", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        manifest = load_json(MANIFEST_PATH)
        expected = manifest["files"]
        mismatches = compare_tree(VENDORED_PACKAGE, expected, "vendored")
        current_upstream_commit = None
        if args.upstream is not None:
            upstream_root = args.upstream.resolve()
            upstream_package = upstream_root / "packages" / "course-contract"
            mismatches.extend(compare_tree(upstream_package, expected, "upstream"))
            current_upstream_commit = upstream_commit(upstream_root)
        payload = {
            "ok": not mismatches,
            "upstreamCommit": manifest["upstreamCommit"],
            "currentUpstreamCommit": current_upstream_commit,
            "commitMatchesSnapshot": (
                current_upstream_commit is None
                or current_upstream_commit == manifest["upstreamCommit"]
            ),
            "mismatches": mismatches,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif mismatches:
            for mismatch in mismatches:
                print(
                    f"{mismatch['scope']} {mismatch['kind']}: {mismatch['path']}",
                    file=sys.stderr,
                )
        else:
            print(f"Course contract snapshot matches {manifest['upstreamCommit']}")
        return 0 if not mismatches else 2
    except Exception as exc:
        if args.json:
            print(
                json.dumps(
                    {"ok": False, "mismatches": [], "error": str(exc)},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(f"Course contract snapshot check failed: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
