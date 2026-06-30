# -*- coding: utf-8 -*-
"""Normalize flam dashboard historical date windows to data max dt.

This repair is intentionally datasource scoped. It preserves existing chart
metric formulas and field mappings, and only replaces system-date windows such
as CURDATE()-29..CURDATE() with the matching fact table's MAX(dt) window.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import psycopg

from core_system_db import core_system_db_config
from flam_first_zombie_dashboard_sql import DATASOURCE_ID, TENANT_ID


ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / ".codex-runtime" / "pg-backups"
SYSTEM_DB = core_system_db_config()
UPDATE_BY = "codex"

OLD_END_RE = r"CAST\s*\(\s*DATE_FORMAT\s*\(\s*CURDATE\s*\(\s*\)\s*,\s*'%Y%m%d'\s*\)\s+AS\s+SIGNED\s*\)"
OLD_START_RE = (
    r"CAST\s*\(\s*DATE_FORMAT\s*\(\s*DATE_SUB\s*\(\s*CURDATE\s*\(\s*\)\s*,\s*"
    r"INTERVAL\s+(?P<days>\d+)\s+DAY\s*\)\s*,\s*'%Y%m%d'\s*\)\s+AS\s+SIGNED\s*\)"
)


def max_dt_expr(table: str) -> str:
    return f"(SELECT MAX(dt) FROM `{table}`)"


def start_dt_expr(table: str, days: str) -> str:
    return (
        "CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST("
        + max_dt_expr(table)
        + f" AS CHAR), '%Y%m%d'), INTERVAL {days} DAY), '%Y%m%d') AS SIGNED)"
    )


def range_expr(table: str, days: str) -> str:
    return f"{start_dt_expr(table, days)} AND {max_dt_expr(table)}"


def replace_qualified_between(sql: str, alias: str, table: str) -> str:
    pattern = re.compile(
        rf"(?P<prefix>\b{re.escape(alias)}\.dt\s+BETWEEN\s+)"
        + OLD_START_RE
        + rf"\s+AND\s+{OLD_END_RE}",
        re.IGNORECASE,
    )
    return pattern.sub(lambda m: m.group("prefix") + range_expr(table, m.group("days")), sql)


def replace_select_max_window(sql: str, table: str) -> str:
    pattern = re.compile(
        rf"SELECT\s+MAX\s*\(\s*dt\s*\)\s+FROM\s+`{re.escape(table)}`\s+WHERE\s+dt\s+BETWEEN\s+"
        + OLD_START_RE
        + rf"\s+AND\s+{OLD_END_RE}",
        re.IGNORECASE,
    )
    return pattern.sub(f"SELECT MAX(dt) FROM `{table}`", sql)


def replace_from_table_unqualified_between(sql: str, table: str) -> str:
    pattern = re.compile(
        rf"(?P<prefix>FROM\s+`{re.escape(table)}`(?:\s+[A-Za-z_][A-Za-z0-9_]*)?\s+WHERE\s+dt\s+BETWEEN\s+)"
        + OLD_START_RE
        + rf"\s+AND\s+{OLD_END_RE}",
        re.IGNORECASE,
    )
    return pattern.sub(lambda m: m.group("prefix") + range_expr(table, m.group("days")), sql)


def replace_only_table_unqualified_between(sql: str, table: str) -> str:
    pattern = re.compile(
        r"(?P<prefix>\bdt\s+BETWEEN\s+)" + OLD_START_RE + rf"\s+AND\s+{OLD_END_RE}",
        re.IGNORECASE,
    )
    return pattern.sub(lambda m: m.group("prefix") + range_expr(table, m.group("days")), sql)


def normalize_sql_date_window(sql: str) -> str:
    next_sql = sql
    for table in ("event", "user"):
        next_sql = replace_select_max_window(next_sql, table)
    next_sql = replace_qualified_between(next_sql, "e", "event")
    next_sql = replace_qualified_between(next_sql, "u", "user")
    next_sql = replace_from_table_unqualified_between(next_sql, "event")
    next_sql = replace_from_table_unqualified_between(next_sql, "user")

    has_event = bool(re.search(r"FROM\s+`event`", next_sql, re.IGNORECASE))
    has_user = bool(re.search(r"FROM\s+`user`", next_sql, re.IGNORECASE))
    if has_event and not has_user:
        next_sql = replace_only_table_unqualified_between(next_sql, "event")
    elif has_user and not has_event:
        next_sql = replace_only_table_unqualified_between(next_sql, "user")
    return next_sql


def clear_result(view: dict[str, Any]) -> None:
    data = view.setdefault("data", {})
    if not isinstance(data, dict):
        data = {}
        view["data"] = data
    fields = view.get("fields") or data.get("fields") or []
    data["fields"] = fields
    data["data"] = []
    data.pop("source_fields", None)
    data.pop("source_data", None)
    data["snapshotRefreshedAt"] = 0
    view["fields"] = fields
    view["status"] = "success"
    view["message"] = ""
    view["dataState"] = "ready"
    view["loadingProgress"] = 100
    view["snapshotRefreshedAt"] = 0


def backup_dashboard(row: dict[str, Any], backup_path: Path) -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    existing = []
    if backup_path.exists():
        existing = json.loads(backup_path.read_text(encoding="utf-8"))
    existing.append(row)
    backup_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def repair_dashboards(conn: Any) -> None:
    backup_path = BACKUP_DIR / f"flam_dashboard_date_windows_before_repair_{int(time.time())}.json"
    changed_views: list[dict[str, Any]] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, canvas_view_info
            FROM public.core_dashboard
            WHERE tenant_id = %s
              AND datasource = %s
              AND COALESCE(delete_flag, 0) = 0
              AND type = 'dashboard'
            FOR UPDATE
            """,
            (TENANT_ID, DATASOURCE_ID),
        )
        for dashboard_id, dashboard_name, canvas_view_info_text in cur.fetchall():
            canvas_view_info = json.loads(canvas_view_info_text or "{}")
            touched: list[str] = []
            for view_id, view in canvas_view_info.items():
                if not isinstance(view, dict):
                    continue
                sql = view.get("sql") or ""
                if not re.search(r"\bCURDATE\s*\(|\bNOW\s*\(", sql, re.IGNORECASE):
                    continue
                next_sql = normalize_sql_date_window(sql)
                if next_sql == sql:
                    continue
                view["sql"] = next_sql
                clear_result(view)
                touched.append(view_id)
            if not touched:
                continue
            backup_dashboard(
                {
                    "id": dashboard_id,
                    "name": dashboard_name,
                    "canvas_view_info": canvas_view_info_text,
                },
                backup_path,
            )
            cur.execute(
                """
                UPDATE public.core_dashboard
                   SET canvas_view_info = %s,
                       update_time = %s,
                       update_by = %s
                 WHERE id = %s
                   AND tenant_id = %s
                """,
                (
                    json.dumps(canvas_view_info, ensure_ascii=False, separators=(",", ":")),
                    int(time.time()),
                    UPDATE_BY,
                    dashboard_id,
                    TENANT_ID,
                ),
            )
            changed_views.append(
                {
                    "dashboard_id": dashboard_id,
                    "dashboard_name": dashboard_name,
                    "views": touched,
                    "updated_rows": cur.rowcount,
                }
            )
    print(json.dumps({"backup": str(backup_path), "changed": changed_views}, ensure_ascii=False, indent=2))


def main() -> None:
    with psycopg.connect(**SYSTEM_DB) as conn:
        with conn.transaction():
            repair_dashboards(conn)


if __name__ == "__main__":
    main()

