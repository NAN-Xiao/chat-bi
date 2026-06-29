# -*- coding: utf-8 -*-
"""Repair remaining flam dashboards from datasource-scoped SQL definitions."""

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
from flam_first_zombie_active_dashboard_sql import VIEW_SQL as ACTIVE_VIEW_SQL, axis as active_axis
from flam_first_zombie_dashboard_sql import DATASOURCE_ID, TENANT_ID
from flam_first_zombie_remaining_dashboard_sql import REMAINING_VIEW_SQL, axis as remaining_axis


ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / ".codex-runtime" / "pg-backups"
SYSTEM_DB = core_system_db_config()
UPDATE_BY = "codex"
REALTIME_VIEW_IDS = (
    "e3fe7e4819e64b71b76d9329a3023359",
    "4fc570b4be7d406c9f648d9088f760bb",
    "2149b7abbc6c4cd7ad6f52379e69b15a",
)
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


def load_realtime_sql_blocks(cur: Any) -> dict[str, str]:
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
          AND position('<!-- data-skill-source:flam:first-zombie:timezone-realtime -->' in COALESCE(prompt, '')) > 0
        ORDER BY id
        LIMIT 1
        """,
        (TENANT_ID, json.dumps([DATASOURCE_ID])),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("flam realtime Data Skill not found")
    skill_id, prompt = row
    blocks = {match.group("view_id"): match.group("sql").strip() for match in SQL_BLOCK_PATTERN.finditer(prompt or "")}
    missing = sorted(set(REALTIME_VIEW_IDS).difference(blocks))
    if missing:
        raise RuntimeError(f"Realtime Data Skill {skill_id} missing SQL blocks: {missing}")
    return {view_id: blocks[view_id] for view_id in REALTIME_VIEW_IDS}


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


def _apply_spec(view: dict[str, Any], sql: str, spec: Any, axis_func: Any) -> None:
    chart = view.setdefault("chart", {})
    chart["type"] = spec.chart_type
    chart["title"] = spec.title
    chart["xAxis"] = [axis_func(field) | {"type": "x"} for field in spec.x_axis]
    chart["yAxis"] = [axis_func(field) | {"type": "y"} for field in spec.y_axis]
    chart["columns"] = [axis_func(field) for field in (spec.columns or spec.fields)]
    if spec.chart_type == "funnel":
        chart["showLabel"] = True
    view["datasource"] = DATASOURCE_ID
    view["sql"] = sql.strip()
    clear_result(view, spec.fields)


def apply_chart_config(view: dict[str, Any], view_id: str, realtime_sql: dict[str, str]) -> bool:
    if view_id in REMAINING_VIEW_SQL:
        spec = REMAINING_VIEW_SQL[view_id]
        _apply_spec(view, spec.sql, spec, remaining_axis)
        return True
    if view_id in REALTIME_VIEW_IDS:
        fields_by_view = {
            "e3fe7e4819e64b71b76d9329a3023359": ("时间", "实时在线人数"),
            "4fc570b4be7d406c9f648d9088f760bb": ("小时", "实时付费事件次数"),
            "2149b7abbc6c4cd7ad6f52379e69b15a": ("小时", "累计付费事件次数"),
        }
        x_field, y_field = fields_by_view[view_id]
        chart = view.setdefault("chart", {})
        chart["type"] = "line"
        chart["xAxis"] = [{"name": x_field, "value": x_field, "type": "x"}]
        chart["yAxis"] = [{"name": y_field, "value": y_field, "type": "y"}]
        chart["columns"] = [{"name": x_field, "value": x_field}, {"name": y_field, "value": y_field}]
        view["datasource"] = DATASOURCE_ID
        view["sql"] = realtime_sql[view_id]
        clear_result(view, (x_field, y_field))
        return True
    if view_id == "8b3e5b7179af442e8fded00ae25a0245":
        spec = ACTIVE_VIEW_SQL[view_id]
        _apply_spec(view, spec.sql, spec, active_axis)
        return True
    return False


def backup_dashboard(row: dict[str, Any], backup_path: Path) -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    existing = []
    if backup_path.exists():
        existing = json.loads(backup_path.read_text(encoding="utf-8"))
    existing.append(normalize_row(row))
    backup_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def repair_dashboards(conn: Any, realtime_sql: dict[str, str]) -> None:
    expected = set(REMAINING_VIEW_SQL) | set(REALTIME_VIEW_IDS)
    touched_all: set[str] = set()
    backup_path = BACKUP_DIR / f"flam_remaining_dashboards_before_skill_sql_repair_{int(time.time())}.json"
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, datasource, tenant_id, canvas_view_info
            FROM public.core_dashboard
            WHERE tenant_id = %s
              AND datasource = %s
              AND COALESCE(delete_flag, 0) = 0
              AND type = 'dashboard'
            FOR UPDATE
            """,
            (TENANT_ID, DATASOURCE_ID),
        )
        for dashboard_id, dashboard_name, datasource, tenant_id, canvas_view_info_text in cur.fetchall():
            canvas_view_info = json.loads(canvas_view_info_text or "{}")
            touched: list[str] = []
            for view_id, view in canvas_view_info.items():
                if view_id not in expected or not isinstance(view, dict):
                    continue
                if apply_chart_config(view, view_id, realtime_sql):
                    touched.append(view_id)
                    touched_all.add(view_id)
            if not touched:
                continue
            backup_dashboard(
                {
                    "id": dashboard_id,
                    "name": dashboard_name,
                    "datasource": datasource,
                    "tenant_id": tenant_id,
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
            print(
                json.dumps(
                    {
                        "dashboard_id": dashboard_id,
                        "dashboard_name": dashboard_name,
                        "views": touched,
                        "updated_rows": cur.rowcount,
                    },
                    ensure_ascii=False,
                )
            )
    missing = sorted(expected.difference(touched_all))
    if missing:
        raise RuntimeError(f"Expected remaining views not found in dashboards: {missing}")
    print(json.dumps({"backup": str(backup_path), "repaired_views": len(touched_all)}, ensure_ascii=False))


def main() -> None:
    with psycopg.connect(**SYSTEM_DB) as conn:
        with conn.cursor() as cur:
            realtime_sql = load_realtime_sql_blocks(cur)
        with conn.transaction():
            repair_dashboards(conn, realtime_sql)


if __name__ == "__main__":
    main()
