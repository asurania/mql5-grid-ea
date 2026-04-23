from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ENV_PATHS = [
    Path("/home/asurani/Projects/api.env"),
    Path(".env"),
]


def load_env_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_project_env() -> None:
    for path in DEFAULT_ENV_PATHS:
        load_env_file(path)
    _apply_aliases()


def _apply_aliases() -> None:
    aliases = {
        "MASSIVE_API": "MASSIVE_API_KEY",
        "RAPID_CALENDAR_API": "RAPIDAPI_KEY",
        "MASSIVR_BUCKET": "MASSIVE_BUCKET",
    }
    for legacy, canonical in aliases.items():
        if canonical not in os.environ and legacy in os.environ:
            os.environ[canonical] = os.environ[legacy]
