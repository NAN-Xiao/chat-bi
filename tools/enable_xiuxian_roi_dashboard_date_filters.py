# -*- coding: utf-8 -*-
"""为修仙 ROI 看板启用完整 360 日 cohort 口径的日期表达式。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from core_system_db import core_system_db_config


ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / ".codex-runtime" / "dashboard-date-expression-backups"
TENANT_ID = 7482727237662281728
DASHBOARD_NAME = "ROI看板"
VIEW_IDS = {
    "983cf36003f64ca187adca08f547e449",
    "af4fa5ca158342f99e7c3c765e71875d",
    "73eb56330b9248be900ca0e7b6c73a75",
    "2196557720910471168",
}
DEFAULT_EXPRESSION = {"version": 1, "mode": "preset", "preset": "past_30_days"}
START_TOKEN = "{{dashboard_start_yyyymmdd}}"
END_TOKEN = "{{dashboard_end_yyyymmdd}}"

_FIXED_COHORT_WINDOW = re.compile(
    r"""(?P<alias>[A-Za-z_][\w]*)\.dt\s*>=\s*
        CAST\(DATE_FORMAT\(DATE_SUB\(CURDATE\(\),\s*INTERVAL\s+21\s+DAY\),\s*'%Y%m%d'\)\s+AS\s+BIGINT\)\s*
        AND\s*(?P=alias)\.dt\s*<=\s*
        CAST\(DATE_FORMAT\(DATE_SUB\(CURDATE\(\),\s*INTERVAL\s+1\s+DAY\),\s*'%Y%m%d'\)\s+AS\s+BIGINT\)""",
    re.IGNORECASE | re.VERBOSE,
)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _cohort_window(match: re.Match[str]) -> str:
    alias = match.group("alias")
    return f"""{alias}.dt >= CAST(DATE_FORMAT(
            DATE_SUB(STR_TO_DATE(CAST({START_TOKEN} AS CHAR), '%Y%m%d'), INTERVAL 360 DAY),
            '%Y%m%d'
        ) AS BIGINT)
        AND {alias}.dt <= CAST(DATE_FORMAT(
            DATE_SUB(STR_TO_DATE(CAST({END_TOKEN} AS CHAR), '%Y%m%d'), INTERVAL 360 DAY),
            '%Y%m%d'
        ) AS BIGINT)"""


def configure_roi_view(view: dict[str, Any]) -> dict[str, Any]:
    """将所选日期范围映射为提前 360 天的完整 ROI cohort。"""
    result = copy.deepcopy(view)
    sql = str(result.get("sql") or "")
    if START_TOKEN not in sql and END_TOKEN not in sql:
        migrated_sql, replacements = _FIXED_COHORT_WINDOW.subn(_cohort_window, sql)
        if replacements < 2:
            raise ValueError("ROI SQL 不包含预期的固定 ROI cohort 窗口")
        result["sql"] = migrated_sql
    elif sql.count(START_TOKEN) < 2 or sql.count(START_TOKEN) != sql.count(END_TOKEN):
        raise ValueError("ROI SQL 的日期参数数量异常")

    source_config = result.setdefault("sourceConfig", {})
    if not isinstance(source_config, dict):
        raise ValueError("sourceConfig 配置无效")
    sql_config = source_config.setdefault("sql", {})
    if not isinstance(sql_config, dict):
        raise ValueError("sourceConfig.sql 配置无效")
    builder = sql_config.setdefault("builder", {})
    if not isinstance(builder, dict):
        raise ValueError("sourceConfig.sql.builder 配置无效")
    builder.update(
        {
            "dateExpressionPickerEnabled": True,
            "timeField": "投放日期",
            "timeRange": "expression",
            "timeExpression": copy.deepcopy(DEFAULT_EXPRESSION),
        }
    )

    pivot = result.setdefault("pivot", {})
    if not isinstance(pivot, dict):
        raise ValueError("pivot 配置无效")
    pivot.update(
        {
            "time_field": "投放日期",
            "range_enabled": True,
            "client_filter_only": False,
            "date_parameter_type": "yyyymmdd_number",
            "date_expression": copy.deepcopy(DEFAULT_EXPRESSION),
        }
    )
    return result


def _canvas(raw: str) -> dict[str, Any]:
    try:
        canvas = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("canvas_view_info 不是合法 JSON") from exc
    if not isinstance(canvas, dict):
        raise RuntimeError("canvas_view_info 不是对象")
    return canvas


def _verify(view: dict[str, Any]) -> None:
    sql = str(view.get("sql") or "")
    source_config = view.get("sourceConfig") if isinstance(view.get("sourceConfig"), dict) else {}
    sql_config = source_config.get("sql") if isinstance(source_config.get("sql"), dict) else {}
    builder = sql_config.get("builder") if isinstance(sql_config.get("builder"), dict) else {}
    pivot = view.get("pivot") if isinstance(view.get("pivot"), dict) else {}
    if (
        sql.count(START_TOKEN) < 2
        or sql.count(START_TOKEN) != sql.count(END_TOKEN)
        or sql.count("INTERVAL 360 DAY") != sql.count(START_TOKEN) * 2
        or builder.get("dateExpressionPickerEnabled") is not True
        or builder.get("timeExpression") != DEFAULT_EXPRESSION
        or pivot.get("time_field") != "投放日期"
        or pivot.get("date_parameter_type") != "yyyymmdd_number"
        or pivot.get("date_expression") != DEFAULT_EXPRESSION
    ):
        raise RuntimeError("ROI 日期控件读回校验失败")


def _backup(row: dict[str, Any], new_canvas: str) -> str:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"xiuxian_roi_date_filters_{row['id']}_{time.time_ns()}.json"
    payload = {
        "dashboard_id": row["id"],
        "tenant_id": row["tenant_id"],
        "old_canvas_sha256": _hash(row["canvas_view_info"]),
        "new_canvas_sha256": _hash(new_canvas),
        "row": {key: _json_value(value) for key, value in row.items()},
    }
    backup.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(backup.resolve())


def migrate(*, apply: bool) -> dict[str, Any]:
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, tenant_id, name, update_time, canvas_view_info
                FROM public.core_dashboard
                WHERE tenant_id = %s AND name = %s AND type = 'dashboard' AND node_type = 'leaf'
                  AND status = 1 AND is_default = 1 AND COALESCE(delete_flag, 0) = 0
                {'FOR UPDATE' if apply else ''}
                """,
                (TENANT_ID, DASHBOARD_NAME),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError("未找到修仙 ROI 看板")
            canvas = _canvas(row["canvas_view_info"])
            if not VIEW_IDS.issubset(canvas):
                raise RuntimeError("修仙 ROI 看板缺少预期图表")

            for view_id in VIEW_IDS:
                view = canvas.get(view_id)
                if not isinstance(view, dict):
                    raise RuntimeError(f"ROI 图表配置无效：{view_id}")
                canvas[view_id] = configure_roi_view(view)
                _verify(canvas[view_id])

            new_canvas = json.dumps(canvas, ensure_ascii=False, separators=(",", ":"))
            changed = new_canvas != row["canvas_view_info"]
            result = {"applied": apply, "changed": changed, "dashboard_id": row["id"], "view_ids": sorted(VIEW_IDS)}
            if not apply or not changed:
                conn.rollback()
                return result

            backup = _backup(row, new_canvas)
            cur.execute(
                """
                UPDATE public.core_dashboard
                SET canvas_view_info = %s, update_time = %s
                WHERE id = %s AND tenant_id = %s AND canvas_view_info = %s
                  AND COALESCE(delete_flag, 0) = 0
                """,
                (new_canvas, int(time.time()), row["id"], TENANT_ID, row["canvas_view_info"]),
            )
            if cur.rowcount != 1:
                raise RuntimeError("修仙 ROI 看板 CAS 更新失败")
            conn.commit()
            result["backup"] = backup
            return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="备份后写入目标看板")
    args = parser.parse_args()
    print(json.dumps(migrate(apply=args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
