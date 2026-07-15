"""
脚本说明：按当前问题和 Data Skill 生成请求级事件属性 Schema，不持久化虚拟字段。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.system.crud.tracking_expression import (
    compile_tracking_json_expression,
    datasource_family,
    quote_identifier,
)
from apps.system.schemas.tenant_schema import TenantTrackingConfigDTO

EVENT_SCHEMA_PROMPT_BUDGET = 16_000

_CONTAINER_TYPES = {
    "对象",
    "对象组",
    "对象数组",
    "数组",
    "json",
    "jsonb",
    "object",
    "objectarray",
    "array",
}
_NUMBER_TYPES = {
    "int",
    "integer",
    "bigint",
    "smallint",
    "float",
    "double",
    "decimal",
    "number",
    "numeric",
    "real",
    "数值",
    "数字",
    "整数",
    "小数",
}
_BOOLEAN_TYPES = {"bool", "boolean", "布尔", "布尔值"}
_DATE_TYPES = {"date", "datetime", "timestamp", "日期", "时间", "日期时间"}


@dataclass(frozen=True)
class EventSchemaField:
    table_name: str
    event_name: str
    event_name_field: str
    field_name: str
    semantic_type: str
    source_field: str
    json_path: str
    expression: str
    comment: str | None = None


@dataclass
class EventSchemaProjection:
    fields: list[EventSchemaField] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    datasource_type: str | None = None


@dataclass(frozen=True)
class _PropertyCandidate:
    mapping_index: int
    property_index: int
    event_name: str
    item: dict[str, Any]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_type(value: Any) -> str:
    normalized = _text(value).lower().removesuffix("类型").replace("_", "").replace("-", "").replace(" ", "")
    if normalized in {item.replace("_", "") for item in _NUMBER_TYPES}:
        return "number"
    if normalized in _BOOLEAN_TYPES:
        return "boolean"
    if normalized in _DATE_TYPES:
        return "datetime"
    return "text"


def _is_container_type(value: Any) -> bool:
    normalized = _text(value).lower().removesuffix("类型").replace("_", "").replace("-", "").replace(" ", "")
    return normalized in {item.replace("_", "") for item in _CONTAINER_TYPES}


def _event_names(mapping: dict[str, Any]) -> list[str]:
    names = [
        _text(mapping.get(key))
        for key in ("event_name", "eventName", "name", "value")
    ]
    events = mapping.get("events")
    if isinstance(events, list):
        names.extend(_text(item) for item in events)
    return list(dict.fromkeys(name for name in names if name))


def _list_text(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [text] if text else []


def _is_referenced(candidates: list[str], request_text: str) -> bool:
    return any(
        len(candidate.casefold()) >= 2 and candidate.casefold() in request_text
        for candidate in candidates
        if candidate
    )


def _matched_event_names(mapping: dict[str, Any], request_text: str) -> list[str]:
    names = _event_names(mapping)
    explicitly_matched = [name for name in names if _is_referenced([name], request_text)]
    if explicitly_matched:
        return explicitly_matched
    display_candidates: list[str] = []
    for key in ("event_display_name", "eventDisplayName", "display_name", "displayName"):
        display_candidates.extend(_list_text(mapping.get(key)))
    display_candidates.extend(_list_text(mapping.get("aliases")))
    if len(names) == 1 and _is_referenced(display_candidates, request_text):
        return names
    return []


def _property_name(item: dict[str, Any]) -> str:
    for key in ("property_name", "propertyName", "field_name", "fieldName", "name"):
        value = _text(item.get(key))
        if value:
            return value
    return ""


def _property_candidates(item: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in (
        "property_name",
        "propertyName",
        "field_name",
        "fieldName",
        "name",
        "property_display_name",
        "propertyDisplayName",
        "display_name",
        "displayName",
        "description",
    ):
        candidates.extend(_list_text(item.get(key)))
    candidates.extend(_list_text(item.get("aliases")))
    source_field = _text(item.get("source_field") or item.get("sourceField"))
    json_path = _text(item.get("json_path") or item.get("jsonPath"))
    if source_field and json_path:
        candidates.append(f"{source_field}.{json_path.removeprefix('$.')}")
    return list(dict.fromkeys(candidates))


def _physical_field_names(physical_schema: dict[str, Any], table_name: str) -> set[str] | None:
    if table_name not in physical_schema:
        return None
    table = physical_schema.get(table_name)
    if isinstance(table, set):
        return {_text(item) for item in table if _text(item)}
    fields = getattr(table, "fields", None)
    if fields is None:
        return set()
    return {
        _text(getattr(item, "field_name", None))
        for item in fields
        if _text(getattr(item, "field_name", None))
    }


def _selected_candidates(
    config: TenantTrackingConfigDTO,
    request_text: str,
) -> tuple[list[_PropertyCandidate], list[str]]:
    selected: list[_PropertyCandidate] = []
    unresolved: dict[tuple[str, str, str], list[_PropertyCandidate]] = {}
    warnings: list[str] = []

    for mapping_index, mapping in enumerate(getattr(config, "event_name_mappings", None) or []):
        if not isinstance(mapping, dict):
            continue
        event_names = _event_names(mapping)
        matched_events = _matched_event_names(mapping, request_text)
        properties = mapping.get("properties")
        if not event_names or not isinstance(properties, list):
            continue
        for property_index, item in enumerate(properties):
            if not isinstance(item, dict) or not _is_referenced(_property_candidates(item), request_text):
                continue
            candidates = [
                _PropertyCandidate(mapping_index, property_index, event_name, item)
                for event_name in (matched_events or event_names)
            ]
            if matched_events:
                selected.extend(candidates)
                continue
            identity = (
                _property_name(item).casefold(),
                _text(item.get("source_field") or item.get("sourceField")).casefold(),
                _text(item.get("json_path") or item.get("jsonPath")).casefold(),
            )
            unresolved.setdefault(identity, []).extend(candidates)

    for candidates in unresolved.values():
        unique_events = {(item.mapping_index, item.event_name) for item in candidates}
        if len(unique_events) == 1:
            selected.append(candidates[0])
            continue
        field_name = _property_name(candidates[0].item)
        event_names = "、".join(dict.fromkeys(item.event_name for item in candidates))
        warnings.append(f"事件属性 {field_name} 同时属于 {event_names}，无法确定所属事件，已停止投影。")

    selected.sort(key=lambda item: (item.mapping_index, item.property_index, item.event_name))
    return selected, warnings


def project_event_schema_fields(
    config: TenantTrackingConfigDTO,
    physical_schema: dict[str, Any],
    datasource_type: str | None,
    question: str | None,
    data_skill_text: str | None,
) -> EventSchemaProjection:
    """选择、验证并编译本次 SQL 请求明确引用的事件属性。"""
    projection = EventSchemaProjection(datasource_type=datasource_type)
    if not getattr(config, "enabled", False):
        return projection

    request_text = "\n".join(
        part.casefold().strip()
        for part in (question or "", data_skill_text or "")
        if part and part.strip()
    )
    if not request_text:
        return projection

    selected, warnings = _selected_candidates(config, request_text)
    projection.warnings.extend(warnings)
    if not selected:
        return projection

    table_name = _text(getattr(config, "default_event_table", None))
    event_name_field = _text(getattr(config, "default_event_name_field", None))
    if not table_name or not event_name_field:
        projection.warnings.append("事件属性投影缺少默认事件表或默认事件名字段，已停止投影。")
        return projection

    physical_fields = _physical_field_names(physical_schema, table_name)
    if physical_fields is None:
        projection.warnings.append(f"默认事件表 {table_name} 不在当前数据源 schema 中，已停止事件属性投影。")
        return projection
    if event_name_field not in physical_fields:
        projection.warnings.append(
            f"默认事件名字段 {table_name}.{event_name_field} 不在当前数据源 schema 中，已停止事件属性投影。"
        )
        return projection

    seen: set[tuple[str, str, str, str]] = set()
    used_chars = 0
    for candidate in selected:
        item = candidate.item
        field_name = _property_name(item)
        source_field = _text(item.get("source_field") or item.get("sourceField"))
        json_path = _text(item.get("json_path") or item.get("jsonPath"))
        property_type = _text(
            item.get("property_type")
            or item.get("propertyType")
            or item.get("semantic_type")
            or item.get("semanticType")
            or item.get("field_type")
            or item.get("fieldType")
            or item.get("type")
        )
        label = f"{candidate.event_name}.{field_name}"
        if not field_name or not source_field or not json_path:
            projection.warnings.append(f"事件属性 {label} 缺少字段名、来源字段或 JSONPath，已停止投影。")
            continue
        if _is_container_type(property_type):
            projection.warnings.append(f"事件属性 {label} 是容器类型，当前不会自动展开，已停止投影。")
            continue
        if source_field not in physical_fields:
            projection.warnings.append(
                f"事件属性 {label} 的来源字段 {source_field} 不在当前数据源 schema 中，已停止投影。"
            )
            continue
        semantic_type = _normalized_type(property_type)
        expression = compile_tracking_json_expression(
            table_name,
            source_field,
            json_path,
            semantic_type,
            datasource_type,
        )
        if not expression:
            projection.warnings.append(f"事件属性 {label} 无法按当前数据源方言编译，已停止投影。")
            continue
        key = (candidate.event_name, field_name, source_field, json_path)
        if key in seen:
            continue
        field_item = EventSchemaField(
            table_name=table_name,
            event_name=candidate.event_name,
            event_name_field=event_name_field,
            field_name=field_name,
            semantic_type=semantic_type,
            source_field=source_field,
            json_path=json_path,
            expression=expression,
            comment=_text(
                item.get("property_display_name")
                or item.get("propertyDisplayName")
                or item.get("display_name")
                or item.get("displayName")
                or item.get("description")
            )
            or None,
        )
        estimated_chars = len(_format_field_line(field_item)) + 1
        if used_chars + estimated_chars > EVENT_SCHEMA_PROMPT_BUDGET:
            projection.fields.clear()
            projection.warnings.append("请求涉及的事件属性超过 16000 字符预算，未静默截断必需字段。")
            return projection
        seen.add(key)
        projection.fields.append(field_item)
        used_chars += estimated_chars
    return projection


def _format_field_line(item: EventSchemaField) -> str:
    parts = [
        f"({item.field_name}:{item.semantic_type}",
        f"source={item.source_field}",
        f"json_path={item.json_path}",
        f"expression={item.expression}",
    ]
    if item.comment:
        parts.append(f"comment={item.comment}")
    return ", ".join(parts) + ")"


def format_event_schema_projection(projection: EventSchemaProjection) -> str:
    """把请求级虚拟字段按事件边界格式化为可追加到 m-schema 的文本。"""
    if not projection.fields:
        return ""
    family = datasource_family(projection.datasource_type)
    groups: dict[tuple[str, str, str], list[EventSchemaField]] = {}
    for item in projection.fields:
        groups.setdefault((item.table_name, item.event_name_field, item.event_name), []).append(item)

    lines = [
        "【Request event attribute schema】",
        "以下字段是本次请求的事件级虚拟字段。只能使用给出的 expression，且使用它的查询块必须包含对应 Required predicate。",
    ]
    for (table_name, event_name_field, event_name), fields in groups.items():
        table_ref = f"{quote_identifier(table_name, family)}.{quote_identifier(event_name_field, family)}"
        event_literal = event_name.replace("'", "''")
        lines.extend(
            [
                f"# Table: {table_name}",
                f"# Event: {event_name}",
                f"# Required predicate: {table_ref} = '{event_literal}'",
                "[",
                ",\n".join(_format_field_line(item) for item in fields),
                "]",
            ]
        )
    return "\n".join(lines) + "\n"


__all__ = [
    "EventSchemaField",
    "EventSchemaProjection",
    "format_event_schema_projection",
    "project_event_schema_fields",
]
