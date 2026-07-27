"""看板 SQL 日期参数模板的纯函数处理。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from apps.datasource.crud.sql_permission import extract_physical_tables, parse_sql_statements
from common.core.config import settings


DateParameterType = Literal["date", "yyyymmdd_number", "yyyymmdd_text", "timestamp"]

_PARAMETER_TOKENS: dict[DateParameterType, tuple[str, str]] = {
    "date": ("{{dashboard_start_date}}", "{{dashboard_end_date}}"),
    "yyyymmdd_number": (
        "{{dashboard_start_yyyymmdd}}",
        "{{dashboard_end_yyyymmdd}}",
    ),
    "yyyymmdd_text": (
        "{{dashboard_start_yyyymmdd}}",
        "{{dashboard_end_yyyymmdd}}",
    ),
    "timestamp": (
        "{{dashboard_start_timestamp}}",
        "{{dashboard_end_exclusive_timestamp}}",
    ),
}
_ALL_TOKENS = tuple(dict.fromkeys(token for pair in _PARAMETER_TOKENS.values() for token in pair))
_TOKEN_FAMILIES = {
    token: "yyyymmdd" if "yyyymmdd" in token else parameter_type
    for parameter_type, pair in _PARAMETER_TOKENS.items()
    for token in pair
}


@dataclass(frozen=True)
class DashboardDateFilterPreparation:
    sql: str
    start: str | None
    end: str | None
    physical_tables: set[str]
    capability: dict[str, Any]


def default_dashboard_date_range(*, today: date | None = None) -> tuple[date, date]:
    business_today = today or datetime.now(ZoneInfo(settings.DASHBOARD_BUSINESS_TIMEZONE)).date()
    end = business_today - timedelta(days=1)
    return end - timedelta(days=13), end


def _pivot_value(pivot: Any | None, key: str, default: Any = None) -> Any:
    if isinstance(pivot, dict):
        return pivot.get(key, default)
    return getattr(pivot, key, default)


def _scan_sql_tokens(sql: str, replacements: dict[str, str] | None = None) -> tuple[str, set[str]]:
    """只读取 SQL 正文中的受控 token，并可在同一次扫描中替换。"""
    output: list[str] = []
    active: set[str] = set()
    state = "normal"
    index = 0
    length = len(sql)

    while index < length:
        char = sql[index]
        following = sql[index + 1] if index + 1 < length else ""

        if state == "normal":
            token = next((item for item in _ALL_TOKENS if sql.startswith(item, index)), None)
            if token:
                active.add(token)
                output.append(replacements.get(token, token) if replacements else token)
                index += len(token)
                continue
            if char == "'":
                state = "single"
            elif char == '"':
                state = "double"
            elif char == "`":
                state = "backtick"
            elif char == "[":
                state = "bracket"
            elif char == "-" and following == "-":
                state = "line_comment"
            elif char == "#":
                state = "line_comment"
            elif char == "/" and following == "*":
                state = "block_comment"
            output.append(char)
            index += 1
            continue

        output.append(char)
        index += 1
        if state == "single" and char == "'":
            if following == "'":
                output.append(following)
                index += 1
            else:
                state = "normal"
        elif state == "double" and char == '"':
            if following == '"':
                output.append(following)
                index += 1
            else:
                state = "normal"
        elif state == "backtick" and char == "`":
            if following == "`":
                output.append(following)
                index += 1
            else:
                state = "normal"
        elif state == "bracket" and char == "]":
            if following == "]":
                output.append(following)
                index += 1
            else:
                state = "normal"
        elif state == "line_comment" and char in "\r\n":
            state = "normal"
        elif state == "block_comment" and char == "*" and following == "/":
            output.append(following)
            index += 1
            state = "normal"

    return "".join(output), active


def _sql_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _parse_date_value(value: Any) -> date:
    text = str(value or "").strip()
    parsed = date.fromisoformat(text)
    if parsed.isoformat() != text:
        raise ValueError("日期格式需为 YYYY-MM-DD")
    return parsed


def _unconfigured(sql: str, physical_tables: set[str], reason: str) -> DashboardDateFilterPreparation:
    return DashboardDateFilterPreparation(
        sql=sql,
        start=None,
        end=None,
        physical_tables=physical_tables,
        capability={"status": "unconfigured", "reason": reason},
    )


def prepare_dashboard_date_filter(
    sql: str,
    *,
    ds_type: str | None,
    pivot: Any | None,
    today: date | None = None,
) -> DashboardDateFilterPreparation:
    """只处理显式受控模板，不猜测字段，也不改写其他 SQL 条件。"""
    source_sql = str(sql or "")
    parse_replacements = {token: "0" for token in _ALL_TOKENS}
    parse_sql, active_tokens = _scan_sql_tokens(source_sql, parse_replacements)
    try:
        physical_tables = extract_physical_tables(parse_sql_statements(parse_sql, ds_type))
    except Exception:
        return _unconfigured(source_sql, set(), "sql_parse_failed")

    if "event_realtime" in {table.lower() for table in physical_tables}:
        return DashboardDateFilterPreparation(
            sql=source_sql,
            start=None,
            end=None,
            physical_tables=physical_tables,
            capability={"status": "realtime", "reason": "realtime_table"},
        )

    if not str(_pivot_value(pivot, "time_field", "") or "").strip():
        return _unconfigured(source_sql, physical_tables, "missing_time_field")

    parameter_type = str(_pivot_value(pivot, "date_parameter_type", "") or "").strip()
    if parameter_type not in _PARAMETER_TOKENS:
        return _unconfigured(source_sql, physical_tables, "invalid_parameter_type")
    if not active_tokens:
        return _unconfigured(source_sql, physical_tables, "missing_parameters")

    active_families = {_TOKEN_FAMILIES[token] for token in active_tokens}
    expected_family = "yyyymmdd" if parameter_type.startswith("yyyymmdd") else parameter_type
    if len(active_families) > 1:
        return _unconfigured(source_sql, physical_tables, "mixed_parameter_families")
    if active_families != {expected_family}:
        return _unconfigured(source_sql, physical_tables, "parameter_type_mismatch")

    expected_tokens = set(_PARAMETER_TOKENS[parameter_type])
    if active_tokens != expected_tokens:
        return _unconfigured(source_sql, physical_tables, "incomplete_parameters")

    business_today = today or datetime.now(ZoneInfo(settings.DASHBOARD_BUSINESS_TIMEZONE)).date()
    default_start, default_end = default_dashboard_date_range(today=business_today)
    try:
        if str(_pivot_value(pivot, "range", "") or "").strip().lower() == "custom":
            start, end = (
                _parse_date_value(_pivot_value(pivot, "custom_start", "")),
                _parse_date_value(_pivot_value(pivot, "custom_end", "")),
            )
        else:
            start, end = default_start, default_end
    except (TypeError, ValueError):
        return _unconfigured(source_sql, physical_tables, "invalid_date_range")

    if start > end or start > default_end or end > default_end:
        return _unconfigured(source_sql, physical_tables, "invalid_date_range")

    start_text = start.isoformat()
    end_text = end.isoformat()
    if parameter_type == "date":
        values = (_sql_string_literal(start_text), _sql_string_literal(end_text))
    elif parameter_type == "yyyymmdd_number":
        values = (start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
    elif parameter_type == "yyyymmdd_text":
        values = (
            _sql_string_literal(start.strftime("%Y%m%d")),
            _sql_string_literal(end.strftime("%Y%m%d")),
        )
    else:
        start_timestamp = datetime.combine(start, time.min).strftime("%Y-%m-%d %H:%M:%S")
        end_exclusive = datetime.combine(end + timedelta(days=1), time.min).strftime("%Y-%m-%d %H:%M:%S")
        values = (_sql_string_literal(start_timestamp), _sql_string_literal(end_exclusive))

    rendered_sql, _ = _scan_sql_tokens(
        source_sql,
        dict(zip(_PARAMETER_TOKENS[parameter_type], values, strict=True)),
    )
    return DashboardDateFilterPreparation(
        sql=rendered_sql,
        start=start_text,
        end=end_text,
        physical_tables=physical_tables,
        capability={
            "status": "available",
            "reason": "",
            "parameterType": parameter_type,
            "defaultStart": default_start.isoformat(),
            "defaultEnd": default_end.isoformat(),
            "maxEnd": default_end.isoformat(),
        },
    )
