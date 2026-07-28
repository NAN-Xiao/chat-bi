# -*- coding: utf-8 -*-
"""为修仙推荐看板中可安全参数化的 SQL 图表启用日期表达式。"""

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
from typing import Any, Collection

import psycopg
from psycopg.rows import dict_row

from core_system_db import core_system_db_config
from xiuxian_dashboard_snapshot import DATASOURCE_ID, EXPECTED_VIEW_IDS, TENANT_ID


START_TOKEN = "{{dashboard_start_yyyymmdd}}"
END_TOKEN = "{{dashboard_end_yyyymmdd}}"
DEFAULT_EXPRESSION = {"version": 1, "mode": "preset", "preset": "past_30_days"}
ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / ".codex-runtime" / "xiuxian-dashboard-date-expression-backups"

_PARTITION_RANGE = re.compile(r"\b(?P<alias>[A-Za-z_][\w]*)\.dt\s+BETWEEN\b", re.IGNORECASE)
_UNSUPPORTED_SEMANTICS = re.compile(
    r"\b(?:cohort|retention|ltv|d1|d3|d7|d14|d30)\b|留存|生命周期",
    re.IGNORECASE,
)
_BOUNDARY_WORDS = ("AND", "OR", "GROUP", "ORDER", "HAVING", "LIMIT", "UNION")


def _is_word_at(value: str, index: int, words: tuple[str, ...]) -> str | None:
    if index > 0 and (value[index - 1].isalnum() or value[index - 1] == "_"):
        return None
    upper = value[index:].upper()
    for word in words:
        if not upper.startswith(word):
            continue
        end = index + len(word)
        if end >= len(value) or not (value[end].isalnum() or value[end] == "_"):
            return word
    return None


def _find_top_level_word(value: str, start: int, words: tuple[str, ...]) -> int:
    depth = 0
    quote = ""
    index = start
    while index < len(value):
        char = value[index]
        if quote:
            if char == "\\" and index + 1 < len(value):
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in ("'", '"', "`"):
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and _is_word_at(value, index, words):
            return index
        index += 1
    return -1


def is_safe_candidate(sql: str) -> bool:
    source = str(sql or "")
    return bool(
        len(_PARTITION_RANGE.findall(source)) == 1
        and "{{dashboard_" not in source
        and "event_realtime" not in source.lower()
        and not _UNSUPPORTED_SEMANTICS.search(source)
    )


def replace_unique_partition_range(sql: str) -> str:
    source = str(sql or "")
    matches = list(_PARTITION_RANGE.finditer(source))
    if len(matches) != 1:
        raise ValueError("SQL 不包含唯一分区日期窗口")
    match = matches[0]
    and_index = _find_top_level_word(source, match.end(), ("AND",))
    if and_index < 0:
        raise ValueError("分区日期窗口缺少结束条件")
    suffix_index = _find_top_level_word(source, and_index + 3, _BOUNDARY_WORDS)
    if suffix_index < 0:
        suffix_index = source.find(";", and_index + 3)
    if suffix_index < 0:
        suffix_index = len(source)
    replacement = f"{match.group('alias')}.dt BETWEEN {START_TOKEN} AND {END_TOKEN}"
    suffix = source[suffix_index:]
    separator = " " if suffix and not suffix[0].isspace() else ""
    result = source[: match.start()] + replacement + separator + suffix
    if result.count(START_TOKEN) != 1 or result.count(END_TOKEN) != 1:
        raise ValueError("受控日期参数数量异常")
    return result


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} 配置无效")
    return value


def _date_field(view: dict[str, Any]) -> str:
    pivot = view.get("pivot") if isinstance(view.get("pivot"), dict) else {}
    configured = str(pivot.get("time_field") or "").strip()
    if configured:
        return configured
    chart = view.get("chart") if isinstance(view.get("chart"), dict) else {}
    axes = chart.get("xAxis") if isinstance(chart.get("xAxis"), list) else []
    for axis in axes:
        if not isinstance(axis, dict):
            continue
        field = str(axis.get("value") or axis.get("name") or "").strip()
        if field:
            return field
    return "dt"


