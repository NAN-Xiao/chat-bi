# -*- coding: utf-8 -*-
"""为 flam 工作空间当前“我的看板”ROI 卡片启用日期表达式入口。

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

DASHBOARD_ID = "6773e46d6a8e49e18c8811ec1dbab37e"
TENANT_ID = 7477202383789887488
CREATE_BY = "7482253745313550336"
EXPECTED_CANVAS_SHA256 = "9f68b15fdb41019877fccd5b60ad6e3d8bd51984a0e89d25ccbb204456268dfc"
EXPECTED = {
    "2195197577098600448": (
        "e5384bd64a7b8b15b95927b073127c3dfa5e0d1609834320c60d778876d5ab2b",
        "ROI总览",
    ),
    "2195198304432857088": (
        "ce7b809f7cb804752248f9ac81b70518c104958720426d0091b4b15a4abf5c69",
        "ROI地区总览",
    ),
    "2195199004655132672": (
        "c2b8fc25ac1e8e3503cbd4099d6fe03aa0d862ed6dc7f7c3142da9e05bbc0529",
        "ROI广告地区总览",
    ),
    "2196532897761107968": (
        "e5384bd64a7b8b15b95927b073127c3dfa5e0d1609834320c60d778876d5ab2b",
        "安装投放趋势",
    ),
}
START_TOKEN = "{{dashboard_start_yyyymmdd}}"
END_TOKEN = "{{dashboard_end_yyyymmdd}}"
DEFAULT_EXPRESSION = {"version": 1, "mode": "preset", "preset": "past_30_days"}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canvas(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("canvas_view_info 不是合法 JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("canvas_view_info 不是对象")
    return value


def enable_view(view: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(view)
    source_config = result.get("sourceConfig")
    if not isinstance(source_config, dict):
        raise ValueError("sourceConfig 配置无效")
    sql_config = source_config.get("sql")
    if not isinstance(sql_config, dict):
        raise ValueError("sourceConfig.sql 配置无效")
    builder = sql_config.get("builder")
    if not isinstance(builder, dict):
        raise ValueError("sourceConfig.sql.builder 配置无效")
    builder.update(
        {
            "dateExpressionPickerEnabled": True,
            "timeRange": "expression",
            "timeExpression": copy.deepcopy(DEFAULT_EXPRESSION),
        }
    )
    pivot = result.get("pivot")
    if not isinstance(pivot, dict):
        raise ValueError("pivot 配置无效")
    pivot["date_expression"] = copy.deepcopy(DEFAULT_EXPRESSION)
    return result


def validate_baseline(raw_canvas: str, canvas: dict[str, Any]) -> None:
    if sha256_text(raw_canvas) != EXPECTED_CANVAS_SHA256:
        raise RuntimeError("CAS 哈希不匹配：看板 canvas 已发生变化")
    if set(canvas) != set(EXPECTED):
        raise RuntimeError("CAS 哈希不匹配：看板图表集合已发生变化")
    for chart_id, (expected_sql_hash, expected_title) in EXPECTED.items():
        view = canvas.get(chart_id)
        if not isinstance(view, dict):
            raise RuntimeError(f"CAS 哈希不匹配：缺少目标图表 {chart_id}")
        chart = view.get("chart") if isinstance(view.get("chart"), dict) else {}
        if str(chart.get("id")) != chart_id or chart.get("title") != expected_title:
            raise RuntimeError(f"CAS 哈希不匹配：目标图表身份不一致 {chart_id}")
        if sha256_text(str(view.get("sql") or "")) != expected_sql_hash:
            raise RuntimeError(f"CAS 哈希不匹配：目标图表 SQL 已变化 {chart_id}")


def migrate_canvas(canvas: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(canvas)
    for chart_id in EXPECTED:
        view = migrated.get(chart_id)
        if not isinstance(view, dict):
            raise RuntimeError(f"缺少目标图表：{chart_id}")
        migrated[chart_id] = enable_view(view)
    return migrated


def verify_migrated_canvas(canvas: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if set(canvas) != set(EXPECTED):
        raise RuntimeError("读回图表集合发生变化")
    result: dict[str, dict[str, Any]] = {}
    for chart_id, (expected_sql_hash, expected_title) in EXPECTED.items():
        view = canvas.get(chart_id)
        if not isinstance(view, dict):
            raise RuntimeError(f"读回缺少目标图表：{chart_id}")
        sql = str(view.get("sql") or "")
        if sha256_text(sql) != expected_sql_hash:
            raise RuntimeError(f"读回 SQL 已发生变化：{chart_id}")
        chart = view.get("chart") if isinstance(view.get("chart"), dict) else {}
        if str(chart.get("id")) != chart_id or chart.get("title") != expected_title:
            raise RuntimeError(f"读回图表身份不一致：{chart_id}")
        if sql.count(START_TOKEN) != 4 or sql.count(END_TOKEN) != 4:
            raise RuntimeError(f"读回日期参数数量不正确：{chart_id}")
        source_config = view.get("sourceConfig")
        builder = (
            source_config.get("sql", {}).get("builder", {})
            if isinstance(source_config, dict)
            else {}
        )
        pivot = view.get("pivot") if isinstance(view.get("pivot"), dict) else {}
        if (
            builder.get("dateExpressionPickerEnabled") is not True
            or builder.get("timeRange") != "expression"
            or builder.get("timeExpression") != DEFAULT_EXPRESSION
            or pivot.get("date_expression") != DEFAULT_EXPRESSION
        ):
            raise RuntimeError(f"读回日期表达式配置无效：{chart_id}")
        result[chart_id] = {
            "title": expected_title,
            "sql_sha256": expected_sql_hash,
            "start_tokens": sql.count(START_TOKEN),
            "end_tokens": sql.count(END_TOKEN),
            "expression": copy.deepcopy(DEFAULT_EXPRESSION),
        }
    return result


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


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


def _backup(row: dict[str, Any], *, new_canvas: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"flam_roi_card_date_expression_{time.time_ns()}.json"
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


def _readback() -> tuple[str, dict[str, dict[str, Any]]]:
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            raw = _select_dashboard(cur, lock=False)["canvas_view_info"]
            verification = verify_migrated_canvas(_canvas(raw))
        conn.rollback()
    return raw, verification


def migrate_dashboard(*, apply: bool) -> dict[str, Any]:
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            row = _select_dashboard(cur, lock=True)
            old_raw = row["canvas_view_info"]
            original = _canvas(old_raw)
            validate_baseline(old_raw, original)
            migrated = migrate_canvas(original)
            new_raw = json.dumps(migrated, ensure_ascii=False, separators=(",", ":"))
            planned = verify_migrated_canvas(migrated)
            backup_path: Path | None = None
            if apply:
                backup_path = _backup(row, new_canvas=new_raw)
                cur.execute(
                    """
                    UPDATE public.core_dashboard
                    SET canvas_view_info = %s, update_time = %s
                    WHERE id = %s AND tenant_id = %s AND create_by = %s
                      AND canvas_view_info = %s AND COALESCE(delete_flag, 0) = 0
                    """,
                    (new_raw, int(time.time()), DASHBOARD_ID, TENANT_ID, CREATE_BY, old_raw),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"CAS 更新数量异常：{cur.rowcount}")
                conn.commit()
            else:
                conn.rollback()
    if apply:
        try:
            readback_raw, verification = _readback()
        except Exception as exc:
            rollback = (
                f'python tools/enable_flam_roi_card_date_expression.py '
                f'--restore "{backup_path}"'
            )
            raise RuntimeError(
                f"写入已提交但读回验证失败；备份：{backup_path}；回滚命令：{rollback}"
            ) from exc
    else:
        readback_raw, verification = new_raw, planned
    backup_text = str(backup_path) if backup_path else None
    return {
        "applied": apply,
        "backup": backup_text,
        "old_canvas_sha256": sha256_text(old_raw),
        "new_canvas_sha256": sha256_text(readback_raw),
        "charts": verification,
        "rollback_command": (
            f'python tools/enable_flam_roi_card_date_expression.py --restore "{backup_text}"'
            if backup_text
            else None
        ),
    }


def verify_dashboard() -> dict[str, Any]:
    raw, verification = _readback()
    return {
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
            current_raw = _select_dashboard(cur, lock=True)["canvas_view_info"]
            if sha256_text(current_raw) != payload.get("new_canvas_sha256"):
                raise RuntimeError("回滚 CAS 哈希不匹配：当前看板已发生变化")
            cur.execute(
                """
                UPDATE public.core_dashboard
                SET canvas_view_info = %s, update_time = %s
                WHERE id = %s AND tenant_id = %s AND create_by = %s
                  AND canvas_view_info = %s AND COALESCE(delete_flag, 0) = 0
                """,
                (old_raw, int(time.time()), DASHBOARD_ID, TENANT_ID, CREATE_BY, current_raw),
            )
            if cur.rowcount != 1:
                raise RuntimeError(f"回滚 CAS 更新数量异常：{cur.rowcount}")
            conn.commit()
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            restored_raw = _select_dashboard(cur, lock=False)["canvas_view_info"]
        conn.rollback()
    if sha256_text(restored_raw) != payload["old_canvas_sha256"]:
        raise RuntimeError("回滚读回哈希不匹配")
    return {
        "restored": True,
        "backup": str(backup_path.resolve()),
        "canvas_sha256": sha256_text(restored_raw),
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
