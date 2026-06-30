# -*- coding: utf-8 -*-
"""Repair flam active dashboard SQL from datasource-scoped Data Skills."""

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
from flam_first_zombie_active_dashboard_sql import DATASOURCE_ID, DASHBOARD_ID, TENANT_ID, VIEW_SQL, axis


ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / ".codex-runtime" / "pg-backups"

SYSTEM_DB = core_system_db_config()
UPDATE_BY = "codex"
SKILL_MARKER = "<!-- data-skill-source:flam:first-zombie:active-users -->"
SQL_BLOCK_PATTERN = re.compile(
    r"<!--\s*dashboard-sql:(?P<view_id>[a-f0-9]+)\s*-->\s*```sql\s*(?P<sql>.*?)```",
    re.IGNORECASE | re.DOTALL,
)
ACTIVE_DASHBOARD_VIEW_IDS = (
    "a7a7e09c7289414999a25657fa95d527",
    "839ce2cab673467ab22fe508bf822d61",
    "77aa7f9c7c2c4eb38d821d10379978e7",
    "3ea113a229784c6f9c04b2a7b91d65b6",
    "03c44a9f89f2403ea7a9b168da0a13e8",
    "38a1356c04aa4bd2817a0ec9d396d8b6",
    "f0793fb6af7845c8be2b39e2d7ea523f",
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
        SELECT id, prompt
        FROM public.custom_prompt
        WHERE tenant_id = %s
          AND type = 'DATA_SKILL'
          AND active = TRUE
          AND visible = TRUE
          AND specific_ds = TRUE
          AND datasource_ids @> %s::jsonb
          AND position(%s in COALESCE(prompt, '')) > 0
        ORDER BY id
        LIMIT 1
        """,
        (TENANT_ID, json.dumps([DATASOURCE_ID]), SKILL_MARKER),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("flam active Data Skill not found; run seed_flam_first_zombie_data_skills.py first")

    skill_id, prompt = row
    blocks = {
        match.group("view_id"): match.group("sql").strip()
        for match in SQL_BLOCK_PATTERN.finditer(prompt or "")
    }
    missing = sorted(set(ACTIVE_DASHBOARD_VIEW_IDS).difference(blocks))
    if missing:
        raise RuntimeError(f"Data Skill {skill_id} is missing dashboard SQL blocks: {missing}")
    print(f"skill_id={skill_id}")
    return {view_id: blocks[view_id] for view_id in ACTIVE_DASHBOARD_VIEW_IDS}


def backup_dashboard(row: dict[str, Any]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"flam_active_dashboard_before_skill_sql_repair_{int(time.time())}.json"
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
    spec = VIEW_SQL[view_id]
    chart = view.setdefault("chart", {})
    chart["type"] = spec.chart_type
    chart["title"] = spec.title
    chart["xAxis"] = [axis(field) for field in spec.x_axis]
    chart["yAxis"] = [axis(field) for field in spec.y_axis]
    chart["columns"] = [axis(field) for field in (spec.columns or spec.fields)]
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
        missing_views = sorted(set(ACTIVE_DASHBOARD_VIEW_IDS).difference(canvas_view_info))
        if missing_views:
            raise RuntimeError(f"Expected active dashboard views not found: {missing_views}")

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
        for view_id, sql in sql_blocks.items():
            view = canvas_view_info.get(view_id)
            if not isinstance(view, dict):
                continue
            apply_chart_config(view, view_id, sql)
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
