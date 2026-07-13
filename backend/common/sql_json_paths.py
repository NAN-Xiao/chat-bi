from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlglot import exp, parse_one


@dataclass(frozen=True)
class JsonPathAccess:
    table_alias: str
    source_field: str
    json_path: str
    consumed_column_ids: frozenset[int]


@dataclass(frozen=True)
class JsonPathIssue:
    table_alias: str
    source_field: str
    reason: str


@dataclass(frozen=True)
class JsonAccessExtraction:
    accesses: tuple[JsonPathAccess, ...]
    issues: tuple[JsonPathIssue, ...]
    consumed_column_ids: frozenset[int]


_JSON_DIALECTS = {"mysql", "postgres", "clickhouse"}
_SIMPLE_JSON_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_JSON_EXPRESSION_TYPES = tuple(
    expression_type
    for expression_type in (
        getattr(exp, "JSONExtract", None),
        getattr(exp, "JSONExtractScalar", None),
        getattr(exp, "JSONBExtract", None),
        getattr(exp, "JSONBExtractScalar", None),
    )
    if expression_type is not None
)


def json_path_segments(value: Any) -> tuple[str, ...] | None:
    path = str(value or "").strip()
    if not path or path[0] != "$":
        return None
    if path == "$":
        return ()

    segments: list[str] = []
    offset = 1
    while offset < len(path):
        if path[offset] == ".":
            match = re.match(r"\.([A-Za-z_][A-Za-z0-9_]*)", path[offset:])
            if not match:
                return None
            segments.append(match.group(1))
            offset += len(match.group(0))
            continue
        if path[offset] == "[":
            match = re.match(r"\[(\d+)\]", path[offset:])
            if match:
                segments.append(f"[{match.group(1)}]")
                offset += len(match.group(0))
                continue
            quoted = re.match(r"\[['\"]([^'\"]+)['\"]\]", path[offset:])
            if quoted:
                segments.append(quoted.group(1))
                offset += len(quoted.group(0))
                continue
        return None
    return tuple(segments)


def _format_json_path_segments(segments: tuple[str, ...] | list[str]) -> str:
    parts = ["$"]
    for segment in segments:
        if segment.startswith("[") and segment.endswith("]") and segment[1:-1].isdigit():
            parts.append(segment)
        elif _SIMPLE_JSON_KEY.fullmatch(segment):
            parts.append(f".{segment}")
        elif '"' not in segment and "\\" not in segment:
            parts.append(f'["{segment}"]')
        else:
            return ""
    return "".join(parts)


def normalize_json_path(value: Any, *, postgres: bool = False) -> str:
    path = str(value or "").strip()
    if len(path) >= 2 and path[0] == path[-1] and path[0] in {"'", '"'}:
        path = path[1:-1].strip()
    if postgres and path.startswith("{") and path.endswith("}"):
        raw_segments = [item.strip().strip("'\"") for item in path[1:-1].split(",")]
        if any(not item for item in raw_segments):
            return ""
        path = _format_json_path_segments([
            f"[{item}]" if item.isdigit() else item
            for item in raw_segments
        ])
    elif path and not path.startswith("$"):
        path = f"$.{path.lstrip('.')}"
    segments = json_path_segments(path)
    if segments is None:
        return ""
    return _format_json_path_segments(segments)


def json_paths_intersect(left: str, right: str) -> bool:
    left_segments = json_path_segments(normalize_json_path(left))
    right_segments = json_path_segments(normalize_json_path(right))
    if left_segments is None or right_segments is None:
        return False
    common_length = min(len(left_segments), len(right_segments))
    return left_segments[:common_length] == right_segments[:common_length]


def _column_from_json_container(value: exp.Expression) -> exp.Column | None:
    current = value
    while isinstance(current, exp.Cast):
        current = current.this
    if isinstance(current, exp.Column):
        return current
    if isinstance(current, _JSON_EXPRESSION_TYPES):
        return _column_from_json_container(current.this)
    return None


def _path_from_expression(value: exp.Expression | None, *, dialect: str) -> str:
    if isinstance(value, exp.JSONPath):
        segments: list[str] = []
        for part in value.expressions:
            if isinstance(part, exp.JSONPathRoot):
                continue
            if isinstance(part, exp.JSONPathKey):
                key = str(part.this or "").strip()
                if not key:
                    return ""
                segments.append(key)
                continue
            if isinstance(part, exp.JSONPathSubscript):
                index = part.this
                if not isinstance(index, int) and not str(index).isdigit():
                    return ""
                segments.append(f"[{index}]")
                continue
            return ""
        return _format_json_path_segments(segments)
    if isinstance(value, exp.Literal) and value.is_string:
        return normalize_json_path(value.this, postgres=dialect == "postgres")
    return ""


