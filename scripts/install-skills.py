#!/usr/bin/env python3
import argparse
import shutil
import sys
from pathlib import Path
from typing import Iterable, List


RUNTIME_NAME = "_course-toolkit"
IGNORE = shutil.ignore_patterns("*.zip", "__pycache__", "*.pyc", ".DS_Store")


def _skill_sources(root: Path) -> List[Path]:
    return sorted(
        path
        for path in (root / "skills").iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    )


def _parents(home: Path, target: str) -> List[Path]:
    parents = []
    if target in {"codex", "both"}:
        parents.append(home / ".agents" / "skills")
    if target in {"claude", "both"}:
        parents.append(home / ".claude" / "skills")
    return parents


def _remove_exact(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _preflight(
    parents: Iterable[Path],
    skill_sources: Iterable[Path],
    replace: bool,
) -> List[Path]:
    conflicts: List[Path] = []
    names = [source.name for source in skill_sources] + [RUNTIME_NAME]
    for parent in parents:
        for name in names:
            target = parent / name
            if target.exists() or target.is_symlink():
                conflicts.append(target)
    if conflicts and not replace:
        joined = "\n".join(f"- {path}" for path in conflicts)
        raise ValueError(
            "Toolkit files already exist; rerun with --replace:\n" + joined
        )
    return conflicts


def _copy_runtime(root: Path, target: Path) -> None:
    target.mkdir(parents=True)
    for name in ("course_toolkit", "schemas", "scripts"):
        shutil.copytree(root / name, target / name, ignore=IGNORE)


def _install_parent(
    root: Path,
    parent: Path,
    skill_sources: List[Path],
    symlink: bool,
    replace: bool,
) -> None:
    parent.mkdir(parents=True, exist_ok=True)
    targets = [parent / source.name for source in skill_sources]
    runtime_target = parent / RUNTIME_NAME
    if replace:
        for target in targets + [runtime_target]:
            if target.exists() or target.is_symlink():
                _remove_exact(target)
    if symlink:
        runtime_target.symlink_to(root, target_is_directory=True)
        for source, target in zip(skill_sources, targets):
            target.symlink_to(source.resolve(), target_is_directory=True)
    else:
        _copy_runtime(root, runtime_target)
        for source, target in zip(skill_sources, targets):
            shutil.copytree(source, target, ignore=IGNORE)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install platform course authoring skills for Codex and Claude Code"
    )
    parser.add_argument(
        "--target",
        choices=("codex", "claude", "both"),
        default="both",
    )
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--symlink", action="store_true")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    skill_sources = _skill_sources(root)
    parents = _parents(args.home, args.target)
    try:
        _preflight(parents, skill_sources, args.replace)
        for parent in parents:
            _install_parent(
                root,
                parent,
                skill_sources,
                args.symlink,
                args.replace,
            )
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    mode = "符号链接" if args.symlink else "复制"
    print(f"已通过{mode}安装 {len(skill_sources)} 个课程 Skills：")
    for parent in parents:
        print(f"- {parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
