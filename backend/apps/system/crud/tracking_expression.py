"""
脚本说明：运行时按当前数据源方言编译数据字典 JSON 字段表达式。
"""
from __future__ import annotations

import re


def _text(value) -> str:
    return str(value or "").strip()


def normalize_json_path(value: str | None) -> str:
    text = _text(value)
    if not text:
        return ""
    if text.startswith("$"):
        return text
    return f"$.{text.lstrip('.')}"


def json_path_segments(json_path: str | None) -> list[str]:
    text = normalize_json_path(json_path)
    if not text.startswith("$."):
        return []
    path = text[2:]
    if not path:
        return []
    if re.search(r"[^A-Za-z0-9_.$\[\]]", path):
        return []
    return [
        segment
        for segment in re.split(r"\.", path)
        if segment and "[" not in segment and "]" not in segment
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
    semantic = _text(semantic_type).lower()
    if family == "postgres":
        segments = json_path_segments(path)
        if not segments:
            return ""
        base = f"({column}::jsonb #>> '{{{','.join(segments)}}}')"
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