def _json_node_parts(
        expression: exp.Expression,
        *,
        dialect: str,
) -> tuple[exp.Column | None, list[str], str | None]:
    if isinstance(expression, exp.Cast):
        return _json_node_parts(expression.this, dialect=dialect)
    if isinstance(expression, exp.Column):
        return expression, [], None
    if isinstance(expression, _JSON_EXPRESSION_TYPES):
        column, paths, issue = _json_node_parts(expression.this, dialect=dialect)
        path = _path_from_expression(expression.expression, dialect=dialect)
        if not path:
            return column, paths, "dynamic_path"
        return column, [*paths, path], issue
    return None, [], "unsupported_container"


def _is_json_value(expression: exp.Expression) -> bool:
    return isinstance(expression, exp.Anonymous) and expression.name.upper() == "JSON_VALUE"


def _is_nested_json_container(expression: exp.Expression) -> bool:
    parent = expression.parent
    return isinstance(parent, _JSON_EXPRESSION_TYPES) and parent.this is expression


def _nearest_select(expression: exp.Expression) -> exp.Select | None:
    current = expression.parent
    while current is not None:
        if isinstance(current, exp.Select):
            return current
        current = current.parent
    return None


def _merge_paths(paths: list[str]) -> str:
    segments: list[str] = []
    for path in paths:
        current = json_path_segments(path)
        if current is None:
            return ""
        segments.extend(current)
    return _format_json_path_segments(segments)


def extract_json_accesses(
        expression: exp.Expression,
        *,
        dialect: str,
        current_select_only: bool = False,
) -> JsonAccessExtraction:
    normalized_dialect = str(dialect or "").strip().lower()
    if normalized_dialect not in _JSON_DIALECTS:
        issue = JsonPathIssue(table_alias="", source_field="", reason="unsupported_dialect")
        return JsonAccessExtraction(accesses=(), issues=(issue,), consumed_column_ids=frozenset())

    accesses: list[JsonPathAccess] = []
    issues: list[JsonPathIssue] = []
    consumed_column_ids: set[int] = set()
    for node in expression.walk():
        if (
            current_select_only
            and isinstance(expression, exp.Select)
            and _nearest_select(node) is not expression
        ):
            continue
        if isinstance(node, _JSON_EXPRESSION_TYPES):
            if _is_nested_json_container(node):
                continue
            column, paths, issue_reason = _json_node_parts(node, dialect=normalized_dialect)
        elif _is_json_value(node):
            arguments = list(node.expressions)
            column = _column_from_json_container(arguments[0]) if arguments else None
            path = _path_from_expression(arguments[1], dialect=normalized_dialect) if len(arguments) > 1 else ""
            paths = [path] if path else []
            issue_reason = None if path else "dynamic_path"
        else:
            continue

        table_alias = str(column.table or "").strip() if column is not None else ""
        source_field = str(column.name or "").strip() if column is not None else ""
        if column is None or issue_reason:
            issues.append(JsonPathIssue(
                table_alias=table_alias,
                source_field=source_field,
                reason=issue_reason or "unsupported_container",
            ))
            continue
        json_path = _merge_paths(paths)
        if not json_path:
            issues.append(JsonPathIssue(table_alias, source_field, "dynamic_path"))
            continue
        column_ids = frozenset({id(column)})
        consumed_column_ids.update(column_ids)
        accesses.append(JsonPathAccess(
            table_alias=table_alias,
            source_field=source_field,
            json_path=json_path,
            consumed_column_ids=column_ids,
        ))

    return JsonAccessExtraction(
        accesses=tuple(accesses),
        issues=tuple(issues),
        consumed_column_ids=frozenset(consumed_column_ids),
    )


def extract_sql_json_field_pairs(sql: str, dialect: str) -> tuple[set[tuple[str, str]], list[str]]:
    normalized_dialect = str(dialect or "").strip().lower()
    if normalized_dialect not in _JSON_DIALECTS:
        return set(), ["当前数据源方言无法校验 JSON 字段映射。"]
    try:
        statement = parse_one(sql, read=normalized_dialect)
    except Exception as exc:
        return set(), [f"无法解析生成 SQL 的 JSON 字段映射：{exc}"]
    result = extract_json_accesses(statement, dialect=normalized_dialect)
    if result.issues:
        return set(), ["生成 SQL 包含无法静态确认的 JSON 字段映射。"]
    return {
        (access.source_field, access.json_path)
        for access in result.accesses
    }, []
