"""121_remove_hidden_chart_display_names

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-06-23 00:00:00.000000

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
    return op.get_bind()


def _inspector():
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _sanitize_axis_binding(value: Any) -> Any:
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
    if any(key in value for key in ("axis", "xAxis", "yAxis", "series", "multiQuotaName")):
        return True
    return "columns" in value and str(value.get("type") or "").lower() in CHART_TYPES


def _sanitize_chart_display_names(value: Any) -> Any:
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
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _clean_text_json_column(table_name: str, id_column: str, json_column: str) -> None:
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
    _clean_text_json_column("core_dashboard", "id", "canvas_view_info")
    _clean_text_json_column("core_dashboard_share", "id", "canvas_view_info")
    _clean_text_json_column("chat_record", "id", "chart")
    _clean_jsonb_column("analysis_assistant_conversation", "id", "messages")


def downgrade() -> None:
    return None
