"""Load local publication credentials without adding a runtime dependency."""

from __future__ import annotations

import os
from pathlib import Path
import re


_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_local_env(path: Path) -> dict[str, str]:
    """Load one dotenv file without overriding the current process environment."""

    path = path.resolve()
    if not path.is_file() or path.is_symlink():
        return {}
    loaded: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"invalid .env entry at line {line_number}")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not _KEY.fullmatch(key):
            raise ValueError(f"invalid .env key at line {line_number}")
        if key in os.environ:
            continue
        value = _value(raw_value)
        os.environ[key] = value
        loaded[key] = value
    return loaded


def load_publication_env(course_root: Path) -> tuple[Path, ...]:
    """Load course-local credentials first, then the toolkit checkout fallback."""

    toolkit_root = Path(__file__).resolve().parents[1]
    candidates = (course_root.resolve() / ".env", toolkit_root / ".env")
    loaded_paths = []
    for candidate in candidates:
        if load_local_env(candidate):
            loaded_paths.append(candidate)
    return tuple(loaded_paths)
