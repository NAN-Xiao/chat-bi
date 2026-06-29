# -*- coding: utf-8 -*-
"""Repair flam core dashboard SQL and chart mappings from datasource-scoped Data Skills."""

from __future__ import annotations

import json
import re
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg

from core_system_db import core_system_db_config
from flam_first_zombie_core_dashboard_sql import (
    CORE_DASHBOARD_VIEW_IDS,
    CORE_DASHBOARD_VIEW_SQL,
    DASHBOARD_ID,
    DATASOURCE_ID,
    TENANT_ID,
    axis,
)


ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / ".codex-runtime" / "pg-backups"

SYSTEM_DB = core_system_db_config()
UPDATE_BY = "codex"
SKILL_MARKER_PREFIX = "<!-- data-skill-source:flam:first-zombie:"
SQL_BLOCK_PATTERN = re.compile(
    r"<!--\s*dashboard-sql:(?P<view_id>[a-f0-9]+)\s*-->\s*```sql\s*(?P<sql>.*?)```",
    re.IGNORECASE | re.DOTALL,
)


def json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: json_value(value) for key, value in row.items()}


def load_skill_sql_blocks(cur: Any) -> dict[str, str]:
    cur.execute(
        """
        SELECT id, name, prompt
        FROM public.custom_prompt
        WHERE tenant_id = %s
          AND type = 'DATA_SKILL'
          AND active = TRUE
          AND visible = TRUE
          AND specific_ds = TRUE
          AND datasource_ids @> %s::jsonb
          AND position(%s in COALESCE(prompt, '')) > 0
        ORDER BY id
        """,
        (TENANT_ID, json.dumps([DATASOURCE_ID]), SKILL_MARKER_PREFIX),
    )
    blocks: dict[str, str] = {}
    owners: dict[str, str] = {}
    duplicates: list[dict[str, str]] = []
    skill_ids: list[int] = []
    for skill_id, name, prompt in cur.fetchall():
        skill_ids.append(int(skill_id))
        for match in SQL_BLOCK_PATTERN.finditer(prompt or ""):
            view_id = match.group("view_id")
            sql = match.group("sql").strip()
            if view_id in blocks and blocks[view_id] != sql:
                duplicates.append({"view_id": view_id, "first_owner": owners[view_id], "second_owner": str(name)})
            blocks[view_id] = sql
            owners[view_id] = str(name)
    if duplicates:
        raise RuntimeError(f"Conflicting dashboard SQL blocks: {duplicates}")
    missing = sorted(set(CORE_DASHBOARD_VIEW_IDS).difference(blocks))
    if missing:
        raise RuntimeError(f"Data Skills are missing core dashboard SQL blocks: {missing}")
    print(f"skills={skill_ids}")
    return {view_id: blocks[view_id] for view_id in CORE_DASHBOARD_VIEW_IDS}


def backup_dashboard(row: dict[str, Any]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"flam_core_dashboard_before_skill_sql_repair_{int(time.time())}.json"
    path.write_text(json.dumps(normalize_row(row), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def clear_result(view: dict[str, Any], fields: tuple[str, ...]) -> None:
    data = view.setdefault("data", {})
    if not isinstance(data, dict):
        data = {}
        view["data"] = data
    data["fields"] = list(fields)
    data["data"] = []
    data.pop("source_fields", None)
    data.pop("source_data", None)
    data["snapshotRefreshedAt"] = 0
    view["fields"] = list(fields)
    view["status"] = "success"
    view["message"] = ""
    view["dataState"] = "ready"
    view["loadingProgress"] = 100
    view["snapshotRefreshedAt"] = 0


def apply_chart_config(view: dict[str, Any], view_id: str, sql: str) -> None:
    spec = CORE_DASHBOARD_VIEW_SQL[view_id]
    chart = view.setdefault("chart", {})
    chart["type"] = spec.chart_type
    chart["title"] = spec.title
    chart["xAxis"] = [axis(field) for field in spec.x_axis]
    chart["yAxis"] = [axis(field) for field in spec.y_axis]
    chart["columns"] = [axis(field) for field in (spec.columns or spec.fields)]
    if spec.chart_type == "funnel":
        chart["showLabel"] = True
    view["datasource"] = DATASOURCE_ID
    view["sql"] = sql.strip()
    clear_result(view, spec.fields)


def repair_dashboard(system_conn: Any, sql_blocks: dict[str, str]) -> None:
    with system_conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, datasource, tenant_id, canvas_view_info, update_time
            FROM public.core_dashboard
            WHERE id = %s
              AND tenant_id = %s
              AND datasource = %s
              AND COALESCE(delete_flag, 0) = 0
              AND type = 'dashboard'
            FOR UPDATE
            """,
            (DASHBOARD_ID, TENANT_ID, DATASOURCE_ID),
        )
        dashboard = cur.fetchone()
        if not dashboard:
            raise RuntimeError(f"Dashboard not found: {DASHBOARD_ID}")
        dashboard_id, dashboard_name, datasource, tenant_id, canvas_view_info_text, _update_time = dashboard
        canvas_view_info = json.loads(canvas_view_info_text or "{}")
        missing_views = sorted(set(CORE_DASHBOARD_VIEW_IDS).difference(canvas_view_info))
        if missing_views:
            raise RuntimeError(f"Expected core dashboard views not found: {missing_views}")

        backup_path = backup_dashboard(
            {
                "id": dashboard_id,
                "name": dashboard_name,
                "datasource": datasource,
                "tenant_id": tenant_id,
                "canvas_view_info": canvas_view_info_text,
            }
        )
        touched: list[str] = []
        for view_id in CORE_DASHBOARD_VIEW_IDS:
            view = canvas_view_info.get(view_id)
            if not isinstance(view, dict):
                continue
            apply_chart_config(view, view_id, sql_blocks[view_id])
            touched.append(view_id)

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
                DASHBOARD_ID,
                TENANT_ID,
            ),
        )
        print(
            json.dumps(
                {
                    "dashboard_id": dashboard_id,
                    "dashboard_name": dashboard_name,
                    "views": touched,
                    "backup": str(backup_path),
                    "updated_rows": cur.rowcount,
                },
                ensure_ascii=False,
            )
        )


def main() -> None:
    with psycopg.connect(**SYSTEM_DB) as system_conn:
        with system_conn.cursor() as cur:
            sql_blocks = load_skill_sql_blocks(cur)
        with system_conn.transaction():
            repair_dashboard(system_conn, sql_blocks)


if __name__ == "__main__":
    main()
