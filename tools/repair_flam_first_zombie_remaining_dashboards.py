# -*- coding: utf-8 -*-
"""已安全下线的 First Zombie 广域看板修复入口。"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from flam_first_zombie_active_dashboard_sql import VIEW_SQL as ACTIVE_VIEW_SQL, axis as active_axis
from flam_first_zombie_dashboard_sql import DATASOURCE_ID, TENANT_ID
from flam_first_zombie_remaining_dashboard_sql import REMAINING_VIEW_SQL, axis as remaining_axis


ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / ".codex-runtime" / "pg-backups"
UPDATE_BY = "codex"
STRICT_MIGRATION_SCRIPT = "tools/repair_flam_first_zombie_semantic_dashboards.py"
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
          AND datasource_ids = %s::jsonb
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
            "e3fe7e4819e64b71b76d9329a3023359": ("time_label", "时间", "online_users", "实时在线人数"),
            "4fc570b4be7d406c9f648d9088f760bb": ("hour_label", "小时", "pay_count", "实时付费事件次数"),
            "2149b7abbc6c4cd7ad6f52379e69b15a": ("hour_label", "小时", "cumulative_pay_count", "累计付费事件次数"),
        }
        x_field, x_name, y_field, y_name = fields_by_view[view_id]
        chart = view.setdefault("chart", {})
        chart["type"] = "line"
        chart["xAxis"] = [{"name": x_name, "value": x_field, "type": "x"}]
        chart["yAxis"] = [{"name": y_name, "value": y_field, "type": "y"}]
        chart["columns"] = [{"name": x_name, "value": x_field}, {"name": y_name, "value": y_field}]
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


def missing_required_views(touched_view_ids: set[str]) -> list[str]:
    """仅要求每份看板都包含剩余看板定义，实时组件可按部署情况缺失。"""
    return sorted(set(REMAINING_VIEW_SQL).difference(touched_view_ids))


def _raise_legacy_repair_disabled() -> None:
    raise RuntimeError(
        "该广域修复脚本已安全下线，避免覆盖未审计组件；"
        f"请使用 {STRICT_MIGRATION_SCRIPT}。"
    )


def repair_dashboards(conn: Any, realtime_sql: dict[str, str]) -> None:
    del conn, realtime_sql
    _raise_legacy_repair_disabled()


def main() -> None:
    _raise_legacy_repair_disabled()


if __name__ == "__main__":
    main()
