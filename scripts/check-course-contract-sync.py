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


def package_files(base: Path) -> list[Path]:
    return sorted(
        path
        for path in base.rglob("*")
        if path.is_file() and "node_modules" not in path.parts
    )


def tree_hash(base: Path) -> str:
    digest = hashlib.sha256()
    for path in package_files(base):
        relative = path.relative_to(base).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def compare_package(base: Path, expected_hash: str, scope: str) -> list:
    if not base.is_dir():
        return [{"scope": scope, "path": str(base), "kind": "missing-package"}]
    actual_hash = tree_hash(base)
    if actual_hash == expected_hash:
        return []
    return [
        {
            "scope": scope,
            "path": str(base),
            "kind": "tree-hash-mismatch",
            "expected": expected_hash,
            "actual": actual_hash,
        }
    ]


def upstream_commit(root: Path, ref: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", f"{ref}^{{commit}}"],
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
        packages = manifest["packages"]
        mismatches = []
        for package_name, package in sorted(packages.items()):
            vendored_package = ROOT / package["path"]
            mismatches.extend(
                compare_package(
                    vendored_package,
                    package["treeHash"],
                    f"vendored:{package_name}",
                )
            )
        current_upstream_commit = None
        if args.upstream is not None:
            upstream_root = args.upstream.resolve()
            for package_name, package in sorted(packages.items()):
                upstream_package = upstream_root / package["path"]
                mismatches.extend(
                    compare_package(
                        upstream_package,
                        package["treeHash"],
                        f"upstream:{package_name}",
                    )
                )
            current_upstream_commit = upstream_commit(
                upstream_root, manifest["upstreamTag"]
            )
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
