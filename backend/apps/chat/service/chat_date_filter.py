"""聊天图表的看板日期参数校验与渲染。"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from apps.dashboard.crud.dashboard_date_filter import (
    has_dashboard_date_filter_parameters,
    prepare_dashboard_date_filter,
    validate_dashboard_date_parameter_sql,
)


_DATABASE_CURRENT_DATE_PATTERN = re.compile(
    r"\b(?:CURDATE|CURRENT_DATE|NOW|CURRENT_TIMESTAMP|LOCALTIME|LOCALTIMESTAMP|GETDATE|GETUTCDATE)\b",
    re.IGNORECASE,
)


class ChatDateFilterConfigurationError(ValueError):
    """聊天 SQL 的日期模板配置不完整或不一致。"""


def normalize_chat_date_filter(payload: Any, sql: str, chart_type: str) -> dict[str, Any] | None:
    """校验聊天 SQL 响应中的日期配置，并转换为看板 pivot。"""
    has_tokens = has_dashboard_date_filter_parameters(sql)
    if payload in (None, {}):
        if has_tokens:
            raise ChatDateFilterConfigurationError("missing_date_filter")
        return None
    if str(chart_type or "").strip().lower() == "metric":
        raise ChatDateFilterConfigurationError("metric_chart")
    if not isinstance(payload, dict):
        raise ChatDateFilterConfigurationError("invalid_date_filter")
    if _DATABASE_CURRENT_DATE_PATTERN.search(sql):
        raise ChatDateFilterConfigurationError("database_current_date")

    time_field = str(payload.get("time_field") or "").strip()
    if not time_field:
        raise ChatDateFilterConfigurationError("missing_time_field")
    parameter_type = str(payload.get("date_parameter_type") or "").strip()
    parameter_error = validate_dashboard_date_parameter_sql(sql, parameter_type)
    if parameter_error:
        raise ChatDateFilterConfigurationError(parameter_error)
    expression = payload.get("date_expression")
    if not isinstance(expression, dict):
        raise ChatDateFilterConfigurationError("missing_date_expression")

    return {
        "enabled": False,
        "time_field": time_field,
        "date_parameter_type": parameter_type,
        "date_expression": expression,
    }


def render_chat_date_filter_sql(
    sql: str,
    datasource_type: str | None,
    pivot: dict[str, Any] | None,
    *,
    today: date | None = None,
) -> str:
    """在聊天执行前将受控日期 token 渲染为数据源可执行的字面量。"""
    if pivot is None:
        return sql
    prepared = prepare_dashboard_date_filter(
        sql,
        ds_type=datasource_type,
        pivot=pivot,
        today=today,
    )
    if prepared.capability.get("status") != "available":
        reason = str(prepared.capability.get("reason") or "date_filter_unavailable")
        raise ChatDateFilterConfigurationError(reason)
    return prepared.sql
