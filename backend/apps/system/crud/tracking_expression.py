"""
脚本说明：运行时按当前数据源方言编译数据字典 JSON 字段表达式。
"""
from __future__ import annotations

from common.sql_json_paths import json_path_segments as _json_path_segments
from common.sql_json_paths import normalize_json_path as _normalize_json_path


def _text(value) -> str:
    return str(value or "").strip()


def normalize_tracking_property_type(value) -> str:
    """Use the same declared value-type vocabulary for schema and SQL expressions."""
    normalized = _text(value).lower().removesuffix("类型").replace("_", "").replace("-", "").replace(" ", "")
    if normalized in {"int", "integer", "bigint", "smallint", "float", "double", "decimal",
                      "number", "numeric", "real", "数值", "数字", "整数", "小数"}:
        return "number"
    if normalized in {"bool", "boolean", "布尔", "布尔值"}:
        return "boolean"
    if normalized in {"date", "datetime", "timestamp", "日期", "时间", "日期时间"}:
        return "datetime"
    return "text"


def normalize_json_path(value: str | None) -> str:
    return _normalize_json_path(value)


def json_path_segments(json_path: str | None) -> list[str]:
    segments = _json_path_segments(normalize_json_path(json_path))
    if segments is None:
        return []
    return [
        segment[1:-1]
        if segment.startswith("[") and segment.endswith("]") and segment[1:-1].isdigit()
        else segment
        for segment in segments
    ]


def datasource_family(datasource_type: str | None) -> str:
    text = _text(datasource_type).lower()
    if text in {"mysql", "mariadb"} or "mysql" in text:
        return "mysql"
    if text in {"pg", "postgres", "postgresql", "kingbase", "redshift", "excel"} or "postgres" in text:
        return "postgres"
    if text in {"clickhouse", "ck"} or "clickhouse" in text:
        return "clickhouse"
    return ""


def quote_identifier(identifier: str, family: str) -> str:
    quote = '"' if family == "postgres" else "`"
    escaped = str(identifier or "").replace(quote, quote + quote)
    return f"{quote}{escaped}{quote}"


def qualified_field(table_name: str, field_name: str, family: str) -> str:
    return f"{quote_identifier(table_name, family)}.{quote_identifier(field_name, family)}"


def _postgres_typed_json_expression(column: str, segments: tuple[str, ...]) -> str:
    expression = f"{column}::jsonb"
    for index, segment in enumerate(segments):
        is_array_index = (
            segment.startswith("[")
            and segment.endswith("]")
            and segment[1:-1].isdigit()
        )
        operand = segment[1:-1] if is_array_index else f"'{segment}'"
        operator = "->>" if index == len(segments) - 1 else "->"
        expression = f"{expression} {operator} {operand}"
    return f"({expression})"


def compile_tracking_json_expression(
    table_name: str,
    source_field: str,
    json_path: str,
    semantic_type: str | None,
    datasource_type: str | None,
) -> str:
    """
    是什么：把数据字典的 source_field/json_path 按当前数据源方言编译成 SQL 表达式。
    """
    family = datasource_family(datasource_type)
    if not family or not table_name or not source_field or not json_path:
        return ""

    column = qualified_field(table_name, source_field, family)
    path = normalize_json_path(json_path)
    semantic = normalize_tracking_property_type(semantic_type)
    if family == "postgres":
        typed_segments = _json_path_segments(path)
        if typed_segments is None or not typed_segments:
            return ""
        base = _postgres_typed_json_expression(column, typed_segments)
        if semantic == "number":
            return f"NULLIF({base}, '')::numeric"
        return base
    if family == "clickhouse":
        base = f"JSON_VALUE({column}, '{path}')"
        if semantic == "number":
            return f"toFloat64OrNull({base})"
        return base
    base = f"JSON_UNQUOTE(JSON_EXTRACT({column}, '{path}'))"
    if semantic == "number":
        return f"CAST({base} AS DECIMAL(38, 10))"
    return base
