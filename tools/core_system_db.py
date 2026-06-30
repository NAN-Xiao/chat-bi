"""Shared core system database defaults for local tooling.

Tool scripts write platform metadata to the Shuzhi system database. SHUZHI_DB_*
is the authoritative endpoint. POSTGRES_* is exported only as compatibility for
older backend helpers that still read those variable names.
"""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path
from typing import Any


DEFAULT_CORE_DB = {
    "host": "10.1.5.28",
    "port": 5432,
    "dbname": "zhishu_bi",
    "user": "root",
    "password": "Password123@pg",
}

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_root_env(root: Path) -> None:
    env_path = root / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _env(name: str, default: Any) -> Any:
    value = os.getenv(name)
    if value not in (None, ""):
        return value
    return default


def core_system_db_config() -> dict[str, Any]:
    load_root_env(REPO_ROOT)
    return {
        "host": _env("SHUZHI_DB_HOST", DEFAULT_CORE_DB["host"]),
        "port": int(_env("SHUZHI_DB_PORT", DEFAULT_CORE_DB["port"])),
        "dbname": _env("SHUZHI_DB_DB", DEFAULT_CORE_DB["dbname"]),
        "user": _env("SHUZHI_DB_USER", DEFAULT_CORE_DB["user"]),
        "password": _env("SHUZHI_DB_PASSWORD", DEFAULT_CORE_DB["password"]),
    }


def export_postgres_compat_env(db: dict[str, Any]) -> None:
    os.environ.setdefault("SHUZHI_DB_HOST", str(db["host"]))
    os.environ.setdefault("SHUZHI_DB_PORT", str(db["port"]))
    os.environ.setdefault("SHUZHI_DB_DB", str(db["dbname"]))
    os.environ.setdefault("SHUZHI_DB_USER", str(db["user"]))
    os.environ.setdefault("SHUZHI_DB_PASSWORD", str(db["password"]))
    os.environ.setdefault("POSTGRES_SERVER", str(db["host"]))
    os.environ.setdefault("POSTGRES_PORT", str(db["port"]))
    os.environ.setdefault("POSTGRES_DB", str(db["dbname"]))
    os.environ.setdefault("POSTGRES_USER", str(db["user"]))
    os.environ.setdefault("POSTGRES_PASSWORD", str(db["password"]))


def core_system_db_url(driver: str = "postgresql+psycopg") -> str:
    db = core_system_db_config()
    user = urllib.parse.quote(str(db["user"]))
    password = urllib.parse.quote(str(db["password"]))
    database = urllib.parse.quote(str(db["dbname"]))
    return f"{driver}://{user}:{password}@{db['host']}:{db['port']}/{database}"
