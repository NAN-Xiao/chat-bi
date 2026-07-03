"""
脚本说明：这个脚本负责数据字典 Excel 的导入导出，把运维可维护的表格转换成工作空间语义配置。
"""
from __future__ import annotations

import io
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from apps.system.schemas.tenant_schema import (
    TenantTrackingConfigDTO,
    TenantTrackingConfigEditor,
    TenantTrackingFieldBase,
    TenantTrackingImportSummary,
    TenantTrackingTableBase,
)

GENERIC_PROFILE = "shuzhi_generic_v1"
THINKINGDATA_LIKE_PROFILE = "thinkingdata_like_v1"

INFO_SHEET = "_说明"
TABLE_MAP_SHEET = "_表映射"
ENUM_SHEET = "_枚举与值域"
SQL_RULE_SHEET = "_SQL规则"
COMPETITOR_EVENT_SHEET = "#事件数据"
COMPETITOR_COMMON_PROPERTY_SHEET = "#公共事件属性"
COMPETITOR_USER_PROPERTY_SHEET = "#用户数据"

SYSTEM_SHEETS = {
    INFO_SHEET,
    TABLE_MAP_SHEET,
    ENUM_SHEET,
    SQL_RULE_SHEET,
    "接入必知",
    "#用户ID体系",
    COMPETITOR_EVENT_SHEET,
    COMPETITOR_COMMON_PROPERTY_SHEET,
    COMPETITOR_USER_PROPERTY_SHEET,
    "数据类型设计原则",
    "公共事件属性设置方式",
    "多端接入注意点",
    "多用户id体系的埋点建议",
}

BUSINESS_COLUMNS = [
    "row_type",
    "event_name",
    "event_display_name",
    "event_category",
    "collect_side",
    "field_view",
    "field_name",
    "field_display_name",
    "field_type",
    "field_role",
    "semantic_type",
    "source_field",
    "json_path",
    "expression",
    "required",
    "enum_values",
    "example_values",
    "description",
    "ai_notes",
]

TABLE_MAP_COLUMNS = [
    "sheet_name",
    "table_name",
    "table_display_name",
    "table_role",
    "subject_field",
    "event_name_field",
    "event_time_field",
    "partition_field",
    "table_comment",
    "ai_notes",
]

ENUM_COLUMNS = [
    "object_type",
    "object_name",
    "value",
    "display_name",
    "description",
    "deprecated",
]

SQL_RULE_COLUMNS = [
    "rule_name",
    "scope",
    "rule_text",
    "priority",
]

EXPORT_COLUMN_LABELS = {
    "row_type": "行类型",
    "event_name": "事件名",
    "event_display_name": "事件显示名",
    "event_category": "事件分类",
    "collect_side": "采集端",
    "field_view": "字段视图",
    "field_name": "字段名",
    "field_display_name": "字段显示名",
    "field_type": "字段类型",
    "field_role": "字段角色",
    "semantic_type": "语义类型",
    "source_field": "来源字段",
    "json_path": "JSON 路径",
    "expression": "字段表达式",
    "required": "是否必填",
    "enum_values": "枚举值",
    "example_values": "示例值",
    "description": "说明",
    "ai_notes": "AI 说明",
    "sheet_name": "工作表名",
    "table_name": "物理表名",
    "table_display_name": "表显示名",
    "table_role": "表角色",
    "subject_field": "主体字段",
    "event_name_field": "事件名字段",
    "event_time_field": "事件时间字段",
    "partition_field": "分区字段",
    "table_comment": "表说明",
    "object_type": "对象类型",
    "object_name": "对象名",
    "value": "值",
    "display_name": "显示名",
    "deprecated": "是否废弃",
    "rule_name": "规则名",
    "scope": "适用范围",
    "rule_text": "规则内容",
    "priority": "优先级",
}

TYPE_ALIASES = {
    "text": "text",
    "string": "text",
    "str": "text",
    "varchar": "text",
    "char": "text",
    "文本": "text",
    "字符串": "text",
    "字符": "text",
    "number": "number",
    "numeric": "number",
    "decimal": "number",
    "double": "number",
    "float": "number",
    "int": "number",
    "integer": "number",
    "long": "number",
    "bigint": "number",
    "数值": "number",
    "数字": "number",
    "整数": "number",
    "小数": "number",
    "datetime": "datetime",
    "timestamp": "datetime",
    "date": "datetime",
    "time": "datetime",
    "时间": "datetime",
    "日期": "datetime",
    "boolean": "boolean",
    "bool": "boolean",
    "布尔": "boolean",
    "array": "array",
    "list": "array",
    "列表": "array",
    "object": "object",
    "对象": "object",
    "json": "json",
    "object_array": "object_array",
    "objectarray": "object_array",
    "对象组": "object_array",
    "对象数组": "object_array",
}

HEADER_ALIASES = {
    "rowtype": "row_type",
    "行类型": "row_type",
    "类型": "row_type",
    "sheetname": "sheet_name",
    "sheet": "sheet_name",
    "工作表名": "sheet_name",
    "表单名": "sheet_name",
    "tablename": "table_name",
    "sourcetable": "source_table",
    "source_table": "source_table",
    "物理表名": "table_name",
    "实际表名": "table_name",
    "表名": "table_name",
    "来源表": "source_table",
    "所在物理表": "source_table",
    "tabledisplayname": "table_display_name",
    "tablealias": "table_display_name",
    "表显示名": "table_display_name",
    "表展示名": "table_display_name",
    "tablecomment": "table_comment",
    "表说明": "table_comment",
    "tablerole": "table_role",
    "表角色": "table_role",
    "subjectfield": "subject_field",
    "主体字段": "subject_field",
    "eventnamefield": "event_name_field",
    "事件名字段": "event_name_field",
    "eventtimefield": "event_time_field",
    "事件时间字段": "event_time_field",
    "partitionfield": "partition_field",
    "分区字段": "partition_field",
    "eventname": "event_name",
    "事件名": "event_name",
    "埋点名": "event_name",
    "eventdisplayname": "event_display_name",
    "事件显示名": "event_display_name",
    "事件展示名": "event_display_name",
    "eventdescription": "event_description",
    "事件说明": "event_description",
    "eventcategory": "event_category",
    "事件分类": "event_category",
    "事件标签": "event_category",
    "collectside": "collect_side",
    "采集端": "collect_side",
    "fieldview": "field_view",
    "view": "field_view",
    "字段视图": "field_view",
    "字段分组": "field_view",
    "json视图": "field_view",
    "fieldname": "field_name",
    "字段名": "field_name",
    "fielddisplayname": "field_display_name",
    "字段显示名": "field_display_name",
    "字段展示名": "field_display_name",
    "fieldtype": "field_type",
    "字段类型": "field_type",
    "fieldrole": "field_role",
    "字段角色": "field_role",
    "semantictype": "semantic_type",
    "语义类型": "semantic_type",
    "sourcefield": "source_field",
    "来源字段": "source_field",
    "源字段": "source_field",
    "jsonpath": "json_path",
    "json路径": "json_path",
    "expression": "expression",
    "sql表达式": "expression",
    "字段表达式": "expression",
    "required": "required",
    "是否必填": "required",
    "必填": "required",
    "enumvalues": "enum_values",
    "枚举值": "enum_values",
    "value_mappings": "enum_values",
    "examplevalues": "example_values",
    "示例值": "example_values",
    "description": "description",
    "fieldcomment": "description",
    "字段说明": "description",
    "属性说明": "description",
    "ainotes": "ai_notes",
    "ai说明": "ai_notes",
    "llm说明": "ai_notes",
    "propertyname": "property_name",
    "属性名": "property_name",
    "propertydisplayname": "property_display_name",
    "属性显示名": "property_display_name",
    "属性展示名": "property_display_name",
    "propertytype": "property_type",
    "属性类型": "property_type",
    "propertycategory": "property_category",
    "属性标签": "property_category",
    "updatemode": "update_mode",
    "更新方式": "update_mode",
    "subjecttype": "subject_type",
    "主体类型": "subject_type",
    "ruletitle": "rule_name",
    "rulename": "rule_name",
    "规则名": "rule_name",
    "scope": "scope",
    "范围": "scope",
    "ruletext": "rule_text",
    "规则内容": "rule_text",
    "priority": "priority",
    "优先级": "priority",
    "objecttype": "object_type",
    "对象类型": "object_type",
    "objectname": "object_name",
    "对象名": "object_name",
    "value": "value",
    "值": "value",
    "displayname": "display_name",
    "显示名": "display_name",
    "deprecated": "deprecated",
    "是否废弃": "deprecated",
}


