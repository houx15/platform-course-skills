import json
import os
from pathlib import Path
import tempfile
from typing import Any


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON at {path}: {exc}") from exc


def dump_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def write_json_atomic(path: Path, data: Any, *, reject_symlinks: bool = False) -> None:
    """Atomically write formatted JSON without predictable temporary paths.

    Callers that operate inside a confined evidence root can opt into rejecting
    symlinked output components. The default remains compatible with existing
    writers: replacing a destination symlink is safe because ``replace`` does
    not follow it.
    """
    if reject_symlinks and path.parent.is_symlink():
        raise ValueError("JSON destination directory may not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    if reject_symlinks and path.is_symlink():
        raise ValueError("JSON destination may not be a symlink")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(dump_json(data).encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_fd = os.open(path.parent, directory_flags)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()
