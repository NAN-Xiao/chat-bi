"""聊天图表的看板日期参数校验与渲染。"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from apps.dashboard.crud.dashboard_date_filter import (
    dashboard_date_parameter_tokens,
    has_dashboard_date_filter_parameters,
    prepare_dashboard_date_filter,
    validate_dashboard_date_parameter_sql,
)


_DATABASE_CURRENT_DATE_PATTERN = re.compile(
    r"\b(?:CURDATE|CURRENT_DATE|NOW|CURRENT_TIMESTAMP|LOCALTIME|LOCALTIMESTAMP|GETDATE|GETUTCDATE)\b",
    re.IGNORECASE,
)

_SQL_IDENTIFIER_PATTERN = r'(?:`[^`]+`|"[^"]+"|\[[^\]]+\]|[A-Za-z_][A-Za-z0-9_$]*)'
_EXPLICIT_PAST_DAYS_PATTERN = re.compile(
    r"(?:最近|近|过去)\s*(?P<days>[1-9]\d{0,3})\s*(?:个\s*)?(?:完整\s*)?(?:自然\s*)?[天日]"
)
_EXPLICIT_CURRENT_DAY_PATTERN = re.compile(r"(?:今天|今日|当天)")
_DEFAULT_DATE_EXPRESSION = {"version": 1, "mode": "preset", "preset": "past_7_days"}


class ChatDateFilterConfigurationError(ValueError):
    """聊天 SQL 的日期模板配置不完整或不一致。"""


def _explicit_question_date_expression(question: str | None) -> dict[str, Any] | None:
    """将问题中明确的最近 N 天转换为截至昨天的动态看板日期表达式。"""
    question_text = str(question or "")
    matches = _EXPLICIT_PAST_DAYS_PATTERN.findall(question_text)
    distinct_days = {int(value) for value in matches}
    has_current_day = bool(_EXPLICIT_CURRENT_DAY_PATTERN.search(question_text))
    if has_current_day and not distinct_days:
        return {"version": 1, "mode": "preset", "preset": "today"}
    if len(distinct_days) != 1 or has_current_day:
        return None
    days = distinct_days.pop()
    if days == 7:
        return {"version": 1, "mode": "preset", "preset": "past_7_days"}
    if days == 30:
        return {"version": 1, "mode": "preset", "preset": "past_30_days"}
    if days == 90:
        return {"version": 1, "mode": "preset", "preset": "past_90_days"}
    return {
        "version": 1,
        "mode": "range",
        "start": {"mode": "dynamic", "unit": "day", "offset": -days},
        "end": {"mode": "dynamic", "unit": "day", "offset": -1},
    }


def _question_requires_date_filter(question: str | None, chart_type: str) -> bool:
    if str(chart_type or "").strip().lower() == "metric":
        return False
    question_text = str(question or "")
    return bool(
        _EXPLICIT_CURRENT_DAY_PATTERN.search(question_text)
        or _EXPLICIT_PAST_DAYS_PATTERN.search(question_text)
    )


def normalize_chat_date_filter_for_question(
    question: str | None,
    payload: Any,
    sql: str,
    chart_type: str,
) -> dict[str, Any] | None:
    """将聊天日期配置对齐到用户明确范围或未指定时的过去七天默认值。"""
    expression = _explicit_question_date_expression(question)
    if not isinstance(payload, dict):
        if _question_requires_date_filter(question, chart_type):
            raise ChatDateFilterConfigurationError("missing_date_filter")
        return normalize_chat_date_filter(payload, sql, chart_type)
    if expression is None:
        question_text = str(question or "")
        if (
            _EXPLICIT_PAST_DAYS_PATTERN.search(question_text)
            or _EXPLICIT_CURRENT_DAY_PATTERN.search(question_text)
        ):
            return normalize_chat_date_filter(payload, sql, chart_type)
        expression = _DEFAULT_DATE_EXPRESSION
    normalized_payload = {**payload, "date_expression": expression}
    return normalize_chat_date_filter(normalized_payload, sql, chart_type)


def _date_literal_pattern(parameter_type: str) -> str | None:
    if parameter_type == "yyyymmdd_number":
        return r"\b\d{8}\b"
    if parameter_type == "yyyymmdd_text":
        return r"(?:'\d{8}'|\"\d{8}\")"
    if parameter_type == "date":
        return r"(?:DATE\s+)?(?:'\d{4}-\d{2}-\d{2}'|\"\d{4}-\d{2}-\d{2}\")"
    if parameter_type == "timestamp":
        return r"(?:TIMESTAMP\s+)?(?:'\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}'|\"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}\")"
    return None


def rewrite_chat_date_filter_literals(payload: Any, sql: str) -> str:
    """将已声明日期字段的 BETWEEN 边界保留为看板日期模板。"""
    if not isinstance(payload, dict) or has_dashboard_date_filter_parameters(sql):
        return sql

    time_field = str(payload.get("time_field") or "").strip().rsplit(".", 1)[-1]
    time_field = time_field.strip("`\"[]")
    parameter_type = str(payload.get("date_parameter_type") or "").strip()
    tokens = dashboard_date_parameter_tokens(parameter_type)
    literal_pattern = _date_literal_pattern(parameter_type)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", time_field) or not tokens or not literal_pattern:
        return sql

    field_pattern = rf"(?:(?:{_SQL_IDENTIFIER_PATTERN}\s*\.\s*)*)`?{re.escape(time_field)}`?"
    start_token, end_token = tokens

    # 模型可能把明确的日期范围写成 CURDATE() 计算式；只改写声明时间字段的完整范围。
    current_date_range_pattern = re.compile(
        rf"(?P<field>{field_pattern})\s+BETWEEN\s+"
        rf"(?P<start>.*?{_DATABASE_CURRENT_DATE_PATTERN.pattern}.*?)\s+AND\s+"
        rf"(?P<end>.*?{_DATABASE_CURRENT_DATE_PATTERN.pattern}.*?)"
        rf"(?=\s+(?:AND|OR|GROUP|ORDER|HAVING|LIMIT|UNION)\b|\s*$)",
        re.IGNORECASE | re.DOTALL,
    )
    rewritten_sql = current_date_range_pattern.sub(
        lambda match: f"{match.group('field')} BETWEEN {start_token} AND {end_token}",
        sql,
    )
    if rewritten_sql != sql:
        return rewritten_sql

    pattern = re.compile(
        rf"(?P<field>{field_pattern})\s+BETWEEN\s+(?P<start>{literal_pattern})\s+AND\s+(?P<end>{literal_pattern})",
        re.IGNORECASE,
    )
    return pattern.sub(
        lambda match: f"{match.group('field')} BETWEEN {start_token} AND {end_token}",
        sql,
    )


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
