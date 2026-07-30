# -*- coding: utf-8 -*-
"""为指定“我的看板”ROI 图表启用受控日期表达式。

默认只读预演；`--apply` 才写入，`--verify` 只读验证，`--restore` 使用备份回滚。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
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

DASHBOARD_ID = "4f08e75945c3498486963e70f3c75688"
TENANT_ID = 7482727237662281728
CREATE_BY = "7482253745313550336"
EXPECTED_CANVAS_SHA256 = "934fe61b112d8fa1d624552185f6194a4651f5ca2afbe4d9f7f0c468463fd7da"
EXPECTED = {
    "2195201518565761024": (
        "12741359f1bda5147cbcf9cd21cfe98065cdbcacacb30b54e7bd772c9f3e61c4",
        "2201f2fca62029ab00ac6d4db2fe8a4f0fbc74484530010ef0c0419543c02cf6",
    ),
    "2195202821815705600": (
        "488033a873ebb1cd916b45b74de135b15c6a27192f035e954479a2209bae0532",
        "258234e132d744e721cd4464d44955c2c7d009d516cfa41b5cd7f46840b4c8ac",
    ),
    "2195203352126726144": (
        "865f76e131ce1ed57e02741df015e53f67372d29de1f09e243c153d737c41cb5",
        "5c67632b43d4a22e7285a94e6dcca551681677d00588bc817fd8e801b817f0c0",
    ),
    "2196527317097029632": (
        "12741359f1bda5147cbcf9cd21cfe98065cdbcacacb30b54e7bd772c9f3e61c4",
        "8de04640ed8057f730a2d9f7e6e040bc3c31b9f30e62492135660e8dc2c01190",
    ),
}
EXPECTED_TITLES = {
    "2195201518565761024": "ROI总览",
    "2195202821815705600": "ROI地区总览",
    "2195203352126726144": "ROI广告地区总览",
    "2196527317097029632": "安装投放趋势",
}

LEGACY_START = "CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 21 DAY), '%Y%m%d') AS BIGINT)"
LEGACY_END = "CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS BIGINT)"
START_TOKEN = "{{dashboard_start_yyyymmdd}}"
END_TOKEN = "{{dashboard_end_yyyymmdd}}"
DEFAULT_EXPRESSION = {"version": 1, "mode": "preset", "preset": "past_30_days"}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_json_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(raw)


def config_fingerprint(view: dict[str, Any]) -> str:
    value = {
        key: view.get(key)
        for key in ("sourceConfig", "pivot", "datasource", "title", "name")
    }
    return stable_json_hash(value)


def migrate_sql(sql: str) -> str:
    if sql.count(LEGACY_START) != 4 or sql.count(LEGACY_END) != 4:
        raise ValueError("固定日期条件数量不是 4 对")
    migrated = sql.replace(LEGACY_START, START_TOKEN).replace(LEGACY_END, END_TOKEN)
    if migrated.count(START_TOKEN) != 4 or migrated.count(END_TOKEN) != 4:
        raise ValueError("受控日期参数数量不是 4 对")
    return migrated


def migrate_view(view: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(view)
    result["sql"] = migrate_sql(str(result.get("sql") or ""))
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
            "timeField": "dt",
            "timeRange": "expression",
            "timeExpression": copy.deepcopy(DEFAULT_EXPRESSION),
        }
    )
    pivot = result.setdefault("pivot", {})
    if not isinstance(pivot, dict):
        raise ValueError("pivot 配置无效")
    pivot.update(
        {
            "enabled": False,
            "time_field": "dt",
            "range_enabled": True,
            "date_parameter_type": "yyyymmdd_number",
            "date_expression": copy.deepcopy(DEFAULT_EXPRESSION),
        }
    )
    return result


def _canvas(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("canvas_view_info 不是合法 JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("canvas_view_info 不是对象")
    return value


def validate_baseline(raw_canvas: str, canvas: dict[str, Any]) -> None:
    if sha256_text(raw_canvas) != EXPECTED_CANVAS_SHA256:
        raise RuntimeError("CAS 哈希不匹配：看板 canvas 已发生变化")
    for chart_id, (expected_sql, expected_config) in EXPECTED.items():
        view = canvas.get(chart_id)
        if not isinstance(view, dict):
            raise RuntimeError(f"CAS 哈希不匹配：缺少目标图表 {chart_id}")
        chart = view.get("chart") if isinstance(view.get("chart"), dict) else {}
        if str(chart.get("id")) != chart_id or chart.get("title") != EXPECTED_TITLES[chart_id]:
            raise RuntimeError(f"CAS 哈希不匹配：目标图表身份不一致 {chart_id}")
        actual_sql = sha256_text(str(view.get("sql") or ""))
        actual_config = config_fingerprint(view)
        if actual_sql != expected_sql or actual_config != expected_config:
            raise RuntimeError(f"CAS 哈希不匹配：目标图表 {chart_id} 已发生变化")


def migrate_canvas(canvas: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    migrated = copy.deepcopy(canvas)
    target_ids = set(EXPECTED)
    missing = target_ids.difference(migrated)
    if missing:
        raise RuntimeError(f"缺少目标图表：{', '.join(sorted(missing))}")
    unchanged_hashes = {
        chart_id: stable_json_hash(view)
        for chart_id, view in canvas.items()
        if chart_id not in target_ids
    }
    for chart_id in EXPECTED:
        view = migrated.get(chart_id)
        if not isinstance(view, dict):
            raise RuntimeError(f"目标图表配置无效：{chart_id}")
        migrated[chart_id] = migrate_view(view)
    return migrated, unchanged_hashes


def verify_migrated_canvas(
    canvas: dict[str, Any],
    *,
    unchanged_hashes: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for chart_id in EXPECTED:
        view = canvas.get(chart_id)
        if not isinstance(view, dict):
            raise RuntimeError(f"读回缺少目标图表：{chart_id}")
        sql = str(view.get("sql") or "")
        start_count = sql.count(START_TOKEN)
        end_count = sql.count(END_TOKEN)
        if start_count != 4 or end_count != 4 or "CURDATE()" in sql:
            raise RuntimeError(f"读回日期参数校验失败：{chart_id}")
        source_config = view.get("sourceConfig")
        builder = (
            source_config.get("sql", {}).get("builder", {})
            if isinstance(source_config, dict)
            else {}
        )
        pivot = view.get("pivot") if isinstance(view.get("pivot"), dict) else {}
        builder_expression = builder.get("timeExpression")
        pivot_expression = pivot.get("date_expression")
        if builder_expression != pivot_expression:
            raise RuntimeError(f"日期表达式配置不一致：{chart_id}")
        if (
            builder.get("dateExpressionPickerEnabled") is not True
            or builder.get("timeField") != "dt"
            or builder.get("timeRange") != "expression"
            or builder_expression != DEFAULT_EXPRESSION
            or pivot.get("enabled") is not False
            or pivot.get("time_field") != "dt"
            or pivot.get("range_enabled") is not True
            or pivot.get("date_parameter_type") != "yyyymmdd_number"
        ):
            raise RuntimeError(f"读回日期表达式配置无效：{chart_id}")
        result[chart_id] = {
            "sql_sha256": sha256_text(sql),
            "start_tokens": start_count,
            "end_tokens": end_count,
            "expression": copy.deepcopy(builder_expression),
        }
    for chart_id, expected_hash in (unchanged_hashes or {}).items():
        if chart_id not in canvas or stable_json_hash(canvas[chart_id]) != expected_hash:
            raise RuntimeError(f"非目标图表发生变化：{chart_id}")
    return result


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _backup(row: dict[str, Any], *, new_canvas: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"roi_date_expression_{time.time_ns()}.json"
    payload = {
        "dashboard_id": DASHBOARD_ID,
        "tenant_id": TENANT_ID,
        "create_by": CREATE_BY,
        "old_canvas_sha256": sha256_text(row["canvas_view_info"]),
        "new_canvas_sha256": sha256_text(new_canvas),
        "row": {key: _json_value(value) for key, value in row.items()},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path.resolve()


def _select_dashboard(cur: Any, *, lock: bool) -> dict[str, Any]:
    cur.execute(
        f"""
        SELECT id, tenant_id, name, create_by, update_time, canvas_view_info
        FROM public.core_dashboard
        WHERE id = %s AND tenant_id = %s AND create_by = %s
          AND COALESCE(delete_flag, 0) = 0
        {'FOR UPDATE' if lock else ''}
        """,
        (DASHBOARD_ID, TENANT_ID, CREATE_BY),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("未找到目标看板或所有权边界不匹配")
    if not isinstance(row.get("canvas_view_info"), str):
        raise RuntimeError("canvas_view_info 类型不是文本")
    return row


def _readback(
    *, unchanged_hashes: dict[str, str] | None = None
) -> tuple[str, dict[str, dict[str, Any]]]:
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            row = _select_dashboard(cur, lock=False)
            raw = row["canvas_view_info"]
            verification = verify_migrated_canvas(
                _canvas(raw), unchanged_hashes=unchanged_hashes
            )
        conn.rollback()
    return raw, verification


def migrate_dashboard(*, apply: bool) -> dict[str, Any]:
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            row = _select_dashboard(cur, lock=True)
            old_raw = row["canvas_view_info"]
            original = _canvas(old_raw)
            validate_baseline(old_raw, original)
            migrated, unchanged_hashes = migrate_canvas(original)
            new_raw = json.dumps(migrated, ensure_ascii=False, separators=(",", ":"))
            planned_verification = verify_migrated_canvas(
                migrated, unchanged_hashes=unchanged_hashes
            )
            backup_path: Path | None = None
            if apply:
                backup_path = _backup(row, new_canvas=new_raw)
                cur.execute(
                    """
                    UPDATE public.core_dashboard
                    SET canvas_view_info = %s, update_time = %s
                    WHERE id = %s AND tenant_id = %s AND create_by = %s
                      AND canvas_view_info = %s
                      AND COALESCE(delete_flag, 0) = 0
                    """,
                    (
                        new_raw,
                        int(time.time()),
                        DASHBOARD_ID,
                        TENANT_ID,
                        CREATE_BY,
                        old_raw,
                    ),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"CAS 更新数量异常：{cur.rowcount}")
                conn.commit()
            else:
                conn.rollback()

    if apply:
        try:
            readback_raw, verification = _readback(unchanged_hashes=unchanged_hashes)
        except Exception as exc:
            rollback = (
                f'python tools/migrate_roi_dashboard_date_expression.py --restore "{backup_path}"'
            )
            raise RuntimeError(
                f"写入已提交但读回验证失败；备份：{backup_path}；回滚命令：{rollback}"
            ) from exc
    else:
        readback_raw, verification = new_raw, planned_verification
    backup_text = str(backup_path) if backup_path else None
    return {
        "applied": apply,
        "backup": backup_text,
        "old_canvas_sha256": sha256_text(old_raw),
        "new_canvas_sha256": sha256_text(readback_raw),
        "charts": verification,
        "rollback_command": (
            f'python tools/migrate_roi_dashboard_date_expression.py --restore "{backup_text}"'
            if backup_text
            else None
        ),
    }


def verify_dashboard() -> dict[str, Any]:
    raw, verification = _readback()
    return {
        "applied": False,
        "verified": True,
        "canvas_sha256": sha256_text(raw),
        "charts": verification,
    }


def restore_dashboard(backup_path: Path) -> dict[str, Any]:
    payload = json.loads(backup_path.read_text(encoding="utf-8"))
    if (
        payload.get("dashboard_id") != DASHBOARD_ID
        or payload.get("tenant_id") != TENANT_ID
        or str(payload.get("create_by")) != CREATE_BY
    ):
        raise RuntimeError("备份所有权边界不匹配")
    old_raw = payload.get("row", {}).get("canvas_view_info")
    if (
        payload.get("old_canvas_sha256") != EXPECTED_CANVAS_SHA256
        or not isinstance(old_raw, str)
        or sha256_text(old_raw) != payload.get("old_canvas_sha256")
    ):
        raise RuntimeError("备份内容哈希不匹配")
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            row = _select_dashboard(cur, lock=True)
            current_raw = row["canvas_view_info"]
            if sha256_text(current_raw) != payload.get("new_canvas_sha256"):
                raise RuntimeError("回滚 CAS 哈希不匹配：当前看板已发生变化")
            cur.execute(
                """
                UPDATE public.core_dashboard
                SET canvas_view_info = %s, update_time = %s
                WHERE id = %s AND tenant_id = %s AND create_by = %s
                  AND canvas_view_info = %s
                  AND COALESCE(delete_flag, 0) = 0
                """,
                (
                    old_raw,
                    int(time.time()),
                    DASHBOARD_ID,
                    TENANT_ID,
                    CREATE_BY,
                    current_raw,
                ),
            )
            if cur.rowcount != 1:
                raise RuntimeError(f"回滚 CAS 更新数量异常：{cur.rowcount}")
            conn.commit()
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            restored = _select_dashboard(cur, lock=False)["canvas_view_info"]
        conn.rollback()
    if sha256_text(restored) != payload["old_canvas_sha256"]:
        raise RuntimeError("回滚读回哈希不匹配")
    return {
        "restored": True,
        "backup": str(backup_path.resolve()),
        "canvas_sha256": sha256_text(restored),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="备份并迁移目标看板")
    mode.add_argument("--verify", action="store_true", help="只读验证已迁移配置")
    mode.add_argument("--restore", type=Path, help="使用指定备份按 CAS 边界回滚")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.restore:
        result = restore_dashboard(args.restore)
    elif args.verify:
        result = verify_dashboard()
    else:
        result = migrate_dashboard(apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
