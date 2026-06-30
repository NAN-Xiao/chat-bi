"""迁移脚本：121_remove_hidden_chart_display_names

迁移版本 ID： f1a2b3c4d5e6
上一版本： e0f1a2b3c4d5
创建时间： 2026-06-23 00:00:00.000000
"""
from __future__ import annotations

import json
from typing import Any

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f1a2b3c4d5e6"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None

CHART_TYPES = {
    "table",
    "metric",
    "column",
    "bar",
    "line",
    "pie",
    "funnel",
    "heatmap",
    "scatter",
    "sankey",
    "treemap",
}


def _bind():
    """
    是什么：_bind 是 backend/alembic/versions/121_remove_hidden_chart_display_names.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：更新数据库迁移相关状态、配置或持久化数据，并保持后续流程可继续使用。
    """
    return op.get_bind()


def _inspector():
    """
    是什么：_inspector 是 backend/alembic/versions/121_remove_hidden_chart_display_names.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _inspector 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/121_remove_hidden_chart_display_names.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/121_remove_hidden_chart_display_names.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _sanitize_axis_binding(value: Any) -> Any:
    """
    是什么：_sanitize_axis_binding 是 backend/alembic/versions/121_remove_hidden_chart_display_names.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _sanitize_axis_binding 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if isinstance(value, list):
        return [_sanitize_axis_binding(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: _sanitize_axis_binding(item)
        for key, item in value.items()
        if key != "name"
    }


def _sanitize_chart_object(chart: dict[str, Any]) -> dict[str, Any]:
    """
    是什么：_sanitize_chart_object 是 backend/alembic/versions/121_remove_hidden_chart_display_names.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _sanitize_chart_object 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    for key in ("columns", "xAxis", "yAxis", "series"):
        if key in chart:
            chart[key] = _sanitize_axis_binding(chart[key])
    axis = chart.get("axis")
    if isinstance(axis, dict):
        for key in ("x", "y", "series", "multi-quota"):
            if key in axis:
                axis[key] = _sanitize_axis_binding(axis[key])
    chart.pop("multiQuotaName", None)
    return chart


def _looks_like_chart_object(value: dict[str, Any]) -> bool:
    """
    是什么：_looks_like_chart_object 是 backend/alembic/versions/121_remove_hidden_chart_display_names.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _looks_like_chart_object 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if any(key in value for key in ("axis", "xAxis", "yAxis", "series", "multiQuotaName")):
        return True
    return "columns" in value and str(value.get("type") or "").lower() in CHART_TYPES


def _sanitize_chart_display_names(value: Any) -> Any:
    """
    是什么：_sanitize_chart_display_names 是 backend/alembic/versions/121_remove_hidden_chart_display_names.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _sanitize_chart_display_names 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if isinstance(value, list):
        return [_sanitize_chart_display_names(item) for item in value]
    if not isinstance(value, dict):
        return value

    result = {
        key: _sanitize_chart_display_names(item)
        for key, item in value.items()
    }
    if _looks_like_chart_object(result):
        _sanitize_chart_object(result)
    chart = result.get("chart")
    if isinstance(chart, dict):
        _sanitize_chart_object(chart)
    return result


def _load_json_text(value: Any) -> Any:
    """
    是什么：_load_json_text 是 backend/alembic/versions/121_remove_hidden_chart_display_names.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询数据库迁移相关数据，整理后返回给调用方。
    """
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _dump_json_text(value: Any) -> str:
    """
    是什么：_dump_json_text 是 backend/alembic/versions/121_remove_hidden_chart_display_names.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _dump_json_text 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _clean_text_json_column(table_name: str, id_column: str, json_column: str) -> None:
    """
    是什么：_clean_text_json_column 是 backend/alembic/versions/121_remove_hidden_chart_display_names.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：删除或清理数据库迁移相关数据、缓存或临时状态。
    """
    if not (_has_column(table_name, id_column) and _has_column(table_name, json_column)):
        return

    rows = _bind().execute(
        sa.text(f"SELECT {id_column}, {json_column} FROM {table_name} WHERE {json_column} IS NOT NULL")
    ).fetchall()
    update_stmt = sa.text(
        f"UPDATE {table_name} SET {json_column} = :value WHERE {id_column} = :row_id"
    )
    for row in rows:
        row_id = row[0]
        original = _load_json_text(row[1])
        if original is None:
            continue
        sanitized = _sanitize_chart_display_names(original)
        if sanitized == original:
            continue
        _bind().execute(update_stmt, {"value": _dump_json_text(sanitized), "row_id": row_id})


def _clean_jsonb_column(table_name: str, id_column: str, json_column: str) -> None:
    """
    是什么：_clean_jsonb_column 是 backend/alembic/versions/121_remove_hidden_chart_display_names.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：删除或清理数据库迁移相关数据、缓存或临时状态。
    """
    if not (_has_column(table_name, id_column) and _has_column(table_name, json_column)):
        return

    rows = _bind().execute(
        sa.text(f"SELECT {id_column}, {json_column} FROM {table_name} WHERE {json_column} IS NOT NULL")
    ).fetchall()
    update_stmt = sa.text(
        f"UPDATE {table_name} SET {json_column} = :value WHERE {id_column} = :row_id"
    ).bindparams(sa.bindparam("value", type_=postgresql.JSONB))
    for row in rows:
        row_id = row[0]
        original = _load_json_text(row[1])
        if original is None:
            continue
        sanitized = _sanitize_chart_display_names(original)
        if sanitized == original:
            continue
        _bind().execute(update_stmt, {"value": sanitized, "row_id": row_id})


def upgrade() -> None:
    """
    是什么：upgrade 是 backend/alembic/versions/121_remove_hidden_chart_display_names.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    _clean_text_json_column("core_dashboard", "id", "canvas_view_info")
    _clean_text_json_column("core_dashboard_share", "id", "canvas_view_info")
    _clean_text_json_column("chat_record", "id", "chart")
    _clean_jsonb_column("analysis_assistant_conversation", "id", "messages")


def downgrade() -> None:
    """
    是什么：downgrade 是 backend/alembic/versions/121_remove_hidden_chart_display_names.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return None
