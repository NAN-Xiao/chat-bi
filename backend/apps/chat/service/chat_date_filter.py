"""聊天图表的看板日期参数校验与渲染。"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from apps.dashboard.crud.dashboard_date_filter import (
    dashboard_date_parameter_tokens,
    has_dashboard_date_filter_parameters,
    has_unresolved_dashboard_date_parameters,
    prepare_dashboard_date_filter,
    validate_dashboard_date_parameter_sql,
)
from common.core.config import settings


_DATABASE_CURRENT_DATE_PATTERN = re.compile(
    r"\b(?:CURDATE|CURRENT_DATE|NOW|CURRENT_TIMESTAMP|LOCALTIME|LOCALTIMESTAMP|GETDATE|GETUTCDATE)\b",
    re.IGNORECASE,
)

_SQL_IDENTIFIER_PATTERN = r'(?:`[^`]+`|"[^"]+"|\[[^\]]+\]|[A-Za-z_][A-Za-z0-9_$]*)'
_EXPLICIT_PAST_DAYS_PATTERN = re.compile(
    r"(?:最近|近|过去)\s*(?P<days>[1-9]\d{0,3})\s*(?:个\s*)?(?:完整\s*)?(?:自然\s*)?[天日]"
)
_EXPLICIT_CURRENT_DAY_PATTERN = re.compile(r"(?:今天|今日|当天)")
_EXPLICIT_CURRENT_TIME_BUCKET_PATTERN = re.compile(r"当前\s*(?:小时|分钟|整点)")
_REALTIME_PATTERN = re.compile(r"实时")
_TIME_SERIES_PATTERN = re.compile(
    r"(?:趋势|走势|变化|每日|每天|逐日|按天|按日|每周|按周|每月|按月|"
    r"每小时|按小时|逐小时|daily|weekly|monthly|hourly|trend|over\s+time)",
    re.IGNORECASE,
)
_EXPLICIT_YESTERDAY_PATTERN = re.compile(r"(?:昨天|昨日)")
_EXPLICIT_DAY_BEFORE_YESTERDAY_PATTERN = re.compile(r"前天")
_EXPLICIT_ABSOLUTE_DATE_PATTERN = re.compile(
    r"(?<!\d)\d{4}(?:[-/.]\d{1,2}[-/.]\d{1,2}|年\d{1,2}月\d{1,2}日?)(?!\d)"
)
_SQL_DATE_LITERAL_PATTERN = re.compile(
    r"(?<!\d)(?:(?:19|20)\d{6}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2})(?!\d)"
)
_EXPLICIT_NAMED_PERIOD_PATTERN = re.compile(r"本月")
_EXPLICIT_RELATIVE_PERIOD_PATTERN = re.compile(
    r"(?:(?:最近|近)\s*(?:两|[1-9]\d{0,3})\s*(?:个\s*)?周|"
    r"(?:最近|近)\s*(?:一|1)\s*个?月)"
)
_EXPLICIT_REALTIME_SCALAR_TERMS = (
    "总额",
    "总的",
    "合计",
    "汇总",
    "总计",
    "单值",
    "指标卡",
    "截至当前",
    "截至目前",
    "当前累计",
)
_DEFAULT_DATE_EXPRESSION = {"version": 1, "mode": "preset", "preset": "past_7_days"}

QuestionDateScope = Literal["current_day", "explicit_other", "unspecified"]


class ChatDateFilterConfigurationError(ValueError):
    """聊天 SQL 的日期模板配置不完整或不一致。"""


def system_business_date() -> date:
    """返回 Smart Q&A 统一使用的系统业务日期。"""
    return datetime.now(ZoneInfo(settings.DASHBOARD_BUSINESS_TIMEZONE)).date()


def _parse_contract_date(value: Any) -> date:
    text = str(value or "").strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise ChatDateFilterConfigurationError("invalid_time_range") from error
    if parsed.isoformat() != text:
        raise ChatDateFilterConfigurationError("invalid_time_range")
    return parsed


def _static_date_expression(start: date, end: date) -> dict[str, Any]:
    return {
        "version": 1,
        "mode": "range",
        "start": {"mode": "static", "date": start.isoformat()},
        "end": {"mode": "static", "date": end.isoformat()},
    }


def normalize_chat_date_filter_contract(
    payload: Any,
    sql: str,
    chart_type: str,
    *,
    time_scope: Any,
    time_range: Any,
    business_date: date | None = None,
    requires_current_business_day: bool = False,
) -> dict[str, Any] | None:
    """校验同一次 LLM 响应中的具体日期契约，不重新解释用户自然语言。"""
    if str(chart_type or "").strip().lower() == "metric":
        return normalize_chat_date_filter(payload, sql, chart_type)
    if time_scope not in {"explicit", "unspecified"}:
        raise ChatDateFilterConfigurationError("missing_time_scope")
    if not isinstance(time_range, dict):
        raise ChatDateFilterConfigurationError("missing_time_range")

    start = _parse_contract_date(time_range.get("start_date"))
    end = _parse_contract_date(time_range.get("end_date"))
    if start > end:
        raise ChatDateFilterConfigurationError("invalid_time_range")

    anchor = business_date or system_business_date()
    if end > anchor:
        raise ChatDateFilterConfigurationError("time_range_exceeds_business_date")
    if requires_current_business_day:
        if time_scope != "explicit" or (start, end) != (anchor, anchor):
            raise ChatDateFilterConfigurationError("invalid_current_day_time_range")
    elif time_scope == "unspecified":
        expected_start = anchor - timedelta(days=7)
        expected_end = anchor - timedelta(days=1)
        if (start, end) != (expected_start, expected_end):
            raise ChatDateFilterConfigurationError("invalid_default_time_range")

    if not isinstance(payload, dict):
        raise ChatDateFilterConfigurationError("missing_date_filter")
    expected_expression = _static_date_expression(start, end)
    if payload.get("date_expression") != expected_expression:
        raise ChatDateFilterConfigurationError("time_range_mismatch")
    parameter_type = str(payload.get("date_parameter_type") or "").strip()
    tokens = dashboard_date_parameter_tokens(parameter_type)
    if tokens is None or not all(token in sql for token in tokens):
        raise ChatDateFilterConfigurationError("missing_parameters")
    return normalize_chat_date_filter(payload, sql, chart_type)


DASHBOARD_DATE_FILTER_DISABLED_GUIDANCE = """
当前工作空间未启用看板日期参数能力。生成 SQL 时必须遵守以下运行时约束：
1. 不得返回 date_filter 字段。
2. 不得使用任何 {{dashboard_start_*}}、{{dashboard_end_*}} 或其他 dashboard 日期占位符。
3. 用户明确要求时间范围或连续日期时，使用当前数据源业务日期字段和已加载 Data Skill 中定义的可执行日期边界；可以从事实数据的最大业务日期推导范围，或使用可执行的日期字面量。
4. 不得把未解析的日期占位符交给 SQL 执行器；如果当前数据源无法表达用户要求，应明确说明缺少可执行的日期口径。
""".strip()


def ensure_chat_date_filter_allowed(enabled: bool, payload: Any, sql: str) -> None:
    """拒绝未启用看板日期能力的租户使用日期配置或占位符。"""
    if enabled:
        return
    if payload not in (None, {}) or has_unresolved_dashboard_date_parameters(sql):
        raise ChatDateFilterConfigurationError("dashboard_date_filter_disabled")


def question_date_scope(question: str | None) -> QuestionDateScope:
    """识别问题日期范围；明确日期优先于“实时”的今天默认值。"""
    text = str(question or "")
    has_explicit_other = bool(
        _EXPLICIT_PAST_DAYS_PATTERN.search(text)
        or _EXPLICIT_YESTERDAY_PATTERN.search(text)
        or _EXPLICIT_DAY_BEFORE_YESTERDAY_PATTERN.search(text)
        or _EXPLICIT_ABSOLUTE_DATE_PATTERN.search(text)
        or _EXPLICIT_NAMED_PERIOD_PATTERN.search(text)
        or _EXPLICIT_RELATIVE_PERIOD_PATTERN.search(text)
    )
    if has_explicit_other:
        return "explicit_other"
    if (
        _EXPLICIT_CURRENT_DAY_PATTERN.search(text)
        or _EXPLICIT_CURRENT_TIME_BUCKET_PATTERN.search(text)
        or _REALTIME_PATTERN.search(text)
    ):
        return "current_day"
    return "unspecified"


def _explicit_question_date_expression(question: str | None) -> dict[str, Any] | None:
    """将问题中明确的时间范围转换为平台支持的版本化日期表达式。"""
    question_text = str(question or "")
    if _EXPLICIT_NAMED_PERIOD_PATTERN.search(question_text):
        return {"version": 1, "mode": "preset", "preset": "current_month"}
    matches = _EXPLICIT_PAST_DAYS_PATTERN.findall(question_text)
    distinct_days = {int(value) for value in matches}
    has_current_day = bool(_EXPLICIT_CURRENT_DAY_PATTERN.search(question_text))
    has_yesterday = bool(_EXPLICIT_YESTERDAY_PATTERN.search(question_text))
    has_day_before_yesterday = bool(
        _EXPLICIT_DAY_BEFORE_YESTERDAY_PATTERN.search(question_text)
    )
    has_absolute_date = bool(_EXPLICIT_ABSOLUTE_DATE_PATTERN.search(question_text))
    if has_absolute_date:
        return None
    if len(distinct_days) > 1 or (
        distinct_days and (has_current_day or has_yesterday or has_day_before_yesterday)
    ):
        return None
    if sum((has_current_day, has_yesterday, has_day_before_yesterday)) > 1:
        return None
    if distinct_days:
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
    if has_yesterday:
        return {"version": 1, "mode": "preset", "preset": "yesterday"}
    if has_day_before_yesterday:
        return {
            "version": 1,
            "mode": "range",
            "start": {"mode": "dynamic", "unit": "day", "offset": -2},
            "end": {"mode": "dynamic", "unit": "day", "offset": -2},
        }
    if has_current_day or question_date_scope(question_text) == "current_day":
        return {"version": 1, "mode": "preset", "preset": "today"}
    return None


def _question_requires_date_filter(question: str | None, chart_type: str, sql: str = "") -> bool:
    if str(chart_type or "").strip().lower() == "metric":
        return (
            question_date_scope(question) != "unspecified"
            or bool(_SQL_DATE_LITERAL_PATTERN.search(sql))
            or bool(_DATABASE_CURRENT_DATE_PATTERN.search(sql))
        )
    if _TIME_SERIES_PATTERN.search(str(question or "")):
        return True
    return False


def _question_explicitly_requests_realtime_scalar(question: str | None) -> bool:
    """识别用户明确要求实时汇总值的通用表达，不绑定具体业务指标。"""
    text = str(question or "")
    if not _REALTIME_PATTERN.search(text):
        return False
    if _TIME_SERIES_PATTERN.search(text):
        return False
    if any(term in text for term in _EXPLICIT_REALTIME_SCALAR_TERMS):
        return True
    return not re.search(r"(?:按|各|每)\s*[\u4e00-\u9fffA-Za-z]", text)


def normalize_chat_date_filter_for_question(
    question: str | None,
    payload: Any,
    sql: str,
    chart_type: str,
) -> dict[str, Any] | None:
    """校验时间序列的日期配置，未指定窗口时使用过去七天。"""
    question_text = str(question or "")
    if (
        str(chart_type or "").strip().lower() == "metric"
        and _TIME_SERIES_PATTERN.search(question_text)
    ):
        raise ChatDateFilterConfigurationError("realtime_requires_hourly_time_series")

    expression = _explicit_question_date_expression(question)
    if not isinstance(payload, dict):
        if _question_requires_date_filter(question, chart_type, sql):
            raise ChatDateFilterConfigurationError("missing_date_filter")
        return normalize_chat_date_filter(payload, sql, chart_type)
    if expression is None:
        if question_date_scope(question_text) == "explicit_other":
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
    """校验并将已声明日期字段的 BETWEEN 字面量改写为看板日期模板。"""
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

    if _DATABASE_CURRENT_DATE_PATTERN.search(sql):
        expression = payload.get("date_expression")
        if isinstance(expression, dict) and expression.get("mode") == "range":
            raise ChatDateFilterConfigurationError("database_current_date")

    pattern = re.compile(
        rf"(?P<field>{field_pattern})\s+BETWEEN\s+(?P<start>{literal_pattern})\s+AND\s+(?P<end>{literal_pattern})",
        re.IGNORECASE,
    )
    expression = payload.get("date_expression")
    expected_literals: tuple[str, str] | None = None
    if isinstance(expression, dict) and expression.get("mode") == "range":
        raw_start = expression.get("start")
        raw_end = expression.get("end")
        if (
            isinstance(raw_start, dict)
            and raw_start.get("mode") == "static"
            and isinstance(raw_end, dict)
            and raw_end.get("mode") == "static"
        ):
            start_date = _parse_contract_date(raw_start.get("date"))
            end_date = _parse_contract_date(raw_end.get("date"))
            if parameter_type == "yyyymmdd_number":
                expected_literals = (start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d"))
            elif parameter_type == "yyyymmdd_text":
                expected_literals = (
                    f"'{start_date.strftime('%Y%m%d')}'",
                    f"'{end_date.strftime('%Y%m%d')}'",
                )
            elif parameter_type == "date":
                expected_literals = (f"'{start_date.isoformat()}'", f"'{end_date.isoformat()}'")
            elif parameter_type == "timestamp":
                expected_literals = (
                    f"'{start_date.isoformat()} 00:00:00'",
                    f"'{(end_date + timedelta(days=1)).isoformat()} 00:00:00'",
                )

    def replace_literal_range(match: re.Match[str]) -> str:
        if expected_literals is not None:
            actual = (match.group("start").replace('"', "'"), match.group("end").replace('"', "'"))
            if actual != expected_literals:
                raise ChatDateFilterConfigurationError("sql_time_range_mismatch")
        return f"{match.group('field')} BETWEEN {start_token} AND {end_token}"

    rewritten_sql = pattern.sub(replace_literal_range, sql)
    if rewritten_sql != sql:
        return rewritten_sql

    comparison_pattern = re.compile(
        rf"(?P<field>{field_pattern})\s*(?P<operator>>=|<=|<|=)\s*"
        rf"(?P<literal>{literal_pattern})",
        re.IGNORECASE,
    )

    def replace_literal_comparison(match: re.Match[str]) -> str:
        operator = match.group("operator")
        literal = match.group("literal").replace('"', "'")
        if expected_literals is not None:
            start_literal, end_literal = expected_literals
            if operator == ">=":
                if literal != start_literal:
                    raise ChatDateFilterConfigurationError("sql_time_range_mismatch")
                replacement = start_token
            elif operator in {"<=", "<"}:
                if literal != end_literal:
                    raise ChatDateFilterConfigurationError("sql_time_range_mismatch")
                replacement = end_token
            else:
                if start_literal != end_literal or literal != start_literal:
                    raise ChatDateFilterConfigurationError("sql_time_range_mismatch")
                return f"{match.group('field')} BETWEEN {start_token} AND {end_token}"
        else:
            replacement = start_token if operator == ">=" else end_token
        return f"{match.group('field')} {operator} {replacement}"

    return comparison_pattern.sub(replace_literal_comparison, sql)


def normalize_chat_date_filter(payload: Any, sql: str, chart_type: str) -> dict[str, Any] | None:
    """校验聊天 SQL 响应中的日期配置，并转换为看板 pivot。"""
    has_tokens = has_unresolved_dashboard_date_parameters(sql)
    if payload in (None, {}):
        if has_tokens:
            raise ChatDateFilterConfigurationError("missing_date_filter")
        return None
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
        if has_unresolved_dashboard_date_parameters(sql):
            raise ChatDateFilterConfigurationError("date_filter_render_incomplete")
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
    if has_unresolved_dashboard_date_parameters(prepared.sql):
        raise ChatDateFilterConfigurationError("date_filter_render_incomplete")
    return prepared.sql
