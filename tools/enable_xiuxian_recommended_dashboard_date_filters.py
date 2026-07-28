# -*- coding: utf-8 -*-
"""为修仙推荐看板中可安全参数化的 SQL 图表启用日期表达式。"""

from __future__ import annotations

import copy
import re
from typing import Any


START_TOKEN = "{{dashboard_start_yyyymmdd}}"
END_TOKEN = "{{dashboard_end_yyyymmdd}}"
DEFAULT_EXPRESSION = {"version": 1, "mode": "preset", "preset": "past_30_days"}

_PARTITION_RANGE = re.compile(r"\b(?P<alias>[A-Za-z_][\w]*)\.dt\s+BETWEEN\b", re.IGNORECASE)
_CURRENT_DATE = re.compile(r"\bCURDATE\s*\(|\bCURRENT_DATE\b", re.IGNORECASE)
_UNSUPPORTED_SEMANTICS = re.compile(
    r"\b(?:cohort|retention|ltv|d1|d3|d7|d14|d30)\b|留存|生命周期",
    re.IGNORECASE,
)
_BOUNDARY_WORDS = ("AND", "OR", "GROUP", "ORDER", "HAVING", "LIMIT", "UNION")


def _is_word_at(value: str, index: int, words: tuple[str, ...]) -> str | None:
    if index > 0 and (value[index - 1].isalnum() or value[index - 1] == "_"):
        return None
    upper = value[index:].upper()
    for word in words:
        if not upper.startswith(word):
            continue
        end = index + len(word)
        if end >= len(value) or not (value[end].isalnum() or value[end] == "_"):
            return word
    return None


def _find_top_level_word(value: str, start: int, words: tuple[str, ...]) -> int:
    depth = 0
    quote = ""
    index = start
    while index < len(value):
        char = value[index]
        if quote:
            if char == "\\" and index + 1 < len(value):
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in ("'", '"', "`"):
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and _is_word_at(value, index, words):
            return index
        index += 1
    return -1


def is_safe_candidate(sql: str) -> bool:
    source = str(sql or "")
    return bool(
        len(_PARTITION_RANGE.findall(source)) == 1
        and "{{dashboard_" not in source
        and "event_realtime" not in source.lower()
        and len(_CURRENT_DATE.findall(source)) == 2
        and not _UNSUPPORTED_SEMANTICS.search(source)
    )


def replace_unique_partition_range(sql: str) -> str:
    source = str(sql or "")
    matches = list(_PARTITION_RANGE.finditer(source))
    if len(matches) != 1:
        raise ValueError("SQL 不包含唯一分区日期窗口")
    match = matches[0]
    and_index = _find_top_level_word(source, match.end(), ("AND",))
    if and_index < 0:
        raise ValueError("分区日期窗口缺少结束条件")
    suffix_index = _find_top_level_word(source, and_index + 3, _BOUNDARY_WORDS)
    if suffix_index < 0:
        suffix_index = source.find(";", and_index + 3)
    if suffix_index < 0:
        suffix_index = len(source)
    replacement = f"{match.group('alias')}.dt BETWEEN {START_TOKEN} AND {END_TOKEN}"
    suffix = source[suffix_index:]
    separator = " " if suffix and not suffix[0].isspace() else ""
    result = source[: match.start()] + replacement + separator + suffix
    if result.count(START_TOKEN) != 1 or result.count(END_TOKEN) != 1:
        raise ValueError("受控日期参数数量异常")
    return result


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} 配置无效")
    return value


def _date_field(view: dict[str, Any]) -> str:
    pivot = view.get("pivot") if isinstance(view.get("pivot"), dict) else {}
    configured = str(pivot.get("time_field") or "").strip()
    if configured:
        return configured
    chart = view.get("chart") if isinstance(view.get("chart"), dict) else {}
    axes = chart.get("xAxis") if isinstance(chart.get("xAxis"), list) else []
    for axis in axes:
        if not isinstance(axis, dict):
            continue
        field = str(axis.get("value") or axis.get("name") or "").strip()
        if field:
            return field
    return "dt"


def configure_view(view: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(view)
    source_sql = str(result.get("sql") or "")
    if not is_safe_candidate(source_sql):
        raise ValueError("SQL 不属于可安全迁移的唯一分区日期窗口")
    result["sql"] = replace_unique_partition_range(source_sql)
    time_field = _date_field(result)
    source_config = _mapping(result.setdefault("sourceConfig", {}), "sourceConfig")
    sql_config = _mapping(source_config.setdefault("sql", {}), "sourceConfig.sql")
    builder = _mapping(sql_config.setdefault("builder", {}), "sourceConfig.sql.builder")
    builder.update(
        {
            "dateExpressionPickerEnabled": True,
            "timeField": time_field,
            "timeRange": "expression",
            "timeExpression": copy.deepcopy(DEFAULT_EXPRESSION),
        }
    )
    pivot = _mapping(result.setdefault("pivot", {}), "pivot")
    pivot.update(
        {
            "time_field": time_field,
            "range_enabled": True,
            "client_filter_only": False,
            "date_parameter_type": "yyyymmdd_number",
            "date_expression": copy.deepcopy(DEFAULT_EXPRESSION),
        }
    )
    return result
