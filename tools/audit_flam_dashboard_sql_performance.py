# -*- coding: utf-8 -*-
"""Run every flam dashboard chart SQL and write a per-chart performance list."""

from __future__ import annotations

import csv
import json
import os
import signal
import sys
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import pymysql

from core_system_db import core_system_db_config, export_postgres_compat_env
from flam_first_zombie_dashboard_sql import DATASOURCE_ID, TENANT_ID


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
OUT_DIR = ROOT / ".codex-runtime" / "flam-sql-audit"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_DB = core_system_db_config()
DEFAULT_TIMEOUT_SEC = int(os.getenv("FLAM_SQL_AUDIT_TIMEOUT_SEC", "120"))
JSONL_PATH = OUT_DIR / "optimized_results.jsonl"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _setup_backend_imports() -> None:
    _load_env_file(ROOT / ".env")
    os.environ.setdefault("SECRET_KEY", "y5txe1mRmS_JpOrUzFzHEu-kIQn3lf7ll0AOv9DQh0s")
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    export_postgres_compat_env(SYSTEM_DB)


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _classify_sql(sql: str) -> str:
    flags: list[str] = []
    checks = (
        ("max_dt", "MAX(dt)"),
        ("order_dt_desc", "ORDER BY dt DESC"),
        ("lag", "LAG("),
        ("row_number", "ROW_NUMBER("),
        ("curdate", "CURDATE()"),
        ("prod", "prod = 110000038"),
        ("useractive", "UserActive"),
        ("user", "`user`"),
        ("event", "`event`"),
    )
    for name, needle in checks:
        if needle in sql:
            flags.append(name)
    if any(event in sql for event in ("UserLogin", "EnterGame", "GameServerLogin", "BISDKAccountLogin", "EPSDKLogin")):
        flags.append("old_login_events")
    return ",".join(flags)


def _load_mysql_config(cur: Any) -> Any:
    _setup_backend_imports()
    from apps.datasource.models.datasource import DatasourceConf
    from apps.datasource.utils.utils import aes_decrypt

    cur.execute(
        """
        SELECT configuration
        FROM public.core_datasource
        WHERE id = %s
          AND tenant_id = %s
        """,
        (DATASOURCE_ID, TENANT_ID),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"Datasource not found: {DATASOURCE_ID}")
    return DatasourceConf(**json.loads(aes_decrypt(row[0])))


def _collect_chart_specs(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT id, name, canvas_view_info
        FROM public.core_dashboard
        WHERE tenant_id = %s
          AND datasource = %s
          AND COALESCE(delete_flag, 0) = 0
          AND type = 'dashboard'
        ORDER BY name, id
        """,
        (TENANT_ID, DATASOURCE_ID),
    )
    specs: list[dict[str, Any]] = []
    for dashboard_id, dashboard_name, canvas_view_info_text in cur.fetchall():
        canvas_view_info = json.loads(canvas_view_info_text or "{}")
        if not isinstance(canvas_view_info, dict):
            continue
        for view_id, view in canvas_view_info.items():
            if not isinstance(view, dict):
                continue
            sql = (view.get("sql") or "").strip()
            if not sql:
                continue
            chart = view.get("chart") or {}
            data = view.get("data") or {}
            specs.append(
                {
                    "dashboard_id": dashboard_id,
                    "dashboard_name": dashboard_name,
                    "view_id": view_id,
                    "title": chart.get("title") or view.get("title") or "",
                    "chart_type": chart.get("type") or view.get("type") or "",
                    "fields": view.get("fields") or data.get("fields") or [],
                    "sql": sql,
                }
            )
    return specs


def _run_sql(conf: Any, sql: str, timeout_sec: int) -> tuple[str, float, int, list[str], str]:
    conn = pymysql.connect(
        host=conf.host,
        port=int(conf.port),
        user=conf.username,
        password=conf.password,
        database=conf.database,
        charset="utf8mb4",
        connect_timeout=10,
        read_timeout=timeout_sec,
        write_timeout=timeout_sec,
        cursorclass=pymysql.cursors.DictCursor,
    )
    start = time.perf_counter()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            fields = [field[0] for field in cur.description or []]
        return "ok", time.perf_counter() - start, len(rows), fields, ""
    except Exception as exc:
        return "error", time.perf_counter() - start, 0, [], f"{type(exc).__name__}: {exc}"
    finally:
        conn.close()


def _write_results(rows: list[dict[str, Any]]) -> tuple[Path, Path]:
    json_path = OUT_DIR / "optimized_results.json"
    csv_path = OUT_DIR / "optimized_results.csv"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    fieldnames = [
        "idx",
        "dashboard_name",
        "dashboard_id",
        "view_id",
        "title",
        "chart_type",
        "status",
        "elapsed_sec",
        "row_count",
        "fields",
        "result_fields",
        "flags",
        "error",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return json_path, csv_path


def _append_jsonl(row: dict[str, Any]) -> None:
    with JSONL_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _load_existing_rows() -> list[dict[str, Any]]:
    if not JSONL_PATH.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in JSONL_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def main() -> None:
    with psycopg.connect(**SYSTEM_DB) as system_conn:
        with system_conn.cursor() as cur:
            conf = _load_mysql_config(cur)
            specs = _collect_chart_specs(cur)

    rows: list[dict[str, Any]] = _load_existing_rows()
    done = {
        (row.get("dashboard_id"), row.get("view_id"))
        for row in rows
        if row.get("status") in {"ok", "error"}
    }
    for idx, spec in enumerate(specs, 1):
        key = (spec["dashboard_id"], spec["view_id"])
        if key in done:
            continue
        status, elapsed, row_count, result_fields, error = _run_sql(
            conf, spec["sql"], DEFAULT_TIMEOUT_SEC
        )
        row = {
            "idx": idx,
            "dashboard_name": spec["dashboard_name"],
            "dashboard_id": spec["dashboard_id"],
            "view_id": spec["view_id"],
            "title": spec["title"],
            "chart_type": spec["chart_type"],
            "status": status,
            "elapsed_sec": round(elapsed, 3),
            "row_count": row_count,
            "fields": json.dumps(spec["fields"], ensure_ascii=False),
            "result_fields": json.dumps([_json_value(v) for v in result_fields], ensure_ascii=False),
            "flags": _classify_sql(spec["sql"]),
            "error": error[:500],
        }
        rows.append(row)
        done.add(key)
        _append_jsonl(row)
        _write_results(rows)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    json_path, csv_path = _write_results(rows)
    ok_count = sum(1 for row in rows if row["status"] == "ok")
    print(
        json.dumps(
            {
                "count": len(rows),
                "ok": ok_count,
                "error": len(rows) - ok_count,
                "json": str(json_path),
                "csv": str(csv_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    if sys.platform != "win32":
        signal.signal(signal.SIGINT, signal.SIG_DFL)
    main()