def configure_view(view: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(view)
    source_sql = str(result.get("sql") or "")
    if not is_safe_candidate(source_sql):
        raise ValueError("SQL 不属于可安全迁移的唯一分区日期窗口")
    result["sql"] = replace_unique_partition_range(source_sql)
    time_field = _date_field(result)
    source_config = _mapping(result.setdefault("sourceConfig", {}), "sourceConfig")
    sql_config = _mapping(source_config.setdefault("sql", {}), "sourceConfig.sql")
    builder = _mapping(sql_config.setdefault("builder", {}), "sourceConfig.sql.builder")
    builder.update(
        {
            "dateExpressionPickerEnabled": True,
            "timeField": time_field,
            "timeRange": "expression",
            "timeExpression": copy.deepcopy(DEFAULT_EXPRESSION),
        }
    )
    pivot = _mapping(result.setdefault("pivot", {}), "pivot")
    pivot.update(
        {
            "time_field": time_field,
            "range_enabled": True,
            "client_filter_only": False,
            "date_parameter_type": "yyyymmdd_number",
            "date_expression": copy.deepcopy(DEFAULT_EXPRESSION),
        }
    )
    return result


def stable_json_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canvas(raw: str) -> dict[str, Any]:
    try:
        canvas = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("canvas_view_info 不是合法 JSON") from exc
    if not isinstance(canvas, dict):
        raise RuntimeError("canvas_view_info 不是对象")
    return canvas


def migrate_canvas(
    canvas: dict[str, Any], *, allowed_ids: Collection[str] | None = None
) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    migrated = copy.deepcopy(canvas)
    target_ids = [
        chart_id
        for chart_id, view in canvas.items()
        if (
            isinstance(view, dict)
            and (allowed_ids is None or chart_id in allowed_ids)
            and is_safe_candidate(str(view.get("sql") or ""))
        )
    ]
    unchanged = {
        chart_id: stable_json_hash(view)
        for chart_id, view in canvas.items()
        if chart_id not in target_ids
    }
    for chart_id in target_ids:
        migrated[chart_id] = configure_view(migrated[chart_id])
    return migrated, target_ids, unchanged


def verify_canvas(
    canvas: dict[str, Any], *, target_ids: list[str], unchanged: dict[str, str]
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for chart_id in target_ids:
        view = canvas.get(chart_id)
        if not isinstance(view, dict):
            raise RuntimeError(f"读回缺少目标图表：{chart_id}")
        sql = str(view.get("sql") or "")
        source_config = view.get("sourceConfig") if isinstance(view.get("sourceConfig"), dict) else {}
        sql_config = source_config.get("sql") if isinstance(source_config.get("sql"), dict) else {}
        builder = sql_config.get("builder") if isinstance(sql_config.get("builder"), dict) else {}
        pivot = view.get("pivot") if isinstance(view.get("pivot"), dict) else {}
        if (
            sql.count(START_TOKEN) != 1
            or sql.count(END_TOKEN) != 1
            or builder.get("dateExpressionPickerEnabled") is not True
            or builder.get("timeRange") != "expression"
            or builder.get("timeExpression") != DEFAULT_EXPRESSION
            or pivot.get("range_enabled") is not True
            or pivot.get("client_filter_only") is not False
            or pivot.get("date_parameter_type") != "yyyymmdd_number"
            or pivot.get("date_expression") != DEFAULT_EXPRESSION
        ):
            raise RuntimeError(f"日期配置读回校验失败：{chart_id}")
        result[chart_id] = {
            "sql_sha256": hashlib.sha256(sql.encode("utf-8")).hexdigest(),
            "expression": copy.deepcopy(DEFAULT_EXPRESSION),
        }
    for chart_id, expected_hash in unchanged.items():
        if chart_id not in canvas or stable_json_hash(canvas[chart_id]) != expected_hash:
            raise RuntimeError(f"非目标图表发生变化：{chart_id}")
    return result


def build_migration_plan(
    row: dict[str, Any], *, allowed_ids: Collection[str] = EXPECTED_VIEW_IDS
) -> dict[str, Any] | None:
    old_canvas = row.get("canvas_view_info")
    if not isinstance(old_canvas, str):
        raise RuntimeError("canvas_view_info 类型不是文本")
    canvas = _canvas(old_canvas)
    migrated, target_ids, unchanged = migrate_canvas(canvas, allowed_ids=allowed_ids)
    if not target_ids:
        return None
    new_canvas = json.dumps(migrated, ensure_ascii=False, separators=(",", ":"))
    verify_canvas(migrated, target_ids=target_ids, unchanged=unchanged)
    return {
        "row": row,
        "old_canvas": old_canvas,
        "new_canvas": new_canvas,
        "target_ids": target_ids,
        "unchanged": unchanged,
    }


def _select_recommended_dashboards(cur: Any, *, lock: bool) -> list[dict[str, Any]]:
    cur.execute(
        f"""
        SELECT d.id, d.tenant_id, d.datasource, d.name, d.update_time,
               d.canvas_view_info
        FROM public.core_dashboard d
        WHERE d.tenant_id = %s AND d.datasource = %s
          AND d.type = 'dashboard' AND d.node_type = 'leaf' AND d.status = 1
          AND d.is_default = 1 AND COALESCE(d.delete_flag, 0) = 0
          AND EXISTS (
              SELECT 1
              FROM public.core_dashboard_tree t
              WHERE t.dashboard_id = d.id AND t.tenant_id = d.tenant_id
                AND t.scope = 'default'
          )
        ORDER BY d.id
        {'FOR UPDATE' if lock else ''}
        """,
        (TENANT_ID, DATASOURCE_ID),
    )
    return list(cur.fetchall())


def _select_recommended_dashboard(
    cur: Any, dashboard_id: str, *, lock: bool
) -> dict[str, Any]:
    cur.execute(
        f"""
        SELECT d.id, d.tenant_id, d.datasource, d.name, d.update_time,
               d.canvas_view_info
        FROM public.core_dashboard d
        WHERE d.id = %s AND d.tenant_id = %s AND d.datasource = %s
          AND d.type = 'dashboard' AND d.node_type = 'leaf'
          AND d.status = 1 AND d.is_default = 1 AND COALESCE(d.delete_flag, 0) = 0
          AND EXISTS (
              SELECT 1
              FROM public.core_dashboard_tree t
              WHERE t.dashboard_id = d.id AND t.tenant_id = d.tenant_id
                AND t.scope = 'default'
          )
        {'FOR UPDATE' if lock else ''}
        """,
        (dashboard_id, TENANT_ID, DATASOURCE_ID),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"未找到修仙推荐看板或范围已变化：{dashboard_id}")
    return row


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _write_backup(plans: list[dict[str, Any]]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "tenant_id": TENANT_ID,
        "datasource_id": DATASOURCE_ID,
        "dashboards": [
            {
                "id": str(plan["row"]["id"]),
                "old_canvas_sha256": sha256_text(plan["old_canvas"]),
                "new_canvas_sha256": sha256_text(plan["new_canvas"]),
                "row": {
                    key: _json_value(value) for key, value in plan["row"].items()
                },
            }
            for plan in plans
        ],
    }
    path = BACKUP_DIR / f"xiuxian_recommended_dashboard_date_filters_{time.time_ns()}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path.resolve()


def _read_backup(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("日期控件备份无法读取") from exc
    if (
        payload.get("tenant_id") != TENANT_ID
        or payload.get("datasource_id") != DATASOURCE_ID
        or not isinstance(payload.get("dashboards"), list)
        or not payload["dashboards"]
    ):
        raise RuntimeError("日期控件备份范围不匹配")
    for item in payload["dashboards"]:
        row = item.get("row") if isinstance(item, dict) else None
        old_canvas = row.get("canvas_view_info") if isinstance(row, dict) else None
        if (
            not isinstance(item.get("id"), str)
            or not isinstance(old_canvas, str)
            or item.get("old_canvas_sha256") != sha256_text(old_canvas)
            or not isinstance(item.get("new_canvas_sha256"), str)
        ):
            raise RuntimeError("日期控件备份内容无效")
    return payload


def _build_migration_plans(cur: Any, *, lock: bool) -> list[dict[str, Any]]:
    return [
        plan
        for row in _select_recommended_dashboards(cur, lock=lock)
        if (plan := build_migration_plan(row, allowed_ids=EXPECTED_VIEW_IDS)) is not None
    ]


def _preview_result(plans: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "applied": False,
        "dashboard_count": len(plans),
        "chart_count": sum(len(plan["target_ids"]) for plan in plans),
        "charts": {
            str(plan["row"]["id"]): list(plan["target_ids"])
            for plan in plans
        },
    }


def _apply_plans(cur: Any, plans: list[dict[str, Any]]) -> None:
    for plan in plans:
        row = plan["row"]
        cur.execute(
            """
            UPDATE public.core_dashboard
            SET canvas_view_info = %s, update_time = %s
            WHERE id = %s AND tenant_id = %s AND datasource = %s
              AND canvas_view_info = %s AND COALESCE(delete_flag, 0) = 0
            """,
            (
                plan["new_canvas"],
                int(time.time()),
                row["id"],
                TENANT_ID,
                DATASOURCE_ID,
                plan["old_canvas"],
            ),
        )
        if cur.rowcount != 1:
            raise RuntimeError(f"看板 CAS 更新数量异常：{row['id']}")


def _readback_plans(plans: list[dict[str, Any]]) -> dict[str, Any]:
    verified: dict[str, Any] = {}
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            for plan in plans:
                row = _select_recommended_dashboard(cur, str(plan["row"]["id"]), lock=False)
                verified[str(row["id"])] = verify_canvas(
                    _canvas(row["canvas_view_info"]),
                    target_ids=plan["target_ids"],
                    unchanged=plan["unchanged"],
                )
        conn.rollback()
    return verified


def migrate_recommended_dashboards(*, apply: bool) -> dict[str, Any]:
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            plans = _build_migration_plans(cur, lock=apply)
            if not apply:
                conn.rollback()
                return _preview_result(plans)
            backup_path = _write_backup(plans) if plans else None
            _apply_plans(cur, plans)
            conn.commit()
    try:
        verified = _readback_plans(plans) if plans else {}
    except Exception as exc:
        rollback = (
            f'python tools/enable_xiuxian_recommended_dashboard_date_filters.py '
            f'--restore "{backup_path}"'
        )
        raise RuntimeError(f"写入已提交但读回验证失败；备份：{backup_path}；回滚命令：{rollback}") from exc
    return {
        "applied": True,
        "dashboard_count": len(plans),
        "chart_count": sum(len(plan["target_ids"]) for plan in plans),
        "backup": str(backup_path) if backup_path else None,
        "charts": verified,
    }


def verify_recommended_dashboards() -> dict[str, Any]:
    verified: dict[str, Any] = {}
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            for row in _select_recommended_dashboards(cur, lock=False):
                canvas = _canvas(row["canvas_view_info"])
                target_ids = [
                    chart_id
                    for chart_id, view in canvas.items()
                    if chart_id in EXPECTED_VIEW_IDS
                    and isinstance(view, dict)
                    and str(view.get("sql") or "").count(START_TOKEN) == 1
                    and str(view.get("sql") or "").count(END_TOKEN) == 1
                ]
                if target_ids:
                    verified[str(row["id"])] = verify_canvas(
                        canvas, target_ids=target_ids, unchanged={}
                    )
        conn.rollback()
    if not verified:
        raise RuntimeError("未发现已启用日期控件的修仙推荐看板抽屉")
    return {"verified": True, "charts": verified}


def restore_dashboards(backup_path: Path) -> dict[str, Any]:
    payload = _read_backup(backup_path)
    dashboards = payload["dashboards"]
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            for item in dashboards:
                row = _select_recommended_dashboard(cur, item["id"], lock=True)
                if sha256_text(row["canvas_view_info"]) != item["new_canvas_sha256"]:
                    raise RuntimeError(f"回滚 CAS 哈希不匹配：{item['id']}")
            for item in dashboards:
                old_canvas = item["row"]["canvas_view_info"]
                cur.execute(
                    """
                    UPDATE public.core_dashboard
                    SET canvas_view_info = %s, update_time = %s
                    WHERE id = %s AND tenant_id = %s AND datasource = %s
                      AND canvas_view_info = %s AND COALESCE(delete_flag, 0) = 0
                    """,
                    (
                        old_canvas,
                        int(time.time()),
                        item["id"],
                        TENANT_ID,
                        DATASOURCE_ID,
                        _select_recommended_dashboard(cur, item["id"], lock=False)["canvas_view_info"],
                    ),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"回滚更新数量异常：{item['id']}")
            conn.commit()
    return {"restored": True, "backup": str(backup_path.resolve()), "dashboard_count": len(dashboards)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="备份后写入候选看板")
    mode.add_argument("--verify", action="store_true", help="只读验证已迁移配置")
    mode.add_argument("--restore", type=Path, help="使用指定备份按 CAS 边界回滚")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.restore:
        result = restore_dashboards(args.restore)
    elif args.verify:
        result = verify_recommended_dashboards()
    else:
        result = migrate_recommended_dashboards(apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
