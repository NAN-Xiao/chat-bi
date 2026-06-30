# -*- coding: utf-8 -*-
"""Repair flam dashboard statistic SQL from datasource-scoped Data Skills."""

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
from flam_first_zombie_dashboard_sql import DATASOURCE_ID, TENANT_ID, VIEW_SQL, axis


ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / ".codex-runtime" / "pg-backups"

SYSTEM_DB = core_system_db_config()
UPDATE_BY = "codex"
SKILL_MARKER = "<!-- data-skill-source:flam:first-zombie:"
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
        (TENANT_ID, json.dumps([DATASOURCE_ID]), SKILL_MARKER),
    )
    blocks: dict[str, str] = {}
    skill_ids: list[int] = []
    for skill_id, _name, prompt in cur.fetchall():
        skill_ids.append(int(skill_id))
        for match in SQL_BLOCK_PATTERN.finditer(prompt or ""):
            view_id = match.group("view_id")
            blocks[view_id] = match.group("sql").strip()
    missing = sorted(set(VIEW_SQL).difference(blocks))
    if missing:
        raise RuntimeError(f"Data Skills are missing dashboard SQL blocks: {missing}")
    print(f"skills={skill_ids}")
    return {view_id: blocks[view_id] for view_id in VIEW_SQL}


def backup_dashboard(row: dict[str, Any]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"flam_dashboard_statistics_before_repair_{int(time.time())}.json"
    existing = []
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
    existing.append(normalize_row(row))
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _clear_result(view: dict[str, Any], fields: tuple[str, ...]) -> None:
    data = view.setdefault("data", {})
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


def _apply_chart_config(view: dict[str, Any], view_id: str, sql: str) -> None:
    spec = VIEW_SQL[view_id]
    chart = view.setdefault("chart", {})
    chart["type"] = spec.chart_type
    chart["title"] = spec.title
    chart["xAxis"] = [axis(field) for field in spec.x_axis]
    chart["yAxis"] = [axis(field) for field in spec.y_axis]
    if y_axis_semantics := getattr(spec, "y_axis_semantics", None):
        for item in chart["yAxis"]:
            if semantics := y_axis_semantics.get(item.get("value")):
                item.update(semantics)
    if series_axis := getattr(spec, "series_axis", ()):
        chart["series"] = [axis(field) for field in series_axis]
    chart["columns"] = [axis(field) for field in (spec.columns or spec.fields)]
    if pivot := getattr(spec, "pivot", None):
        view["pivot"] = pivot
    view["datasource"] = DATASOURCE_ID
    view["sql"] = sql.strip()
    _clear_result(view, spec.fields)


def repair_dashboards(system_conn: Any, sql_blocks: dict[str, str]) -> None:
    by_dashboard: dict[str, list[str]] = {}
    with system_conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, datasource, tenant_id, canvas_view_info, update_time
            FROM public.core_dashboard
            WHERE tenant_id = %s
              AND datasource = %s
              AND COALESCE(delete_flag, 0) = 0
              AND type = 'dashboard'
            FOR UPDATE
            """,
            (TENANT_ID, DATASOURCE_ID),
        )
        dashboards = cur.fetchall()
        for dashboard_id, dashboard_name, datasource, tenant_id, canvas_view_info_text, _update_time in dashboards:
            canvas_view_info = json.loads(canvas_view_info_text or "{}")
            touched: list[str] = []
            for view_id, sql in sql_blocks.items():
                view = canvas_view_info.get(view_id)
                if not isinstance(view, dict):
                    continue
                _apply_chart_config(view, view_id, sql)
                touched.append(view_id)
            if not touched:
                continue
            backup_path = backup_dashboard(
                {
                    "id": dashboard_id,
                    "name": dashboard_name,
                    "datasource": datasource,
                    "tenant_id": tenant_id,
                    "canvas_view_info": canvas_view_info_text,
                }
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
            by_dashboard[str(dashboard_name)] = touched
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
    missing_views = sorted(set(VIEW_SQL).difference({view_id for ids in by_dashboard.values() for view_id in ids}))
    if missing_views:
        raise RuntimeError(f"Expected views not found in any dashboard: {missing_views}")


def main() -> None:
    with psycopg.connect(**SYSTEM_DB) as system_conn:
        with system_conn.cursor() as cur:
            sql_blocks = load_skill_sql_blocks(cur)
        with system_conn.transaction():
            repair_dashboards(system_conn, sql_blocks)


if __name__ == "__main__":
    main()
