# -*- coding: utf-8 -*-
"""已安全下线的 First Zombie 广域日期窗口修复入口。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from flam_first_zombie_date_sql import complete_business_dt_expr


ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / ".codex-runtime" / "pg-backups"
UPDATE_BY = "codex"
STRICT_MIGRATION_SCRIPT = "tools/repair_flam_first_zombie_semantic_dashboards.py"

OLD_END_RE = r"CAST\s*\(\s*DATE_FORMAT\s*\(\s*CURDATE\s*\(\s*\)\s*,\s*'%Y%m%d'\s*\)\s+AS\s+SIGNED\s*\)"
OLD_START_RE = (
    r"CAST\s*\(\s*DATE_FORMAT\s*\(\s*DATE_SUB\s*\(\s*CURDATE\s*\(\s*\)\s*,\s*"
    r"INTERVAL\s+(?P<days>\d+)\s+DAY\s*\)\s*,\s*'%Y%m%d'\s*\)\s+AS\s+SIGNED\s*\)"
)


def start_dt_expr(table: str, days: str) -> str:
    del table
    return complete_business_dt_expr(max(int(days) - 1, 0))


def range_expr(table: str, days: str) -> str:
    return f"{start_dt_expr(table, days)} AND {complete_business_dt_expr()}"


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
    del table
    return pattern.sub(complete_business_dt_expr(), sql)


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


def _raise_legacy_repair_disabled() -> None:
    raise RuntimeError(
        "该广域日期窗口修复脚本已安全下线，避免改写未审计组件；"
        f"请使用 {STRICT_MIGRATION_SCRIPT}。"
    )


def repair_dashboards(conn: Any) -> None:
    del conn
    _raise_legacy_repair_disabled()


def main() -> None:
    _raise_legacy_repair_disabled()


if __name__ == "__main__":
    main()

