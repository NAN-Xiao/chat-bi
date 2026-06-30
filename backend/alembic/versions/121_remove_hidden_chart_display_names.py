"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
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
    是什么：_bind 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移相关的信息改成最新状态，并保存这些变化。
    """
    return op.get_bind()


def _inspector():
    """
    是什么：_inspector 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _sanitize_axis_binding(value: Any) -> Any:
    """
    是什么：_sanitize_axis_binding 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
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
    是什么：_sanitize_chart_object 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
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
    是什么：_looks_like_chart_object 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if any(key in value for key in ("axis", "xAxis", "yAxis", "series", "multiQuotaName")):
        return True
    return "columns" in value and str(value.get("type") or "").lower() in CHART_TYPES


def _sanitize_chart_display_names(value: Any) -> Any:
    """
    是什么：_sanitize_chart_display_names 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
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
    是什么：_load_json_text 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移需要的数据找出来，整理成后面好用的样子。
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
    是什么：_dump_json_text 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _clean_text_json_column(table_name: str, id_column: str, json_column: str) -> None:
    """
    是什么：_clean_text_json_column 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移不再需要的数据、缓存或临时内容清理掉。
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
    是什么：_clean_jsonb_column 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移不再需要的数据、缓存或临时内容清理掉。
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
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    _clean_text_json_column("core_dashboard", "id", "canvas_view_info")
    _clean_text_json_column("core_dashboard_share", "id", "canvas_view_info")
    _clean_text_json_column("chat_record", "id", "chart")
    _clean_jsonb_column("analysis_assistant_conversation", "id", "messages")


def downgrade() -> None:
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    return None
