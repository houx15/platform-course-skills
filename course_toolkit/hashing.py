"""Neutral, symlink-safe hashing helpers for local course evidence."""

import hashlib
from pathlib import Path


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_path(path: Path) -> str:
    """Hash a file or a stable directory tree without following symlinks."""
    if path.is_symlink():
        raise ValueError(f"Cannot hash symlink: {path}")
    if not path.exists():
        raise ValueError(f"Cannot hash missing path: {path}")
    if path.is_file():
        return _hash_file(path)
    if not path.is_dir():
        raise ValueError(f"Cannot hash unsupported path: {path}")

    entries = []
    for candidate in path.rglob("*"):
        if candidate.is_symlink():
            raise ValueError(f"Cannot hash tree containing symlink: {candidate}")
        if not candidate.is_file() or candidate.suffix.lower() == ".zip":
            continue
        entries.append((candidate.relative_to(path).as_posix(), _hash_file(candidate)))
    digest = hashlib.sha256()
    for relative, file_hash in sorted(entries):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()
