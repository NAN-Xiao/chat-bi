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
_DATE_EXPRESSION_PRESETS = {
    "yesterday",
    "today",
    "previous_week",
    "current_week",
    "previous_month",
    "current_month",
    "past_7_days",
    "recent_7_days",
    "past_30_days",
    "recent_30_days",
    "past_90_days",
    "all_time",
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


def resolve_dashboard_date_expression(expression: Any, *, today: date) -> tuple[date, date]:
    """将版本化看板日期表达式解析为业务日期范围。"""
    if not isinstance(expression, dict) or expression.get("version") != 1:
        raise ValueError("invalid_date_expression")

    mode = expression.get("mode")
    if mode == "preset":
        preset = expression.get("preset")
        if preset not in _DATE_EXPRESSION_PRESETS:
            raise ValueError("invalid_date_expression")
        monday = today - timedelta(days=today.weekday())
        previous_month_end = today.replace(day=1) - timedelta(days=1)
        ranges = {
            "yesterday": (today - timedelta(days=1), today - timedelta(days=1)),
            "today": (today, today),
            "previous_week": (monday - timedelta(days=7), monday - timedelta(days=1)),
            "current_week": (monday, today),
            "previous_month": (previous_month_end.replace(day=1), previous_month_end),
            "current_month": (today.replace(day=1), today),
            "past_7_days": (today - timedelta(days=7), today - timedelta(days=1)),
            "recent_7_days": (today - timedelta(days=6), today),
            "past_30_days": (today - timedelta(days=30), today - timedelta(days=1)),
            "recent_30_days": (today - timedelta(days=29), today),
            "past_90_days": (today - timedelta(days=90), today - timedelta(days=1)),
            "all_time": (date(1000, 1, 1), date(9999, 12, 31)),
        }
        return ranges[preset]

    if mode != "range":
        raise ValueError("invalid_date_expression")

    def endpoint(raw: Any) -> date:
        if not isinstance(raw, dict):
            raise ValueError("invalid_date_expression")
        if raw.get("mode") == "static":
            return _parse_date_value(raw.get("date"))
        offset = raw.get("offset")
        if (
            raw.get("mode") == "dynamic"
            and raw.get("unit") == "day"
            and isinstance(offset, int)
            and not isinstance(offset, bool)
            and offset <= 0
        ):
            try:
                return today + timedelta(days=offset)
            except OverflowError as exc:
                raise ValueError("invalid_date_expression") from exc
        raise ValueError("invalid_date_expression")

    start, end = endpoint(expression.get("start")), endpoint(expression.get("end"))
    if start > end:
        raise ValueError("invalid_date_expression")
    return start, end


def _pivot_value(pivot: Any | None, key: str, default: Any = None) -> Any:
    if isinstance(pivot, dict):
        return pivot.get(key, default)
    return getattr(pivot, key, default)


def _scan_sql_tokens(sql: str, replacements: dict[str, str] | None = None) -> tuple[str, set[str]]:
    """只读取 SQL 正文中的受控 token，并可在同一次扫描中替换。"""
    output: list[str] = []
    active: set[str] = set()
    state = "normal"
    dollar_quote = ""
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
            elif char == "$":
                closing = sql.find("$", index + 1)
                candidate = sql[index:closing + 1] if closing >= 0 else ""
                tag = candidate[1:-1]
                if candidate and (not tag or (tag[0].isalpha() or tag[0] == "_") and all(
                    part.isalnum() or part == "_" for part in tag
                )):
                    state = "dollar_quote"
                    dollar_quote = candidate
                    output.append(candidate)
                    index += len(candidate)
                    continue
            output.append(char)
            index += 1
            continue

        if state == "dollar_quote" and sql.startswith(dollar_quote, index):
            output.append(dollar_quote)
            index += len(dollar_quote)
            state = "normal"
            dollar_quote = ""
            continue

        output.append(char)
        index += 1
        if state in {"single", "double", "backtick"} and char == "\\" and following:
            output.append(following)
            index += 1
        elif state == "single" and char == "'":
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


def _normalize_datasource_type(ds_type: str | None) -> str:
    return str(ds_type or "").strip().lower().replace("-", "_")


def _sql_date_literal(value: str, ds_type: str | None) -> str:
    literal = _sql_string_literal(value)
    ds_key = _normalize_datasource_type(ds_type)
    if ds_key in {"mysql", "doris", "starrocks"}:
        return f"DATE({literal})"
    if ds_key in {"ck", "clickhouse"}:
        return f"toDate({literal})"
    if ds_key in {"sqlserver", "sql server", "sql_server"}:
        return f"CAST({literal} AS DATE)"
    if ds_key in {"oracle", "dm"}:
        return f"TO_DATE({literal}, 'YYYY-MM-DD')"
    if ds_key == "hive":
        return f"TO_DATE({literal})"
    return f"DATE {literal}"


def _sql_timestamp_literal(value: str, ds_type: str | None) -> str:
    literal = _sql_string_literal(value)
    ds_key = _normalize_datasource_type(ds_type)
    if ds_key in {"mysql", "doris", "starrocks"}:
        return f"TIMESTAMP({literal})"
    if ds_key in {"ck", "clickhouse"}:
        return f"toDateTime({literal})"
    if ds_key in {"sqlserver", "sql server", "sql_server"}:
        return f"CAST({literal} AS DATETIME2)"
    if ds_key in {"oracle", "dm"}:
        return f"TO_TIMESTAMP({literal}, 'YYYY-MM-DD HH24:MI:SS')"
    if ds_key == "hive":
        return f"CAST({literal} AS TIMESTAMP)"
    return f"TIMESTAMP {literal}"


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


def has_dashboard_date_filter_parameters(sql: str) -> bool:
    """判断 SQL 正文是否包含受控日期 token。"""
    _, active_tokens = _scan_sql_tokens(str(sql or ""))
    return bool(active_tokens)


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

    if _pivot_value(pivot, "range_enabled", True) is False:
        return _unconfigured(source_sql, physical_tables, "range_disabled")

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
    expression = _pivot_value(pivot, "date_expression", None)
    try:
        if expression is not None:
            if (
                isinstance(expression, dict)
                and expression.get("mode") == "preset"
                and expression.get("preset") == "all_time"
                and not parameter_type.startswith("yyyymmdd")
            ):
                raise ValueError("invalid_date_expression")
            start, end = resolve_dashboard_date_expression(expression, today=business_today)
        elif str(_pivot_value(pivot, "range", "") or "").strip().lower() == "custom":
            start, end = (
                _parse_date_value(_pivot_value(pivot, "custom_start", "")),
                _parse_date_value(_pivot_value(pivot, "custom_end", "")),
            )
        else:
            start, end = default_start, default_end
    except (TypeError, ValueError):
        reason = "invalid_date_expression" if expression is not None else "invalid_date_range"
        return _unconfigured(source_sql, physical_tables, reason)

    if expression is None and (start > end or start > default_end or end > default_end):
        return _unconfigured(source_sql, physical_tables, "invalid_date_range")

    start_text = start.isoformat()
    end_text = end.isoformat()
    if parameter_type == "date":
        values = (_sql_date_literal(start_text, ds_type), _sql_date_literal(end_text, ds_type))
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
        values = (
            _sql_timestamp_literal(start_timestamp, ds_type),
            _sql_timestamp_literal(end_exclusive, ds_type),
        )

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
            "expression": expression,
            "resolvedStart": start_text,
            "resolvedEnd": end_text,
            "timezone": settings.DASHBOARD_BUSINESS_TIMEZONE,
            "maxEnd": business_today.isoformat() if expression is not None else default_end.isoformat(),
        },
    )
