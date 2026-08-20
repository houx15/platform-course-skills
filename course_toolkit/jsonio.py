import json
import os
import errno
from pathlib import Path
import secrets
import stat
from typing import Any, Optional, Tuple


def _unsupported_directory_sync_error(exc: OSError) -> bool:
    unsupported = {errno.EINVAL, errno.ENOTSUP, getattr(errno, "EOPNOTSUPP", errno.ENOTSUP)}
    if exc.errno in unsupported:
        return True
    return os.name == "nt" and exc.errno in {errno.EACCES, errno.EPERM}


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON at {path}: {exc}") from exc


def dump_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _existing_mode(path: Path) -> Optional[int]:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(metadata.st_mode):
        return None
    return stat.S_IMODE(metadata.st_mode)


def _open_secure_temp(parent: Path, name: str, mode: int) -> Tuple[int, Path]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    for _ in range(32):
        temporary = parent / f".{name}.{secrets.token_hex(16)}.tmp"
        try:
            return os.open(temporary, flags, mode), temporary
        except FileExistsError:
            continue
    raise OSError("unable to allocate a unique temporary file")


def _fsync_directory(parent: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(parent, flags)
    except OSError as exc:
        if _unsupported_directory_sync_error(exc):
            return
        raise
    try:
        try:
            os.fsync(descriptor)
        except OSError as exc:
            if not _unsupported_directory_sync_error(exc):
                raise
    finally:
        os.close(descriptor)


def write_text_atomic(path: Path, text: str, *, reject_symlinks: bool = False) -> None:
    """Write UTF-8 text atomically with secure temp allocation and durable replace.

    Existing regular-file permission bits are retained. New artifacts request
    mode 0644 from the operating system (and therefore remain subject to the
    active umask). Directory fsync is best-effort where a platform lacks it.
    """
    if reject_symlinks and path.parent.is_symlink():
        raise ValueError("destination directory may not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    if reject_symlinks and path.is_symlink():
        raise ValueError("destination may not be a symlink")
    existing_mode = _existing_mode(path)
    mode = 0o644 if existing_mode is None else existing_mode
    descriptor, temporary = _open_secure_temp(path.parent, path.name, mode)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_json_atomic(path: Path, data: Any, *, reject_symlinks: bool = False) -> None:
    """Atomically write formatted JSON using the shared secure text primitive."""
    write_text_atomic(path, dump_json(data), reject_symlinks=reject_symlinks)