@dataclass
class PhysicalFieldInfo:
    field_name: str
    field_type: str = ""
    field_comment: str = ""
    custom_comment: str = ""
    field_index: int = 0


@dataclass
class PhysicalTableInfo:
    table_name: str
    table_comment: str = ""
    custom_comment: str = ""
    fields: list[PhysicalFieldInfo] = field(default_factory=list)


@dataclass
class ParsedTrackingConfig:
    editor: TenantTrackingConfigEditor
    profile: str
    warnings: list[str] = field(default_factory=list)
    skipped_rows: int = 0


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _first_text(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _header_key(value: Any) -> str:
    text = _text(value).lower()
    if not text:
        return ""
    text = re.sub(r"[\r\n\t ]+", "", text)
    text = re.sub(r"[（(][^）)]*(?:必填|required)[^）)]*[）)]", "", text, flags=re.I)
    text = text.replace("_", "")
    text = re.sub(r"[:：/\\\-—–,，.。;；#]+", "", text)
    return text


def _canonical_header(value: Any) -> str:
    key = _header_key(value)
    return HEADER_ALIASES.get(key, key)


def _read_sheet_rows(excel: pd.ExcelFile, sheet_name: str) -> tuple[list[dict[str, Any]], int]:
    raw = pd.read_excel(excel, sheet_name=sheet_name, header=None, dtype=object).fillna("")
    if raw.empty:
        return [], 0

    header_index = None
    for index, row in raw.iterrows():
        headers = [_canonical_header(value) for value in row.tolist()]
        known_count = sum(1 for value in headers if value in HEADER_ALIASES.values() or value in BUSINESS_COLUMNS)
        if known_count >= 2:
            header_index = int(index)
            break

    if header_index is None:
        return [], len(raw.index)

    canonical_headers: list[str] = []
    used: dict[str, int] = {}
    for value in raw.iloc[header_index].tolist():
        header = _canonical_header(value)
        if not header:
            canonical_headers.append("")
            continue
        count = used.get(header, 0) + 1
        used[header] = count
        canonical_headers.append(header if count == 1 else f"{header}_{count}")

    rows: list[dict[str, Any]] = []
    skipped = 0
    for _, raw_row in raw.iloc[header_index + 1 :].iterrows():
        row: dict[str, Any] = {}
        has_value = False
        for col_index, header in enumerate(canonical_headers):
            if not header:
                continue
            value = raw_row.iloc[col_index]
            row[header] = value
            if _text(value):
                has_value = True
        if has_value:
            rows.append(row)
        else:
            skipped += 1
    return rows, skipped


def _normalize_type(value: Any) -> str:
    text = _text(value).lower().replace(" ", "_").replace("-", "_")
    if not text:
        return ""
    compact = text.replace("_", "")
    if text in TYPE_ALIASES:
        return TYPE_ALIASES[text]
    if compact in TYPE_ALIASES:
        return TYPE_ALIASES[compact]
    for token, normalized in TYPE_ALIASES.items():
        if token and token in text:
            return normalized
    return text[:64]


def _semantic_type(value: str) -> str:
    normalized = _normalize_type(value)
    if normalized == "datetime":
        return "date"
    if normalized in {"object", "object_array", "json"}:
        return "json"
    if normalized == "boolean":
        return "boolean_flag"
    return normalized or "text"


def _parse_bool(value: Any) -> bool:
    text = _text(value).lower()
    return text in {"1", "y", "yes", "true", "t", "是", "对", "必填", "required"}


def _split_list(value: Any) -> list[str]:
    text = _text(value)
    if not text:
        return []
    return [
        item.strip()
        for item in re.split(r"[\n\r,，;；]+", text)
        if item and item.strip()
    ]


def _json_path_from_field_name(field_name: str) -> tuple[str, str]:
    text = _text(field_name)
    if "." not in text:
        return "", ""
    source, child = text.split(".", 1)
    return source.strip(), f"$.{child.strip()}" if child.strip() else ""


def _source_from_field_view(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    text = re.sub(r"^(?:json|view)[:：]\s*", "", text, flags=re.I).strip()
    text = re.sub(r"\s*(?:view|视图)$", "", text, flags=re.I).strip()
    return text


def _normalize_json_path(value: str) -> str:
    text = _text(value)
    if not text:
        return ""
    if text.startswith("$"):
        return text
    return f"$.{text.lstrip('.')}"


def _json_path_segments(json_path: str) -> list[str]:
    text = _normalize_json_path(json_path)
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


def _json_child_name(source_field: str, field_name: str, json_path: str | None = None) -> str:
    source = _text(source_field)
    field_text = _text(field_name)
    if source and field_text.startswith(f"{source}."):
        return field_text[len(source) + 1 :]
    path_segments = _json_path_segments(json_path or "")
    if path_segments:
        return ".".join(path_segments)
    return field_text


def _datasource_family(datasource_type: str | None) -> str:
    text = _text(datasource_type).lower()
    if text in {"mysql", "mariadb"} or "mysql" in text:
        return "mysql"
    if text in {"pg", "postgres", "postgresql", "kingbase", "redshift", "excel"} or "postgres" in text:
        return "postgres"
    if text in {"clickhouse", "ck"} or "clickhouse" in text:
        return "clickhouse"
    return ""


def _quote_identifier(identifier: str, family: str) -> str:
    quote = '"' if family == "postgres" else "`"
    escaped = identifier.replace(quote, quote + quote)
    return f"{quote}{escaped}{quote}"


def _qualified_field(table_name: str, field_name: str, family: str) -> str:
    return f"{_quote_identifier(table_name, family)}.{_quote_identifier(field_name, family)}"


def _json_expression(
    table_name: str,
    source_field: str,
    json_path: str,
    semantic_type: str,
    datasource_type: str | None,
) -> str:
    family = _datasource_family(datasource_type)
    if not family or not table_name or not source_field or not json_path:
        return ""

    column = _qualified_field(table_name, source_field, family)
    path = _normalize_json_path(json_path)
    semantic = _text(semantic_type).lower()
    if family == "postgres":
        segments = _json_path_segments(path)
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


def _field_role(row_type: str, semantic_type: str, source_field: str, json_path: str, configured: str) -> str:
    if configured:
        return configured[:64]
    if row_type == "json_view":
        return "dimension_json"
    if source_field and json_path:
        return "json_path_metric" if semantic_type == "number" else "json_path_dimension"
    return ""


def _table_base(item: Any) -> TenantTrackingTableBase:
    return TenantTrackingTableBase(
        table_name=_text(getattr(item, "table_name", None) if not isinstance(item, dict) else item.get("table_name")),
        table_comment=_text(getattr(item, "table_comment", None) if not isinstance(item, dict) else item.get("table_comment")) or None,
        table_role=_text(getattr(item, "table_role", None) if not isinstance(item, dict) else item.get("table_role")) or None,
        aliases=list(getattr(item, "aliases", []) if not isinstance(item, dict) else item.get("aliases", []) or []),
        ai_notes=_text(getattr(item, "ai_notes", None) if not isinstance(item, dict) else item.get("ai_notes")) or None,
    )


def _field_base(item: Any) -> TenantTrackingFieldBase:
    return TenantTrackingFieldBase(
        table_name=_text(getattr(item, "table_name", None) if not isinstance(item, dict) else item.get("table_name")),
        field_name=_text(getattr(item, "field_name", None) if not isinstance(item, dict) else item.get("field_name")),
        field_comment=_text(getattr(item, "field_comment", None) if not isinstance(item, dict) else item.get("field_comment")) or None,
        field_role=_text(getattr(item, "field_role", None) if not isinstance(item, dict) else item.get("field_role")) or None,
        semantic_type=_text(getattr(item, "semantic_type", None) if not isinstance(item, dict) else item.get("semantic_type")) or None,
        source_field=_text(getattr(item, "source_field", None) if not isinstance(item, dict) else item.get("source_field")) or None,
        json_path=_text(getattr(item, "json_path", None) if not isinstance(item, dict) else item.get("json_path")) or None,
        aliases=list(getattr(item, "aliases", []) if not isinstance(item, dict) else item.get("aliases", []) or []),
        value_mappings=getattr(item, "value_mappings", None) if not isinstance(item, dict) else item.get("value_mappings"),
        expression=_text(getattr(item, "expression", None) if not isinstance(item, dict) else item.get("expression")) or None,
        required=bool(getattr(item, "required", False) if not isinstance(item, dict) else item.get("required", False)),
        example_values=list(getattr(item, "example_values", []) if not isinstance(item, dict) else item.get("example_values", []) or []),
        ai_notes=_text(getattr(item, "ai_notes", None) if not isinstance(item, dict) else item.get("ai_notes")) or None,
    )


def _editor_from_existing(config: TenantTrackingConfigDTO) -> TenantTrackingConfigEditor:
    return TenantTrackingConfigEditor(
        enabled=config.enabled,
        default_event_table=config.default_event_table,
        default_subject_field=config.default_subject_field,
        default_event_name_field=config.default_event_name_field,
        default_event_time_field=config.default_event_time_field,
        field_role_mappings=list(config.field_role_mappings or []),
        event_name_mappings=list(config.event_name_mappings or []),
        sql_rules=config.sql_rules,
        notes=config.notes,
        tables=[_table_base(item) for item in config.tables or []],
        fields=[_field_base(item) for item in config.fields or []],
    )


def _merge_text(old: str | None, new: str | None) -> str | None:
    return _text(new) or (_text(old) or None)


def _merge_list(old: Iterable[Any] | None, new: Iterable[Any] | None) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in list(old or []) + list(new or []):
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _merge_event_mappings(old: list[Any], new: list[Any]) -> list[Any]:
    result: dict[str, dict[str, Any]] = {}
    ordered_names: list[str] = []

    def event_key(item: Any) -> str:
        if isinstance(item, dict):
            return _first_text(item.get("event_name"), item.get("name"), item.get("value"))
        return ""

    def as_dict(item: Any) -> dict[str, Any]:
        return dict(item) if isinstance(item, dict) else {"event_name": _text(item)}

    for source in (old or []) + (new or []):
        name = event_key(source)
        if not name:
            continue
        current = result.setdefault(name, {"event_name": name})
        if name not in ordered_names:
            ordered_names.append(name)
        incoming = as_dict(source)
        for key, value in incoming.items():
            if key == "properties" and isinstance(value, list):
                current_props = {
                    _first_text(prop.get("property_name"), prop.get("field_name"), prop.get("name")): dict(prop)
                    for prop in current.get("properties", [])
                    if isinstance(prop, dict)
                }
                prop_order = [
                    _first_text(prop.get("property_name"), prop.get("field_name"), prop.get("name"))
                    for prop in current.get("properties", [])
                    if isinstance(prop, dict)
                ]
                for prop in value:
                    if not isinstance(prop, dict):
                        continue
                    prop_name = _first_text(prop.get("property_name"), prop.get("field_name"), prop.get("name"))
                    if not prop_name:
                        continue
                    if prop_name not in prop_order:
                        prop_order.append(prop_name)
                    merged = current_props.setdefault(prop_name, {"property_name": prop_name})
                    for prop_key, prop_value in prop.items():
                        if _text(prop_value) or prop_key not in merged:
                            merged[prop_key] = prop_value
                current["properties"] = [current_props[name] for name in prop_order if name in current_props]
            elif _text(value) or key not in current:
                current[key] = value
    return [result[name] for name in ordered_names]


def _merge_tracking_config(existing: TenantTrackingConfigDTO, imported: TenantTrackingConfigEditor) -> TenantTrackingConfigEditor:
    base = _editor_from_existing(existing)
    base.enabled = imported.enabled if imported.enabled is not None else base.enabled
    base.default_event_table = _merge_text(base.default_event_table, imported.default_event_table)
    base.default_subject_field = _merge_text(base.default_subject_field, imported.default_subject_field)
    base.default_event_name_field = _merge_text(base.default_event_name_field, imported.default_event_name_field)
    base.default_event_time_field = _merge_text(base.default_event_time_field, imported.default_event_time_field)
    base.field_role_mappings = _merge_list(base.field_role_mappings, imported.field_role_mappings)
    base.event_name_mappings = _merge_event_mappings(base.event_name_mappings, imported.event_name_mappings)
    base.sql_rules = _merge_text(base.sql_rules, imported.sql_rules)
    base.notes = _merge_text(base.notes, imported.notes)

    table_by_name = {table.table_name: table for table in base.tables if table.table_name}
    for table in imported.tables or []:
        if not table.table_name:
            continue
        current = table_by_name.get(table.table_name)
        if current is None:
            table_by_name[table.table_name] = table
            continue
        current.table_comment = _merge_text(current.table_comment, table.table_comment)
        current.table_role = _merge_text(current.table_role, table.table_role)
        current.aliases = _merge_list(current.aliases, table.aliases)
        current.ai_notes = _merge_text(current.ai_notes, table.ai_notes)
    base.tables = list(table_by_name.values())

    field_by_key = {
        (field.table_name, field.field_name): field
        for field in base.fields
        if field.table_name and field.field_name
    }
    for field_item in imported.fields or []:
        if not field_item.table_name or not field_item.field_name:
            continue
        key = (field_item.table_name, field_item.field_name)
        current = field_by_key.get(key)
        if current is None:
            field_by_key[key] = field_item
            continue
        current.field_comment = _merge_text(current.field_comment, field_item.field_comment)
        current.field_role = _merge_text(current.field_role, field_item.field_role)
        current.semantic_type = _merge_text(current.semantic_type, field_item.semantic_type)
        current.source_field = _merge_text(current.source_field, field_item.source_field)
        current.json_path = _merge_text(current.json_path, field_item.json_path)
        current.aliases = _merge_list(current.aliases, field_item.aliases)
        current.value_mappings = field_item.value_mappings if field_item.value_mappings not in (None, [], {}) else current.value_mappings
        current.expression = _merge_text(current.expression, field_item.expression)
        current.required = bool(current.required or field_item.required)
        current.example_values = _merge_list(current.example_values, field_item.example_values)
        current.ai_notes = _merge_text(current.ai_notes, field_item.ai_notes)
    base.fields = list(field_by_key.values())
    return base


def _physical_field_names(physical_schema: dict[str, PhysicalTableInfo], table_name: str) -> set[str]:
    table = physical_schema.get(table_name)
    if not table:
        return set()
    return {field_info.field_name for field_info in table.fields if field_info.field_name}


def _add_warning(warnings: list[str], text: str) -> None:
    if text and text not in warnings:
        warnings.append(text)


def _resolve_event_table(existing: TenantTrackingConfigDTO, physical_schema: dict[str, PhysicalTableInfo], warnings: list[str]) -> str:
    if existing.default_event_table:
        return existing.default_event_table
    for table in existing.tables or []:
        role = _text(table.table_role).lower()
        if role in {"event", "event_fact", "fact_event", "fact_events"}:
            return table.table_name
    if "event" in physical_schema:
        _add_warning(warnings, "未配置默认事件表，已使用当前数据源中的 event 表；建议在 _表映射 中显式维护。")
        return "event"
    raise ValueError("Excel 包含事件数据，但当前工作空间没有默认事件表；请先在配置或 _表映射 中指定事件所在物理表。")


def _resolve_subject_table(existing: TenantTrackingConfigDTO, physical_schema: dict[str, PhysicalTableInfo], warnings: list[str]) -> str:
    for table in existing.tables or []:
        role = _text(table.table_role).lower()
        if role in {"subject", "subject_profile", "user", "profile", "profile_table", "user_profile"}:
            return table.table_name
    for candidate in ("user", "users", "profile", "subject_profile"):
        if candidate in physical_schema:
            _add_warning(warnings, f"未配置主体属性表，已使用当前数据源中的 {candidate} 表；建议在 _表映射 中显式维护。")
            return candidate
    raise ValueError("Excel 包含用户/主体属性，但当前工作空间没有主体属性表；请在 _表映射 中指定 source_table。")


def _table_item(
    table_name: str,
    *,
    table_comment: str = "",
    table_role: str = "",
    alias: str = "",
    ai_notes: str = "",
) -> TenantTrackingTableBase:
    aliases = [alias] if alias and alias != table_name else []
    return TenantTrackingTableBase(
        table_name=table_name,
        table_comment=table_comment or None,
        table_role=table_role or None,
        aliases=aliases,
        ai_notes=ai_notes or None,
    )


def _field_item(
    row: dict[str, Any],
    table_name: str,
    *,
    row_type: str,
    datasource_type: str | None,
    warnings: list[str],
    physical_schema: dict[str, PhysicalTableInfo],
) -> TenantTrackingFieldBase | None:
    raw_field_name = _first_text(row.get("field_name"), row.get("property_name"))
    field_name = raw_field_name
    if not table_name or not field_name:
        return None

    display_name = _first_text(row.get("field_display_name"), row.get("property_display_name"))
    field_type = _first_text(row.get("field_type"), row.get("property_type"))
    semantic_type = _first_text(row.get("semantic_type"), _semantic_type(field_type))
    view_source = _source_from_field_view(row.get("field_view"))
    source_field = _text(row.get("source_field")) or view_source
    json_path = _normalize_json_path(_text(row.get("json_path")))
    inferred_source, inferred_path = _json_path_from_field_name(raw_field_name)
    if not source_field and inferred_source:
        source_field = inferred_source
    if not json_path and inferred_path:
        json_path = inferred_path
    elif not json_path and source_field and row_type not in {"physical_field", "json_view"} and "." not in raw_field_name:
        json_path = _normalize_json_path(raw_field_name)
    if source_field and json_path and row_type not in {"physical_field", "json_view"} and "." not in raw_field_name:
        field_name = f"{source_field}.{raw_field_name}"
    if row_type == "json_view" and not source_field:
        source_field = field_name

    physical_names = _physical_field_names(physical_schema, table_name)
    if physical_names and source_field and source_field not in physical_names:
        _add_warning(
            warnings,
            f"{table_name}.{field_name} 的来源字段 {source_field} 不在当前物理表字段中，已跳过该字典字段。",
        )
        return None
    if physical_names and not source_field and field_name not in physical_names:
        _add_warning(
            warnings,
            f"{table_name}.{field_name} 未配置来源字段，且不是当前物理字段；如它来自 JSON，请补充 source_field/json_path，已跳过该字典字段。",
        )
        return None

    expression = _text(row.get("expression"))
    if not expression and source_field and json_path:
        expression = _json_expression(table_name, source_field, json_path, semantic_type, datasource_type)
        if not expression:
            _add_warning(
                warnings,
                f"{table_name}.{field_name} 已配置 JSON 路径，但未能按当前数据源生成 SQL 表达式；请在 Excel expression 列补充。",
            )

    aliases = [display_name] if display_name and display_name != field_name else []
    return TenantTrackingFieldBase(
        table_name=table_name,
        field_name=field_name,
        field_comment=_first_text(row.get("description"), row.get("event_description")) or None,
        field_role=_field_role(row_type, semantic_type, source_field, json_path, _text(row.get("field_role"))) or None,
        semantic_type=semantic_type or None,
        source_field=source_field or None,
        json_path=json_path or None,
        aliases=aliases,
        value_mappings=_split_list(row.get("enum_values")) or None,
        expression=expression or None,
        required=_parse_bool(row.get("required")),
        example_values=_split_list(row.get("example_values")),
        ai_notes=_text(row.get("ai_notes")) or None,
    )


def _event_mapping(row: dict[str, Any]) -> dict[str, Any] | None:
    event_name = _text(row.get("event_name"))
    if not event_name:
        return None
    result = {
        "event_name": event_name,
        "event_display_name": _text(row.get("event_display_name")),
        "event_category": _text(row.get("event_category")),
        "collect_side": _text(row.get("collect_side")),
        "description": _first_text(row.get("event_description"), row.get("description")),
        "ai_notes": _text(row.get("ai_notes")),
    }
    return {key: value for key, value in result.items() if value}


def _event_property(row: dict[str, Any]) -> dict[str, Any] | None:
    raw_name = _first_text(row.get("field_name"), row.get("property_name"))
    name = raw_name
    if not name:
        return None
    view_source = _source_from_field_view(row.get("field_view"))
    source_field = _text(row.get("source_field")) or view_source
    json_path = _normalize_json_path(_text(row.get("json_path")))
    inferred_source, inferred_path = _json_path_from_field_name(raw_name)
    if not source_field and inferred_source:
        source_field = inferred_source
    if not json_path and inferred_path:
        json_path = inferred_path
    elif not json_path and source_field and "." not in raw_name:
        json_path = _normalize_json_path(raw_name)
    if source_field and json_path and "." not in raw_name:
        name = f"{source_field}.{raw_name}"
    result = {
        "property_name": name,
        "property_display_name": _first_text(row.get("field_display_name"), row.get("property_display_name")),
        "property_type": _first_text(row.get("field_type"), row.get("property_type")),
        "source_field": source_field,
        "json_path": json_path,
        "description": _text(row.get("description")),
    }
    return {key: value for key, value in result.items() if value}


def _append_event_mapping(event_mappings: list[dict[str, Any]], event: dict[str, Any], prop: dict[str, Any] | None = None) -> None:
    event_name = event.get("event_name")
    if not event_name:
        return
    for existing in event_mappings:
        if existing.get("event_name") == event_name:
            for key, value in event.items():
                if value:
                    existing[key] = value
            if prop:
                props = existing.setdefault("properties", [])
                if isinstance(props, list) and not any(item.get("property_name") == prop.get("property_name") for item in props if isinstance(item, dict)):
                    props.append(prop)
            return
    new_event = dict(event)
    if prop:
        new_event["properties"] = [prop]
    event_mappings.append(new_event)


def _parse_table_map(
    rows: list[dict[str, Any]],
    editor: TenantTrackingConfigEditor,
    warnings: list[str],
) -> dict[str, str]:
    sheet_to_table: dict[str, str] = {}
    for row in rows:
        table_name = _text(row.get("table_name")) or _text(row.get("source_table"))
        if not table_name:
            continue
        sheet_name = _text(row.get("sheet_name")) or table_name
        sheet_to_table[sheet_name] = table_name
        editor.tables.append(
            _table_item(
                table_name,
                table_comment=_text(row.get("table_comment")),
                table_role=_text(row.get("table_role")),
                alias=_text(row.get("table_display_name")),
                ai_notes=_text(row.get("ai_notes")),
            )
        )
        if _text(row.get("event_name_field")) and not editor.default_event_table:
            editor.default_event_table = table_name
            editor.default_event_name_field = _text(row.get("event_name_field"))
            editor.default_event_time_field = _text(row.get("event_time_field")) or editor.default_event_time_field
            editor.default_subject_field = _text(row.get("subject_field")) or editor.default_subject_field
        elif _text(row.get("subject_field")) and not editor.default_subject_field:
            editor.default_subject_field = _text(row.get("subject_field"))
    if not sheet_to_table and rows:
        _add_warning(warnings, "_表映射 中没有可识别的 table_name，已跳过该 sheet。")
    return sheet_to_table


def _parse_sql_rules(rows: list[dict[str, Any]]) -> str:
    rules = []
    for row in rows:
        rule_text = _text(row.get("rule_text"))
        if not rule_text:
            continue
        name = _text(row.get("rule_name"))
        scope = _text(row.get("scope"))
        prefix = " / ".join([item for item in (name, scope) if item])
        rules.append(f"{prefix}: {rule_text}" if prefix else rule_text)
    return "\n".join(rules)


def _parse_generic_business_sheet(
    rows: list[dict[str, Any]],
    table_name: str,
    editor: TenantTrackingConfigEditor,
    *,
    datasource_type: str | None,
    warnings: list[str],
    physical_schema: dict[str, PhysicalTableInfo],
) -> None:
    for row in rows:
        row_type = _text(row.get("row_type")).lower() or "dictionary_field"
        row_type = row_type.replace("-", "_").replace(" ", "_")
        if row_type in {"event", "event_definition"}:
            event = _event_mapping(row)
            if event:
                _append_event_mapping(editor.event_name_mappings, event)
            continue

        if row_type in {"event_property", "eventproperty"}:
            event = _event_mapping(row)
            prop = _event_property(row)
            if event:
                _append_event_mapping(editor.event_name_mappings, event, prop)
            field_item = _field_item(
                row,
                table_name,
                row_type="event_property",
                datasource_type=datasource_type,
                warnings=warnings,
                physical_schema=physical_schema,
            )
            if field_item:
                editor.fields.append(field_item)
            continue

        if row_type in {"physical_field", "dictionary_field", "json_view", "field", "property"}:
            field_item = _field_item(
                row,
                table_name,
                row_type=row_type,
                datasource_type=datasource_type,
                warnings=warnings,
                physical_schema=physical_schema,
            )
            if field_item:
                editor.fields.append(field_item)


def _parse_competitor_event_sheet(
    rows: list[dict[str, Any]],
    editor: TenantTrackingConfigEditor,
    *,
    event_table: str,
    datasource_type: str | None,
    warnings: list[str],
    physical_schema: dict[str, PhysicalTableInfo],
) -> None:
    last_event: dict[str, Any] = {}
    for row in rows:
        event_name = _text(row.get("event_name"))
        if event_name:
            last_event = {
                "event_name": event_name,
                "event_display_name": _text(row.get("event_display_name")),
                "event_description": _text(row.get("event_description")),
                "event_category": _text(row.get("event_category")),
                "collect_side": _text(row.get("collect_side")),
            }
        elif last_event:
            for key, value in last_event.items():
                if not _text(row.get(key)):
                    row[key] = value

        event = _event_mapping(row)
        prop = _event_property(row)
        table_name = _text(row.get("source_table")) or event_table
        if event:
            _append_event_mapping(editor.event_name_mappings, event, prop)
        if prop:
            normalized = dict(row)
            normalized["field_name"] = prop["property_name"]
            normalized["field_display_name"] = prop.get("property_display_name", "")
            normalized["field_type"] = prop.get("property_type", "")
            field_item = _field_item(
                normalized,
                table_name,
                row_type="event_property",
                datasource_type=datasource_type,
                warnings=warnings,
                physical_schema=physical_schema,
            )
            if field_item:
                editor.fields.append(field_item)


def _parse_competitor_property_sheet(
    rows: list[dict[str, Any]],
    editor: TenantTrackingConfigEditor,
    *,
    table_name: str,
    datasource_type: str | None,
    warnings: list[str],
    physical_schema: dict[str, PhysicalTableInfo],
) -> None:
    for row in rows:
        field_name = _text(row.get("property_name"))
        if not field_name:
            continue
        table_for_row = _text(row.get("source_table")) or table_name
        normalized = dict(row)
        normalized["field_name"] = field_name
        normalized["field_display_name"] = _text(row.get("property_display_name"))
        normalized["field_type"] = _text(row.get("property_type"))
        normalized["description"] = _text(row.get("description"))
        field_item = _field_item(
            normalized,
            table_for_row,
            row_type="dictionary_field",
            datasource_type=datasource_type,
            warnings=warnings,
            physical_schema=physical_schema,
        )
        if field_item:
            editor.fields.append(field_item)


def parse_tracking_excel(
    content: bytes,
    existing: TenantTrackingConfigDTO,
    *,
    physical_schema: dict[str, PhysicalTableInfo] | None = None,
    datasource_type: str | None = None,
) -> ParsedTrackingConfig:
    schema = physical_schema or {}
    warnings: list[str] = []
    skipped_rows = 0
    excel = pd.ExcelFile(io.BytesIO(content))
    profile = (
        THINKINGDATA_LIKE_PROFILE
        if any(name in excel.sheet_names for name in {COMPETITOR_EVENT_SHEET, COMPETITOR_COMMON_PROPERTY_SHEET, COMPETITOR_USER_PROPERTY_SHEET})
        else GENERIC_PROFILE
    )
    imported = TenantTrackingConfigEditor(
        enabled=True,
        tables=[],
        fields=[],
        event_name_mappings=[],
    )
    sheet_to_table: dict[str, str] = {}

    if TABLE_MAP_SHEET in excel.sheet_names:
        rows, skipped = _read_sheet_rows(excel, TABLE_MAP_SHEET)
        skipped_rows += skipped
        sheet_to_table = _parse_table_map(rows, imported, warnings)

    if SQL_RULE_SHEET in excel.sheet_names:
        rows, skipped = _read_sheet_rows(excel, SQL_RULE_SHEET)
        skipped_rows += skipped
        imported.sql_rules = _parse_sql_rules(rows) or None

    if profile == THINKINGDATA_LIKE_PROFILE:
        event_table = ""
        if COMPETITOR_EVENT_SHEET in excel.sheet_names or COMPETITOR_COMMON_PROPERTY_SHEET in excel.sheet_names:
            event_table = sheet_to_table.get(COMPETITOR_EVENT_SHEET) or sheet_to_table.get(COMPETITOR_COMMON_PROPERTY_SHEET) or _resolve_event_table(existing, schema, warnings)
            imported.default_event_table = imported.default_event_table or event_table
        if COMPETITOR_EVENT_SHEET in excel.sheet_names:
            rows, skipped = _read_sheet_rows(excel, COMPETITOR_EVENT_SHEET)
            skipped_rows += skipped
            _parse_competitor_event_sheet(
                rows,
                imported,
                event_table=event_table,
                datasource_type=datasource_type,
                warnings=warnings,
                physical_schema=schema,
            )
        if COMPETITOR_COMMON_PROPERTY_SHEET in excel.sheet_names:
            rows, skipped = _read_sheet_rows(excel, COMPETITOR_COMMON_PROPERTY_SHEET)
            skipped_rows += skipped
            _parse_competitor_property_sheet(
                rows,
                imported,
                table_name=event_table,
                datasource_type=datasource_type,
                warnings=warnings,
                physical_schema=schema,
            )
        if COMPETITOR_USER_PROPERTY_SHEET in excel.sheet_names:
            rows, skipped = _read_sheet_rows(excel, COMPETITOR_USER_PROPERTY_SHEET)
            skipped_rows += skipped
            user_table = sheet_to_table.get(COMPETITOR_USER_PROPERTY_SHEET) or _resolve_subject_table(existing, schema, warnings)
            _parse_competitor_property_sheet(
                rows,
                imported,
                table_name=user_table,
                datasource_type=datasource_type,
                warnings=warnings,
                physical_schema=schema,
            )

    for sheet_name in excel.sheet_names:
        if sheet_name in SYSTEM_SHEETS:
            continue
        rows, skipped = _read_sheet_rows(excel, sheet_name)
        skipped_rows += skipped
        if not rows:
            continue
        table_name = sheet_to_table.get(sheet_name, sheet_name)
        imported.tables.append(
            _table_item(
                table_name,
                table_comment=_text(schema.get(table_name).custom_comment if schema.get(table_name) else ""),
            )
        )
        _parse_generic_business_sheet(
            rows,
            table_name,
            imported,
            datasource_type=datasource_type,
            warnings=warnings,
            physical_schema=schema,
        )

    if not imported.tables and not imported.fields and not imported.event_name_mappings:
        raise ValueError("Excel 中没有可识别的表、字段或事件配置，请使用平台模板或包含 #事件数据/#用户数据 的兼容模板。")

    known_tables = set(schema.keys())
    if known_tables:
        for table in imported.tables:
            if table.table_name not in known_tables:
                _add_warning(
                    warnings,
                    f"{table.table_name} 不在当前绑定数据源 schema 中，配置会保存但不会出现在图表字段列表里。",
                )

    merged = _merge_tracking_config(existing, imported)
    return ParsedTrackingConfig(editor=merged, profile=profile, warnings=warnings, skipped_rows=skipped_rows)


def import_summary(parsed: ParsedTrackingConfig) -> TenantTrackingImportSummary:
    return TenantTrackingImportSummary(
        profile=parsed.profile,
        table_count=len(parsed.editor.tables or []),
        field_count=len(parsed.editor.fields or []),
        event_count=len(parsed.editor.event_name_mappings or []),
        skipped_rows=parsed.skipped_rows,
        warning_count=len(parsed.warnings),
        warnings=parsed.warnings[:50],
    )


def _safe_sheet_name(value: str, used: set[str]) -> str:
    text = re.sub(r"[\[\]:*?/\\]", "_", _text(value) or "Sheet")
    text = text.strip("'") or "Sheet"
    base = text[:31]
    candidate = base
    index = 2
    while candidate in used:
        suffix = f"_{index}"
        candidate = f"{base[:31 - len(suffix)]}{suffix}"
        index += 1
    used.add(candidate)
    return candidate


def _apply_business_sheet_layout(workbook, worksheet, rows: list[dict[str, Any]], columns: list[str]) -> None:
    if not rows or "field_view" not in columns:
        return
    view_col = columns.index("field_view")
    group_clear_format = workbook.add_format({
        "bg_color": "#BFBFBF",
        "border": 1,
    })
    view_format = workbook.add_format({
        "align": "center",
        "valign": "vcenter",
        "bold": True,
        "text_wrap": True,
        "bg_color": "#EAF1FF",
        "font_color": "#1F4E79",
        "border": 1,
    })
    event_area_end_col = max(view_col - 1, 0)
    start_index = 0
    while start_index < len(rows):
        current_view = _text(rows[start_index].get("field_view"))
        if not current_view:
            start_index += 1
            continue
        end_index = start_index
        while end_index + 1 < len(rows) and _text(rows[end_index + 1].get("field_view")) == current_view:
            end_index += 1
        excel_start = start_index + 1
        excel_end = end_index + 1
        if event_area_end_col > 0:
            if excel_end > excel_start:
                worksheet.merge_range(excel_start, 0, excel_end, event_area_end_col, "", group_clear_format)
            else:
                worksheet.write_blank(excel_start, 0, None, group_clear_format)
                for clear_col in range(1, event_area_end_col + 1):
                    worksheet.write_blank(excel_start, clear_col, None, group_clear_format)
        if excel_end > excel_start:
            worksheet.merge_range(excel_start, view_col, excel_end, view_col, current_view, view_format)
        else:
            worksheet.write(excel_start, view_col, current_view, view_format)
        start_index = end_index + 1


def _first_alias(value: Any) -> str:
    aliases = getattr(value, "aliases", None) or []
    for alias in aliases:
        text = _text(alias)
        if text:
            return text
    return ""


def _config_table_map(config: TenantTrackingConfigDTO) -> dict[str, Any]:
    return {table.table_name: table for table in config.tables or [] if table.table_name}


def _config_field_map(config: TenantTrackingConfigDTO) -> dict[tuple[str, str], Any]:
    return {
        (field.table_name, field.field_name): field
        for field in config.fields or []
        if field.table_name and field.field_name
    }


def _business_row_from_field(field_item: Any, *, row_type: str) -> dict[str, Any]:
    source_field = _text(field_item.source_field)
    json_path = _text(field_item.json_path)
    has_view = bool(source_field and json_path)
    display_field_name = _json_child_name(source_field, field_item.field_name, json_path) if has_view else field_item.field_name
    return {
        "row_type": row_type,
        "event_name": "",
        "event_display_name": "",
        "event_category": "",
        "collect_side": "",
        "field_view": f"{source_field} view" if has_view else "",
        "field_name": display_field_name,
        "field_display_name": _first_alias(field_item),
        "field_type": field_item.semantic_type or "",
        "field_role": field_item.field_role or "",
        "semantic_type": field_item.semantic_type or "",
        "source_field": source_field,
        "json_path": json_path,
        "expression": field_item.expression or "",
        "required": "Y" if field_item.required else "",
        "enum_values": "\n".join(str(item) for item in field_item.value_mappings or []) if isinstance(field_item.value_mappings, list) else "",
        "example_values": "\n".join(str(item) for item in field_item.example_values or []),
        "description": field_item.field_comment or "",
        "ai_notes": field_item.ai_notes or "",
    }


def _business_field_sort_key(field_item: Any) -> tuple[str, str, str]:
    source = _text(getattr(field_item, "source_field", ""))
    json_path = _text(getattr(field_item, "json_path", ""))
    view_key = source if source and json_path else ""
    return (view_key, _text(getattr(field_item, "field_name", "")), _text(getattr(field_item, "semantic_type", "")))


def _business_event_rows(config: TenantTrackingConfigDTO, table_name: str) -> list[dict[str, Any]]:
    if not config.default_event_table or config.default_event_table != table_name:
        return []
    rows: list[dict[str, Any]] = []
    for item in config.event_name_mappings or []:
        if not isinstance(item, dict):
            continue
        event_name = _first_text(item.get("event_name"), item.get("name"), item.get("value"))
        if not event_name:
            continue
        rows.append({
            "row_type": "event",
            "event_name": event_name,
            "event_display_name": _text(item.get("event_display_name")),
            "event_category": _text(item.get("event_category")),
            "collect_side": _text(item.get("collect_side")),
            "field_view": "",
            "field_name": "",
            "field_display_name": "",
            "field_type": "",
            "field_role": "",
            "semantic_type": "",
            "source_field": "",
            "json_path": "",
            "expression": "",
            "required": "",
            "enum_values": "",
            "example_values": "",
            "description": _text(item.get("description")),
            "ai_notes": _text(item.get("ai_notes")),
        })
        for prop in item.get("properties", []) or []:
            if not isinstance(prop, dict):
                continue
            prop_name = _first_text(prop.get("property_name"), prop.get("field_name"), prop.get("name"))
            if not prop_name:
                continue
            source_field = _text(prop.get("source_field"))
            json_path = _text(prop.get("json_path"))
            has_view = bool(source_field and json_path)
            rows.append({
                "row_type": "event_property",
                "event_name": event_name,
                "event_display_name": "",
                "event_category": "",
                "collect_side": "",
                "field_view": f"{source_field} view" if has_view else "",
                "field_name": _json_child_name(source_field, prop_name, json_path) if has_view else prop_name,
                "field_display_name": _text(prop.get("property_display_name")),
                "field_type": _text(prop.get("property_type")),
                "field_role": "",
                "semantic_type": "",
                "source_field": source_field,
                "json_path": json_path,
                "expression": "",
                "required": "",
                "enum_values": "",
                "example_values": "",
                "description": _text(prop.get("description")),
                "ai_notes": "",
            })
    return rows


def tracking_config_excel(
    config: TenantTrackingConfigDTO,
    *,
    physical_schema: dict[str, PhysicalTableInfo] | None = None,
    template_only: bool = False,
) -> io.BytesIO:
    schema = physical_schema or {}
    table_map = _config_table_map(config)
    field_map = _config_field_map(config)
    used_sheet_names: set[str] = set()
    sheet_name_by_table: dict[str, str] = {}
    all_table_names = list(schema.keys())
    for table in config.tables or []:
        if table.table_name and table.table_name not in all_table_names:
            all_table_names.append(table.table_name)
    if not all_table_names:
        all_table_names = ["event", "subject_profile"]

    for table_name in all_table_names:
        sheet_name_by_table[table_name] = _safe_sheet_name(table_name, used_sheet_names)

    table_rows: list[dict[str, Any]] = []
    for table_name in all_table_names:
        table_info = schema.get(table_name)
        configured = table_map.get(table_name)
        table_rows.append({
            "sheet_name": sheet_name_by_table[table_name],
            "table_name": table_name,
            "table_display_name": _first_alias(configured) if configured else "",
            "table_role": getattr(configured, "table_role", "") or "",
            "subject_field": config.default_subject_field if config.default_event_table == table_name else "",
            "event_name_field": config.default_event_name_field if config.default_event_table == table_name else "",
            "event_time_field": config.default_event_time_field if config.default_event_table == table_name else "",
            "partition_field": "",
            "table_comment": (
                getattr(configured, "table_comment", "") or
                (table_info.custom_comment if table_info else "") or
                (table_info.table_comment if table_info else "")
            ),
            "ai_notes": getattr(configured, "ai_notes", "") or "",
        })

    sheets: list[tuple[str, list[dict[str, Any]], list[str]]] = [
        (
            INFO_SHEET,
            [
                {"项目": "用途", "说明": "下载模板后按真实表 sheet 维护字段语义，上传后会合并到当前工作空间数据字典。"},
                {"项目": "JSON 字段", "说明": "JSON 子字段必须维护 source_field 和 json_path；字段名带点号只用于便捷识别。"},
                {"项目": "表达式", "说明": "expression 应填写当前数据源方言的 SQL 表达式，供图表 SQL 配置器直接使用。"},
                {"项目": "复杂口径", "说明": "复杂指标、留存、漏斗、窗口等分析口径建议维护到 Data Skills，不写入字段模板。"},
            ],
            ["项目", "说明"],
        ),
        (TABLE_MAP_SHEET, table_rows, TABLE_MAP_COLUMNS),
    ]

    for table_name in all_table_names:
        rows: list[dict[str, Any]] = []
        if not template_only:
            rows.extend(_business_event_rows(config, table_name))
        physical_fields = schema.get(table_name).fields if schema.get(table_name) else []
        physical_names = {field_info.field_name for field_info in physical_fields}
        for field_info in physical_fields:
            configured = field_map.get((table_name, field_info.field_name))
            if configured and not template_only:
                row = _business_row_from_field(configured, row_type="physical_field")
                row["field_type"] = row["field_type"] or field_info.field_type
                row["description"] = row["description"] or field_info.custom_comment or field_info.field_comment
                rows.append(row)
            else:
                rows.append({
                    "row_type": "physical_field",
                    "event_name": "",
                    "event_display_name": "",
                    "event_category": "",
                    "collect_side": "",
                    "field_view": "",
                    "field_name": field_info.field_name,
                    "field_display_name": "",
                    "field_type": field_info.field_type,
                    "field_role": "",
                    "semantic_type": "",
                    "source_field": "",
                    "json_path": "",
                    "expression": "",
                    "required": "",
                    "enum_values": "",
                    "example_values": "",
                    "description": field_info.custom_comment or field_info.field_comment,
                    "ai_notes": "",
                })
        if not template_only:
            configured_fields = [
                configured
                for (field_table, _), configured in field_map.items()
                if field_table == table_name and configured.field_name not in physical_names
            ]
            for configured in sorted(configured_fields, key=_business_field_sort_key):
                rows.append(_business_row_from_field(configured, row_type="dictionary_field"))
        elif not rows and table_name == "event":
            rows.extend([
                {
                    "row_type": "physical_field",
                    "event_name": "",
                    "event_display_name": "",
                    "event_category": "",
                    "collect_side": "",
                    "field_view": "",
                    "field_name": "event",
                    "field_display_name": "",
                    "field_type": "json",
                    "field_role": "event_params_json",
                    "semantic_type": "json",
                    "source_field": "",
                    "json_path": "",
                    "expression": "",
                    "required": "",
                    "enum_values": "",
                    "example_values": "",
                    "description": "承载事件明细的 JSON 字符串字段示例，可按实际字段名修改。",
                    "ai_notes": "",
                },
                {
                    "row_type": "dictionary_field",
                    "event_name": "",
                    "event_display_name": "",
                    "event_category": "",
                    "collect_side": "",
                    "field_view": "event view",
                    "field_name": "amount",
                    "field_display_name": "金额",
                    "field_type": "number",
                    "field_role": "json_path_metric",
                    "semantic_type": "number",
                    "source_field": "event",
                    "json_path": "$.amount",
                    "expression": "",
                    "required": "",
                    "enum_values": "",
                    "example_values": "",
                    "description": "JSON 子字段示例；上传前请改成真实字段。",
                    "ai_notes": "",
                },
            ])
        sheets.append((sheet_name_by_table[table_name], rows, BUSINESS_COLUMNS))

    sheets.extend([
        (ENUM_SHEET, [], ENUM_COLUMNS),
        (SQL_RULE_SHEET, [{"rule_name": "示例", "scope": "", "rule_text": config.sql_rules or "", "priority": ""}] if config.sql_rules and not template_only else [], SQL_RULE_COLUMNS),
    ])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter", engine_kwargs={"options": {"strings_to_numbers": False}}) as writer:
        for sheet_name, rows, columns in sheets:
            df = pd.DataFrame(rows, columns=columns)
            df.columns = [EXPORT_COLUMN_LABELS.get(column, column) for column in columns]
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            workbook = writer.book
            worksheet = writer.sheets[sheet_name]
            for col_index, column in enumerate(columns):
                header_label = EXPORT_COLUMN_LABELS.get(column, column)
                max_len = max([len(str(header_label))] + [len(str(row.get(column, ""))) for row in rows[:200]])
                worksheet.set_column(col_index, col_index, min(max(max_len + 2, 12), 42))
            if "field_view" in columns:
                worksheet.set_column(columns.index("field_view"), columns.index("field_view"), 16)
                _apply_business_sheet_layout(workbook, worksheet, rows, columns)
            if rows:
                worksheet.freeze_panes(1, 0)
    output.seek(0)
    return io.BytesIO(output.getvalue())
