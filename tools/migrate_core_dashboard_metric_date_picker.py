# -*- coding: utf-8 -*-
"""迁移三个指定核心看板的指标卡日期表达式控件。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row

from core_system_db import core_system_db_config


START_TOKEN = "{{dashboard_start_yyyymmdd}}"
END_TOKEN = "{{dashboard_end_yyyymmdd}}"
YESTERDAY_EXPRESSION = {
    "version": 1,
    "mode": "preset",
    "preset": "yesterday",
}
ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / ".codex-runtime" / "core-dashboard-metric-date-picker-backups"
BACKUP_SCHEMA = "core-dashboard-metric-date-picker/v1"

LEGACY_DATE_LABEL = "DATE_FORMAT(CURDATE(), '%Y-%m-%d')"
PARAMETER_DATE_LABEL = (
    "DATE_FORMAT(STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), "
    "'%Y%m%d'), '%Y-%m-%d')"
)
LEGACY_NUMBER_DAY = "CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)"


@dataclass(frozen=True)
class ChartTarget:
    chart_id: str
    title: str
    time_field: str
    parameter_type: str
    sql_sha256: str | None = None
    transitional_sql_sha256: str | None = None


@dataclass(frozen=True)
class DashboardTarget:
    workspace: str
    tenant_id: int
    dashboard_id: str
    dashboard_name: str
    datasource_id: int
    create_by: str
    charts: tuple[ChartTarget, ...]


def _charts(
    *items: tuple[str, str, str] | tuple[str, str, str, str],
    time_field: str = "dt",
) -> tuple[ChartTarget, ...]:
    return tuple(
        ChartTarget(
            chart_id,
            title,
            time_field,
            "yyyymmdd_number",
            sql_hash,
            transitional_hash if len(item) == 4 else None,
        )
        for item in items
        for chart_id, title, sql_hash, *transitional in (item,)
        for transitional_hash in (transitional[0] if transitional else None,)
    )


DASHBOARD_TARGETS = (
    DashboardTarget(
        "flam",
        7477202383789887488,
        "6d50bd7dfc9f46ba961d636814c3294d",
        "核心看板",
        3,
        "7471612174524223488",
        _charts(
            ("c23c019171804f608e92961dc06ae8b2", "活跃用户", "6c50e05508491782370409626942152da7fee2f4460925a7435e356a014f82a0"),
            ("d84e234a7f3b4e728a8b02d61911d88f", "新增用户", "977654b0e711b1b2f804cf6d66cfafac64716d9f029fc468c94b2d7fea5c09f4"),
            ("4d250a8575cc4bcd84f7b9514abbf455", "充值人数", "200e05cedac05f3c9aa80816163a6ebbb45595ddb137ac67a1f2a6eface2b8c8"),
            ("ba0dc1580f0d43c29c0d6cdf26a6239c", "充值总额", "2b42645c89d307708d1b2576b80dea4f9d1ce6bf041e310bc170ff3ca833f417"),
        ),
    ),
    DashboardTarget(
        "修仙",
        7482727237662281728,
        "afe201c9762c448aa0495f3508c01793",
        "核心看板",
        6,
        "7478377721614045184",
        _charts(
            ("c3d6ca851f8150ba94d73a83ca18b438", "活跃用户", "ab61c21299dfb10cf1ec100b9c8f16cf1aa5a1c65b38df0bd7c59843387d885d", "651fd42fd722d881f6f7491c9bf70c9f8b8a2027642257d976043bbeb2de5a4f"),
            ("2ca07023c33d514eaa07977425ee7f53", "新增用户", "fe4535ac8577e87cf09fb1604fd1b2c92e299eaf7af7398de7b2904b356396cf", "af0188567f53b871e4692030be912199113a178f57d529ec6505c87217810434"),
            ("f212cbcd03a15590a39519e874a1a6f4", "充值人数", "ab47b98da88108a56d9b52d02b329ed9189cdd0d45c6556540d25a8442e2d03c", "ba5fb55bb4f75349a416ceab371ae12ec6e28d1e352a280618f719df46da811b"),
            ("5bb72c937f565b7295b3bf4d1b746496", "充值总额", "ef571613d9aa32ddff4e59f782494e45ceee19bad3c4c4d60f1c4b537e120cbb", "6ccb51a38f4e04f997890043608bfd7ba69aa8ea5a14766416f841d6a85c0d91"),
            time_field="event.dt",
        ),
    ),
    DashboardTarget(
        "模板_修仙",
        7489861204282707968,
        "1f82f42788bc414d8139b20742aea882",
        "核心看板",
        6,
        "1",
        _charts(
            ("a89807329cbb4f12a9a07a2758c42211", "活跃用户", "ab61c21299dfb10cf1ec100b9c8f16cf1aa5a1c65b38df0bd7c59843387d885d", "651fd42fd722d881f6f7491c9bf70c9f8b8a2027642257d976043bbeb2de5a4f"),
            ("a10db6379022474db36ae7e30765dbd5", "新增用户", "fe4535ac8577e87cf09fb1604fd1b2c92e299eaf7af7398de7b2904b356396cf", "af0188567f53b871e4692030be912199113a178f57d529ec6505c87217810434"),
            ("89ecd7e53fad4c31951e8ad4ebb716d4", "充值人数", "ab47b98da88108a56d9b52d02b329ed9189cdd0d45c6556540d25a8442e2d03c", "ba5fb55bb4f75349a416ceab371ae12ec6e28d1e352a280618f719df46da811b"),
            ("7aca5918b69242f28a46c691720334c9", "充值总额", "ef571613d9aa32ddff4e59f782494e45ceee19bad3c4c4d60f1c4b537e120cbb", "6ccb51a38f4e04f997890043608bfd7ba69aa8ea5a14766416f841d6a85c0d91"),
            time_field="event.dt",
        ),
    ),
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_json_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(raw)


def parameterize_metric_sql(sql: str, parameter_type: str) -> str:
    """Convert the two known metric SQL date shapes to dashboard parameters."""
    if parameter_type != "yyyymmdd_number":
        raise ValueError(f"不支持的日期参数类型：{parameter_type}")
    historical_sql, realtime_count = re.subn(
        r"\bFROM\s+event_realtime\b",
        "FROM event",
        sql,
        count=1,
        flags=re.IGNORECASE,
    )
    if "event_realtime" in historical_sql.lower() or realtime_count > 1:
        raise ValueError("目标指标 SQL 包含未知的实时表模式")
    sql = historical_sql
    if START_TOKEN in sql or END_TOKEN in sql:
        if END_TOKEN not in sql:
            raise ValueError("日期模式无效：缺少结束日期参数")
        return sql
    if sql.count(LEGACY_DATE_LABEL) != 1 or sql.count(LEGACY_NUMBER_DAY) != 1:
        raise ValueError("未知的指标卡日期模式")
    return sql.replace(LEGACY_DATE_LABEL, PARAMETER_DATE_LABEL).replace(
        f"dt = {LEGACY_NUMBER_DAY}",
        f"dt BETWEEN {START_TOKEN} AND {END_TOKEN}",
    )


def migrate_metric_view(
    view: dict[str, Any],
    *,
    time_field: str,
    parameter_type: str,
) -> dict[str, Any]:
    result = copy.deepcopy(view)
    chart = result.get("chart")
    if not isinstance(chart, dict) or chart.get("type") != "metric":
        raise ValueError("仅允许迁移 metric 指标卡")
    result["sql"] = parameterize_metric_sql(
        str(result.get("sql") or ""), parameter_type
    )

    source_config = result.setdefault("sourceConfig", {})
    if not isinstance(source_config, dict):
        raise ValueError("sourceConfig 配置无效")
    sql_config = source_config.setdefault("sql", {})
    if not isinstance(sql_config, dict):
        raise ValueError("sourceConfig.sql 配置无效")
    sql_config["sql"] = result["sql"]
    builder = sql_config.setdefault("builder", {})
    if not isinstance(builder, dict):
        raise ValueError("sourceConfig.sql.builder 配置无效")
    builder.update(
        {
            "metricDateExpressionEnabled": True,
            "dateExpressionPickerEnabled": True,
            "timeField": time_field,
            "timeRange": "expression",
            "timeExpression": copy.deepcopy(YESTERDAY_EXPRESSION),
        }
    )

    pivot = result.setdefault("pivot", {})
    if not isinstance(pivot, dict):
        raise ValueError("pivot 配置无效")
    pivot.update(
        {
            "enabled": False,
            "time_field": time_field,
            "range_enabled": True,
            "date_parameter_type": parameter_type,
            "date_expression": copy.deepcopy(YESTERDAY_EXPRESSION),
        }
    )
    result["configVersion"] = 2
    result["dateFilter"] = {
        "enabled": True,
        "parameterType": parameter_type,
        "expression": copy.deepcopy(YESTERDAY_EXPRESSION),
    }
    return result


def migrate_target_views(
    canvas: dict[str, Any],
    *,
    targets: Mapping[str, ChartTarget],
) -> dict[str, Any]:
    result = copy.deepcopy(canvas)
    missing = set(targets).difference(result)
    if missing:
        raise RuntimeError(f"缺少目标图表：{', '.join(sorted(missing))}")
    for chart_id, target in targets.items():
        view = result.get(chart_id)
        if not isinstance(view, dict):
            raise RuntimeError(f"目标图表配置无效：{chart_id}")
        chart = view.get("chart")
        if (
            not isinstance(chart, dict)
            or str(chart.get("id", chart_id)) != chart_id
            or chart.get("title") != target.title
            or chart.get("type") != "metric"
        ):
            raise RuntimeError(f"目标图表身份不一致：{chart_id}")
        actual_sql_hash = sha256_text(str(view.get("sql") or ""))
        accepted_hashes = {target.sql_sha256, target.transitional_sql_sha256}
        accepted_hashes.discard(None)
        if accepted_hashes and actual_sql_hash not in accepted_hashes:
            try:
                verify_migrated_view(view, target=target)
            except RuntimeError as exc:
                raise RuntimeError(f"目标图表 SQL 哈希不一致：{chart_id}") from exc
        result[chart_id] = migrate_metric_view(
            view,
            time_field=target.time_field,
            parameter_type=target.parameter_type,
        )
    return result


def non_target_hashes(
    canvas: Mapping[str, Any], *, target_ids: set[str]
) -> dict[str, str]:
    return {
        chart_id: stable_json_hash(view)
        for chart_id, view in canvas.items()
        if chart_id not in target_ids
    }


def verify_migrated_view(view: Mapping[str, Any], *, target: ChartTarget) -> None:
    sql = str(view.get("sql") or "")
    if re.search(r"\bevent_realtime\b", sql, re.IGNORECASE):
        raise RuntimeError(f"目标图表仍使用实时表：{target.chart_id}")
    if END_TOKEN not in sql or "CURDATE()" in sql:
        raise RuntimeError(f"日期参数校验失败：{target.chart_id}")
    chart = view.get("chart")
    source_config = view.get("sourceConfig")
    sql_config = source_config.get("sql", {}) if isinstance(source_config, dict) else {}
    nested_sql = sql_config.get("sql") if isinstance(sql_config, dict) else None
    if nested_sql != sql:
        raise RuntimeError(f"目标图表嵌套 SQL 不一致：{target.chart_id}")
    builder = sql_config.get("builder", {}) if isinstance(sql_config, dict) else {}
    pivot = view.get("pivot") if isinstance(view.get("pivot"), dict) else {}
    date_filter = (
        view.get("dateFilter") if isinstance(view.get("dateFilter"), dict) else {}
    )
    if (
        not isinstance(chart, dict)
        or chart.get("type") != "metric"
        or chart.get("title") != target.title
        or builder.get("metricDateExpressionEnabled") is not True
        or builder.get("dateExpressionPickerEnabled") is not True
        or builder.get("timeField") != target.time_field
        or builder.get("timeRange") != "expression"
        or builder.get("timeExpression") != YESTERDAY_EXPRESSION
        or pivot.get("time_field") != target.time_field
        or pivot.get("range_enabled") is not True
        or pivot.get("date_parameter_type") != target.parameter_type
        or pivot.get("date_expression") != YESTERDAY_EXPRESSION
        or view.get("configVersion") != 2
        or date_filter.get("enabled") is not True
        or date_filter.get("parameterType") != target.parameter_type
        or date_filter.get("expression") != YESTERDAY_EXPRESSION
    ):
        raise RuntimeError(f"日期表达式配置无效：{target.chart_id}")


def verify_migrated_canvas(
    canvas: Mapping[str, Any],
    *,
    targets: Mapping[str, ChartTarget],
    unchanged_hashes: Mapping[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for chart_id, target in targets.items():
        view = canvas.get(chart_id)
        if not isinstance(view, dict):
            raise RuntimeError(f"读回缺少目标图表：{chart_id}")
        verify_migrated_view(view, target=target)
        sql = str(view.get("sql") or "")
        result[chart_id] = {
            "title": target.title,
            "sql_sha256": sha256_text(sql),
            "start_tokens": sql.count(START_TOKEN),
            "end_tokens": sql.count(END_TOKEN),
            "expression": copy.deepcopy(YESTERDAY_EXPRESSION),
        }
    for chart_id, expected_hash in (unchanged_hashes or {}).items():
        if chart_id not in canvas or stable_json_hash(canvas[chart_id]) != expected_hash:
            raise RuntimeError(f"非目标图表发生变化：{chart_id}")
    return result


def _target_map(target: DashboardTarget) -> dict[str, ChartTarget]:
    return {chart.chart_id: chart for chart in target.charts}


def cas_update_dashboard(
    cursor: Any,
    *,
    target: DashboardTarget,
    old_raw: str,
    new_raw: str,
) -> None:
    cursor.execute(
        """
        UPDATE public.core_dashboard
        SET canvas_view_info = %s, update_time = %s, update_by = %s
        WHERE id = %s AND tenant_id = %s AND datasource = %s AND create_by = %s
          AND name = %s AND canvas_view_info = %s AND COALESCE(delete_flag, 0) = 0
        """,
        (
            new_raw,
            int(time.time()),
            "codex",
            target.dashboard_id,
            target.tenant_id,
            target.datasource_id,
            target.create_by,
            target.dashboard_name,
            old_raw,
        ),
    )
    if cursor.rowcount != 1:
        raise RuntimeError(
            f"CAS 更新数量异常：{target.workspace}/{target.dashboard_id}={cursor.rowcount}"
        )


def verify_transaction_readback(
    cursor: Any,
    *,
    target: DashboardTarget,
    expected_raw: str,
    unchanged_hashes: Mapping[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    row = _select_dashboard(cursor, target=target, lock=False)
    actual_raw = row["canvas_view_info"]
    if actual_raw != expected_raw:
        raise RuntimeError(f"事务内读回 canvas 不一致：{target.workspace}")
    return verify_migrated_canvas(
        _canvas(actual_raw),
        targets=_target_map(target),
        unchanged_hashes=unchanged_hashes,
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def write_backup(
    rows: list[dict[str, Any]],
    *,
    new_raw_by_id: Mapping[str, str],
    directory: Path = BACKUP_DIR,
) -> Path:
    by_id = {str(row["id"]): row for row in rows}
    expected_ids = {target.dashboard_id for target in DASHBOARD_TARGETS}
    if set(by_id) != expected_ids or set(new_raw_by_id) != expected_ids:
        raise RuntimeError("备份目标清单与三个核心看板不一致")
    dashboards = []
    for target in DASHBOARD_TARGETS:
        row = by_id[target.dashboard_id]
        old_raw = row.get("canvas_view_info")
        new_raw = new_raw_by_id[target.dashboard_id]
        if not isinstance(old_raw, str) or not isinstance(new_raw, str):
            raise RuntimeError("备份 canvas_view_info 类型无效")
        dashboards.append(
            {
                "workspace": target.workspace,
                "dashboard_id": target.dashboard_id,
                "tenant_id": target.tenant_id,
                "datasource_id": target.datasource_id,
                "create_by": target.create_by,
                "old_canvas_sha256": sha256_text(old_raw),
                "new_canvas_sha256": sha256_text(new_raw),
                "row": {key: _json_value(value) for key, value in row.items()},
            }
        )
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"core_dashboard_metric_date_picker_{time.time_ns()}.json"
    path.write_text(
        json.dumps(
            {
                "schema": BACKUP_SCHEMA,
                "created_at": int(time.time()),
                "dashboards": dashboards,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path.resolve()


def load_restore_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("备份文件无法读取") from exc
    if not isinstance(payload, dict) or payload.get("schema") != BACKUP_SCHEMA:
        raise RuntimeError("备份 schema 不匹配")
    items = payload.get("dashboards")
    if not isinstance(items, list):
        raise RuntimeError("备份目标列表无效")
    targets = {target.dashboard_id: target for target in DASHBOARD_TARGETS}
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise RuntimeError("备份目标配置无效")
        dashboard_id = str(item.get("dashboard_id") or "")
        target = targets.get(dashboard_id)
        row = item.get("row")
        old_raw = row.get("canvas_view_info") if isinstance(row, dict) else None
        if not isinstance(old_raw, str) or sha256_text(old_raw) != item.get(
            "old_canvas_sha256"
        ):
            raise RuntimeError(f"备份旧 canvas 哈希不匹配：{dashboard_id}")
        if (
            target is None
            or item.get("workspace") != target.workspace
            or item.get("tenant_id") != target.tenant_id
            or item.get("datasource_id") != target.datasource_id
            or str(item.get("create_by")) != target.create_by
        ):
            raise RuntimeError(f"备份所有权边界不匹配：{dashboard_id}")
        if dashboard_id in seen:
            raise RuntimeError(f"备份包含重复看板：{dashboard_id}")
        seen.add(dashboard_id)
    if seen != set(targets):
        raise RuntimeError("备份必须完整包含三个目标看板")
    return payload


def _canvas(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("canvas_view_info 不是合法 JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("canvas_view_info 不是对象")
    return value


def _select_dashboard(
    cursor: Any, *, target: DashboardTarget, lock: bool
) -> dict[str, Any]:
    cursor.execute(
        f"""
        SELECT id, tenant_id, name, datasource, create_by, update_time,
               update_by, canvas_view_info
        FROM public.core_dashboard
        WHERE id = %s AND tenant_id = %s AND datasource = %s AND create_by = %s
          AND name = %s AND type = 'dashboard' AND COALESCE(delete_flag, 0) = 0
        {'FOR UPDATE' if lock else ''}
        """,
        (
            target.dashboard_id,
            target.tenant_id,
            target.datasource_id,
            target.create_by,
            target.dashboard_name,
        ),
    )
    row = cursor.fetchone()
    if not row:
        raise RuntimeError(
            f"未找到目标看板或身份边界变化：{target.workspace}/{target.dashboard_id}"
        )
    if not isinstance(row.get("canvas_view_info"), str):
        raise RuntimeError(f"canvas_view_info 类型无效：{target.dashboard_id}")
    return row


def _plan_row(
    row: dict[str, Any], target: DashboardTarget
) -> tuple[str, dict[str, str], dict[str, dict[str, Any]]]:
    old_raw = row["canvas_view_info"]
    original = _canvas(old_raw)
    target_map = _target_map(target)
    unchanged = non_target_hashes(original, target_ids=set(target_map))
    migrated = migrate_target_views(original, targets=target_map)
    verification = verify_migrated_canvas(
        migrated, targets=target_map, unchanged_hashes=unchanged
    )
    return (
        json.dumps(migrated, ensure_ascii=False, separators=(",", ":")),
        unchanged,
        verification,
    )


def _readback(
    unchanged_by_id: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    dashboards = []
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            for target in DASHBOARD_TARGETS:
                row = _select_dashboard(cursor, target=target, lock=False)
                raw = row["canvas_view_info"]
                charts = verify_migrated_canvas(
                    _canvas(raw),
                    targets=_target_map(target),
                    unchanged_hashes=(unchanged_by_id or {}).get(target.dashboard_id),
                )
                dashboards.append(
                    {
                        "workspace": target.workspace,
                        "dashboard_id": target.dashboard_id,
                        "canvas_sha256": sha256_text(raw),
                        "charts": charts,
                    }
                )
        conn.rollback()
    return {"dashboard_count": len(dashboards), "chart_count": 12, "dashboards": dashboards}


def migrate_dashboard(*, apply: bool) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    new_raw_by_id: dict[str, str] = {}
    unchanged_by_id: dict[str, dict[str, str]] = {}
    planned: list[dict[str, Any]] = []
    backup: Path | None = None
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        try:
            with conn.cursor() as cursor:
                for target in DASHBOARD_TARGETS:
                    row = _select_dashboard(cursor, target=target, lock=apply)
                    new_raw, unchanged, charts = _plan_row(row, target)
                    rows.append(row)
                    new_raw_by_id[target.dashboard_id] = new_raw
                    unchanged_by_id[target.dashboard_id] = unchanged
                    planned.append(
                        {
                            "workspace": target.workspace,
                            "dashboard_id": target.dashboard_id,
                            "changed": new_raw != row["canvas_view_info"],
                            "charts": charts,
                        }
                    )
                changed = [
                    (target, row)
                    for target, row in zip(DASHBOARD_TARGETS, rows)
                    if new_raw_by_id[target.dashboard_id] != row["canvas_view_info"]
                ]
                if apply and changed:
                    backup = write_backup(rows, new_raw_by_id=new_raw_by_id)
                    for target, row in changed:
                        cas_update_dashboard(
                            cursor,
                            target=target,
                            old_raw=row["canvas_view_info"],
                            new_raw=new_raw_by_id[target.dashboard_id],
                        )
                    for target in DASHBOARD_TARGETS:
                        verify_transaction_readback(
                            cursor,
                            target=target,
                            expected_raw=new_raw_by_id[target.dashboard_id],
                            unchanged_hashes=unchanged_by_id[target.dashboard_id],
                        )
                    conn.commit()
                else:
                    conn.rollback()
        except BaseException:
            conn.rollback()
            raise
    if apply:
        readback = _readback(unchanged_by_id)
        rollback_command = (
            f'backend\\.venv\\Scripts\\python.exe '
            f'tools\\migrate_core_dashboard_metric_date_picker.py --restore "{backup}"'
            if backup
            else None
        )
        return {
            "applied": True,
            "changed_dashboard_count": sum(item["changed"] for item in planned),
            "backup": str(backup) if backup else None,
            "rollback_command": rollback_command,
            **readback,
        }
    return {
        "applied": False,
        "dashboard_count": len(planned),
        "chart_count": 12,
        "dashboards": planned,
    }


def verify_dashboard() -> dict[str, Any]:
    return {"applied": False, "verified": True, **_readback()}


def restore_dashboard(path: Path) -> dict[str, Any]:
    payload = load_restore_payload(path)
    by_id = {item["dashboard_id"]: item for item in payload["dashboards"]}
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        try:
            with conn.cursor() as cursor:
                for target in DASHBOARD_TARGETS:
                    item = by_id[target.dashboard_id]
                    row = _select_dashboard(cursor, target=target, lock=True)
                    current_raw = row["canvas_view_info"]
                    if sha256_text(current_raw) != item["new_canvas_sha256"]:
                        raise RuntimeError(
                            f"回滚 CAS 哈希不匹配：{target.workspace}/{target.dashboard_id}"
                        )
                    old_raw = item["row"]["canvas_view_info"]
                    cas_update_dashboard(
                        cursor,
                        target=target,
                        old_raw=current_raw,
                        new_raw=old_raw,
                    )
                conn.commit()
        except BaseException:
            conn.rollback()
            raise
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            for target in DASHBOARD_TARGETS:
                restored = _select_dashboard(cursor, target=target, lock=False)
                expected = by_id[target.dashboard_id]["old_canvas_sha256"]
                if sha256_text(restored["canvas_view_info"]) != expected:
                    raise RuntimeError(f"回滚读回哈希不匹配：{target.dashboard_id}")
        conn.rollback()
    return {"restored": True, "backup": str(path.resolve()), "dashboard_count": 3}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="备份并迁移三个核心看板")
    mode.add_argument("--verify", action="store_true", help="只读验证迁移结果")
    mode.add_argument("--restore", type=Path, help="使用指定备份按 CAS 回滚")
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
