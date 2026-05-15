from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Asia/Seoul"


def load_env_file(path: str | Path | None = None) -> None:
    env_path = Path(path or os.environ.get("CHO_WORKS_ENV_FILE", ".env")).expanduser()
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and value and key not in os.environ:
            os.environ[key] = value


load_env_file()


def database_path() -> Path:
    override = os.environ.get("CHO_WORKS_DB_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cho-works" / "cho_works.sqlite3"


def current_date_iso() -> str:
    return datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).date().isoformat()
