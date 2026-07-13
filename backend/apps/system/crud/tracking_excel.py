"""
脚本说明：这个脚本负责数据字典 Excel 的导入导出，把运维可维护的表格转换成工作空间语义配置。
"""
from __future__ import annotations

import io
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from apps.system.crud.tracking_config import validate_tracking_event_groups
from apps.system.crud.tracking_expression import (
    json_path_segments as _json_path_segments,
)
from apps.system.crud.tracking_expression import (
    normalize_json_path as _normalize_json_path,
)
from apps.system.schemas.tenant_schema import (
    TenantTrackingConfigDTO,
    TenantTrackingConfigEditor,
    TenantTrackingEventGroupBase,
    TenantTrackingFieldBase,
    TenantTrackingImportSummary,
    TenantTrackingTableBase,
)

GENERIC_PROFILE = "shuzhi_generic_v1"

INFO_SHEET = "_说明"
TABLE_MAP_SHEET = "_表映射"
SQL_RULE_SHEET = "_SQL规则"
EVENT_PARAMETER_MAPPING_SHEET = "事件参数对照"
EVENT_GROUP_SHEET = "事件分组"
EXCEL_ROW_NUMBER_KEY = "__excel_row_number__"

SYSTEM_SHEETS = {
    INFO_SHEET,
    TABLE_MAP_SHEET,
    SQL_RULE_SHEET,
    EVENT_PARAMETER_MAPPING_SHEET,
    EVENT_GROUP_SHEET,
    "数据类型设计原则",
    "公共事件属性设置方式",
    "多端接入注意点",
    "多用户id体系的埋点建议",
}

BUSINESS_COLUMNS = [
    "row_type",
    "field_name",
    "field_display_name",
    "field_type",
    "field_role",
    "semantic_type",
    "source_field",
    "json_path",
    "expression",
    "required",
    "value",
    "value_display_name",
    "value_category",
    "collect_side",
    "event_name",
    "event_display_name",
    "event_category",
    "example_values",
    "description",
    "ai_notes",
    "aliases",
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
    "aliases",
]

SQL_RULE_COLUMNS = [
    "rule_name",
    "scope",
    "rule_text",
    "priority",
]

ATTRIBUTE_COLUMNS = [
    "field_name",
    "field_display_name",
    "field_type",
    "update_mode",
    "description",
    "field_category",
]

EVENT_PARAMETER_MAPPING_COLUMNS = [
    "event_name",
    "event_display_name",
    "event_description",
    "event_category",
    "collect_side",
    "source_field",
    "property_name",
    "property_display_name",
    "property_type",
    "description",
]

EVENT_GROUP_COLUMNS = [
    "group_key",
    "group_name",
    "group_description",
    "group_sort_order",
    "event_name",
    "event_order",
    "enabled",
]
EVENT_GROUP_MIN_WIDTHS = {
    "group_key": 20,
    "group_name": 20,
    "group_description": 28,
    "group_sort_order": 12,
    "event_name": 24,
    "event_order": 12,
    "enabled": 10,
}

ATTRIBUTE_EXPORT_COLUMN_LABELS = {
    "field_name": "属性名（必填）",
    "field_display_name": "属性显示名",
    "field_type": "属性类型（必填）",
    "update_mode": "更新方式",
    "description": "属性说明",
    "field_category": "属性标签",
}

EXPORT_COLUMN_LABELS = {
    "row_type": "行类型",
    "event_name": "事件名（必填）",
    "event_display_name": "事件显示名",
    "event_category": "事件标签",
    "collect_side": "采集端",
    "event_description": "事件说明",
    "field_name": "字段名",
    "field_display_name": "字段显示名",
    "field_type": "字段类型",
    "field_category": "属性标签",
    "field_role": "字段角色",
    "semantic_type": "语义类型",
    "source_field": "来源字段",
    "json_path": "JSON 路径",
    "expression": "字段表达式",
    "required": "是否必填",
    "value": "值",
    "value_display_name": "值显示名",
    "value_category": "值标签",
    "example_values": "示例值",
    "description": "说明",
    "ai_notes": "AI 说明",
    "aliases": "别名",
    "source_table": "来源表",
    "property_name": "属性名（必填）",
    "property_display_name": "属性显示名",
    "property_type": "属性类型（必填）",
    "property_category": "属性标签",
    "update_mode": "更新方式",
    "sheet_name": "工作表名",
    "table_name": "物理表名",
    "table_display_name": "表显示名",
    "table_role": "表角色",
    "subject_field": "主体字段",
    "event_name_field": "事件名字段",
    "event_time_field": "事件时间字段",
    "partition_field": "分区字段",
    "table_comment": "表说明",
    "rule_name": "规则名",
    "scope": "适用范围",
    "rule_text": "规则内容",
    "priority": "优先级",
    "group_key": "分组标识（必填）",
    "group_name": "分组名称（必填）",
    "group_description": "分组说明",
    "group_sort_order": "分组排序",
    "event_order": "事件排序",
    "enabled": "启用",
}

BUSINESS_EXPORT_COLUMN_LABELS = {
    "row_type": "行类型",
    "field_name": "字段名",
    "field_display_name": "字段显示名",
    "field_type": "字段类型",
    "field_role": "字段角色",
    "semantic_type": "语义类型",
    "source_field": "来源字段",
    "json_path": "JSON 路径",
    "expression": "字段表达式",
    "required": "是否必填",
    "value": "字段/事件取值",
    "value_display_name": "取值显示名",
    "value_category": "取值标签",
    "collect_side": "采集端",
    "event_name": "适用事件名",
    "event_display_name": "适用事件显示名",
    "event_category": "适用事件标签",
    "example_values": "示例值",
    "description": "说明",
    "ai_notes": "AI 说明",
    "aliases": "别名",
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
    "item": "item",
    "project": "item",
    "configkey": "item",
    "配置项": "item",
    "项目": "item",
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
    "datasourcefield": "source_field",
    "数据源字段": "source_field",
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
    "适用事件名": "event_name",
    "适用事件显示名": "event_display_name",
    "适用事件标签": "event_category",
    "eventdescription": "event_description",
    "事件说明": "event_description",
    "eventcategory": "event_category",
    "事件分类": "event_category",
    "事件标签": "event_category",
    "collectside": "collect_side",
    "采集端": "collect_side",
    "fieldname": "field_name",
    "字段名": "field_name",
    "属性名": "field_name",
    "fielddisplayname": "field_display_name",
    "字段显示名": "field_display_name",
    "字段展示名": "field_display_name",
    "属性显示名": "field_display_name",
    "fieldtype": "field_type",
    "字段类型": "field_type",
    "属性类型": "field_type",
    "updatemode": "update_mode",
    "更新方式": "update_mode",
    "fieldcategory": "field_category",
    "属性标签": "field_category",
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
    "fieldvalue": "value",
    "eventvalue": "value",
    "value": "value",
    "字段事件取值": "value",
    "字段取值": "value",
    "事件取值": "value",
    "枚举取值": "value",
    "取值": "value",
    "值": "value",
    "valuedisplayname": "value_display_name",
    "fieldvaluedisplayname": "value_display_name",
    "eventvaluedisplayname": "value_display_name",
    "字段取值显示名": "value_display_name",
    "事件取值显示名": "value_display_name",
    "取值显示名": "value_display_name",
    "值显示名": "value_display_name",
    "valuecategory": "value_category",
    "fieldvaluecategory": "value_category",
    "eventvaluecategory": "value_category",
    "字段取值标签": "value_category",
    "事件取值标签": "value_category",
    "取值标签": "value_category",
    "值标签": "value_category",
    "examplevalues": "example_values",
    "示例值": "example_values",
    "样例": "example_values",
    "description": "description",
    "说明": "description",
    "备注": "description",
    "fieldcomment": "description",
    "字段说明": "description",
    "属性说明": "description",
    "ainotes": "ai_notes",
    "ai说明": "ai_notes",
    "llm说明": "ai_notes",
    "aliases": "aliases",
    "别名": "aliases",
    "别称": "aliases",
    "ruletitle": "rule_name",
    "rulename": "rule_name",
    "规则名": "rule_name",
    "scope": "scope",
    "范围": "scope",
    "ruletext": "rule_text",
    "规则内容": "rule_text",
    "priority": "priority",
    "优先级": "priority",
    "groupkey": "group_key",
    "分组标识": "group_key",
    "groupname": "group_name",
    "分组名称": "group_name",
    "groupdescription": "group_description",
    "分组说明": "group_description",
    "groupsortorder": "group_sort_order",
    "分组排序": "group_sort_order",
    "eventorder": "event_order",
    "事件排序": "event_order",
    "enabled": "enabled",
    "启用": "enabled",
}

ROW_TYPE_ALIASES = {
    "physicalfield": "physical_field",
    "physical_field": "physical_field",
    "物理字段": "physical_field",
    "物理列": "physical_field",
    "dictionaryfield": "dictionary_field",
    "dictionary_field": "dictionary_field",
    "jsonfield": "dictionary_field",
    "jsonsubfield": "dictionary_field",
    "字典字段": "dictionary_field",
    "json字段": "dictionary_field",
    "json子字段": "dictionary_field",
    "fieldvalue": "field_value",
    "field_value": "field_value",
    "enumvalue": "field_value",
    "字段值": "field_value",
    "字段取值": "field_value",
    "枚举值": "field_value",
    "eventvalue": "event_value",
    "event_value": "event_value",
    "eventname": "event_value",
    "event_name": "event_value",
    "事件值": "event_value",
    "事件取值": "event_value",
    "事件名取值": "event_value",
    "event": "event",
    "eventdefinition": "event",
    "event_definition": "event",
    "事件": "event",
    "事件定义": "event",
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
    if not key:
        return ""
    return HEADER_ALIASES.get(key, _text(value))


def _read_sheet_rows(
    excel: pd.ExcelFile,
    sheet_name: str,
    *,
    require_recognized_header: bool = False,
    include_row_number: bool = False,
) -> tuple[list[dict[str, Any]], int]:
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
        nonempty_row_count = sum(
            1
            for _, row in raw.iterrows()
            if any(_text(value) for value in row.tolist())
        )
        if require_recognized_header and nonempty_row_count > 1:
            raise ValueError(f"{sheet_name} sheet 表头无法识别，请使用平台导出的固定表头。")
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
    for raw_index, raw_row in raw.iloc[header_index + 1 :].iterrows():
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
            if include_row_number:
                row[EXCEL_ROW_NUMBER_KEY] = int(raw_index) + 1
            rows.append(row)
        else:
            skipped += 1
    return rows, skipped


KNOWN_IMPORT_COLUMNS = (
    set(BUSINESS_COLUMNS)
    | set(TABLE_MAP_COLUMNS)
    | set(SQL_RULE_COLUMNS)
    | set(ATTRIBUTE_COLUMNS)
    | set(EVENT_PARAMETER_MAPPING_COLUMNS)
    | set(EVENT_GROUP_COLUMNS)
    | set(HEADER_ALIASES.values())
)


def _extra_properties_from_row(row: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in row.items():
        if not key or key in KNOWN_IMPORT_COLUMNS:
            continue
        text = _text(value)
        if text:
            result[key] = text
    return result


def _merge_extra_properties(old: dict[str, Any] | None, new: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = dict(old or {})
    for key, value in (new or {}).items():
        if _text(value):
            result[key] = value
    return result


def _extra_properties(item: Any) -> dict[str, Any]:
    value = getattr(item, "extra_properties", None)
    return value if isinstance(value, dict) else {}


def _columns_with_extra(base_columns: list[str], rows: list[dict[str, Any]]) -> list[str]:
    columns = list(base_columns)
    seen = set(columns)
    for row in rows:
        for key, value in row.items():
            if key in seen or key in KNOWN_IMPORT_COLUMNS:
                continue
            if _text(value):
                columns.append(key)
                seen.add(key)
    return columns


def _row_type(value: Any) -> str:
    text = _text(value).lower()
    if not text:
        return ""
    normalized = text.replace("-", "_").replace(" ", "_")
    compact = normalized.replace("_", "")
    return ROW_TYPE_ALIASES.get(normalized) or ROW_TYPE_ALIASES.get(compact) or normalized


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


ATTRIBUTE_TYPE_LABELS = {
    "text": "文本",
    "category": "文本",
    "identifier": "文本",
    "country_code": "文本",
    "number": "数值",
    "date": "时间",
    "datetime": "时间",
    "timestamp_ms": "时间",
    "boolean": "布尔",
    "boolean_flag": "布尔",
    "json": "对象组",
    "object": "对象组",
    "object_array": "对象组",
    "array": "对象组",
}


def _attribute_type_label(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if not text:
            continue
        normalized = _semantic_type(text)
        return ATTRIBUTE_TYPE_LABELS.get(normalized, ATTRIBUTE_TYPE_LABELS.get(text.lower(), text))
    return "文本"


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


def _json_text(value: Any) -> str:
    if value in (None, [], {}):
        return ""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _parse_json_list(value: Any, warnings: list[str], label: str) -> list[Any]:
    text = _text(value)
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        _add_warning(warnings, f"{label} 不是合法 JSON，已跳过。")
        return []
    if isinstance(parsed, list):
        return parsed
    _add_warning(warnings, f"{label} 必须是 JSON 数组，已跳过。")
    return []


def _aliases_text(value: Any) -> str:
    aliases = getattr(value, "aliases", None) or []
    return "\n".join(_text(alias) for alias in aliases if _text(alias))


def _aliases_from_row(row: dict[str, Any], display_name: str, canonical_name: str) -> list[str]:
    aliases = []
    if display_name and display_name != canonical_name:
        aliases.append(display_name)
    aliases.extend(_split_list(row.get("aliases")))
    return _merge_list([], aliases)


def _json_path_from_field_name(field_name: str) -> tuple[str, str]:
    text = _text(field_name)
    if "." not in text:
        return "", ""
    source, child = text.split(".", 1)
    return source.strip(), f"$.{child.strip()}" if child.strip() else ""


def _json_child_name(source_field: str, field_name: str, json_path: str | None = None) -> str:
    source = _text(source_field)
    field_text = _text(field_name)
    if source and field_text.startswith(f"{source}."):
        return field_text[len(source) + 1 :]
    path_segments = _json_path_segments(json_path or "")
    if path_segments:
        return ".".join(path_segments)
    return field_text


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
        extra_properties=dict(getattr(item, "extra_properties", {}) if not isinstance(item, dict) else item.get("extra_properties", {}) or {}),
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
        update_mode=_text(getattr(item, "update_mode", None) if not isinstance(item, dict) else item.get("update_mode")) or None,
        category=_text(getattr(item, "category", None) if not isinstance(item, dict) else item.get("category")) or None,
        aliases=list(getattr(item, "aliases", []) if not isinstance(item, dict) else item.get("aliases", []) or []),
        value_mappings=getattr(item, "value_mappings", None) if not isinstance(item, dict) else item.get("value_mappings"),
        expression=_text(getattr(item, "expression", None) if not isinstance(item, dict) else item.get("expression")) or None,
        required=bool(getattr(item, "required", False) if not isinstance(item, dict) else item.get("required", False)),
        example_values=list(getattr(item, "example_values", []) if not isinstance(item, dict) else item.get("example_values", []) or []),
        ai_notes=_text(getattr(item, "ai_notes", None) if not isinstance(item, dict) else item.get("ai_notes")) or None,
        extra_properties=dict(getattr(item, "extra_properties", {}) if not isinstance(item, dict) else item.get("extra_properties", {}) or {}),
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


def _value_mapping_key(item: Any) -> str:
    if isinstance(item, dict):
        return _first_text(item.get("value"), item.get("name"), item.get("key"))
    text = _text(item)
    if "=" in text:
        return text.split("=", 1)[0].strip()
    return text


def _merge_value_mappings(old: Any, new: Any) -> Any:
    if new in (None, [], {}):
        return old
    if old in (None, [], {}):
        return new
    if not isinstance(old, list) or not isinstance(new, list):
        return new

    result: dict[str, Any] = {}
    order: list[str] = []
    for item in old + new:
        key = _value_mapping_key(item)
        if not key:
            continue
        if key not in order:
            order.append(key)
        if isinstance(item, dict):
            current = result.setdefault(key, {"value": key})
            for item_key, item_value in item.items():
                if _text(item_value) or item_key not in current:
                    current[item_key] = item_value
        else:
            result.setdefault(key, item)
    return [result[key] for key in order if key in result]


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
    base.event_groups = imported.event_groups

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
        current.extra_properties = _merge_extra_properties(current.extra_properties, table.extra_properties)
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
        current.value_mappings = _merge_value_mappings(current.value_mappings, field_item.value_mappings)
        current.expression = _merge_text(current.expression, field_item.expression)
        current.required = bool(current.required or field_item.required)
        current.example_values = _merge_list(current.example_values, field_item.example_values)
        current.ai_notes = _merge_text(current.ai_notes, field_item.ai_notes)
        current.update_mode = _merge_text(getattr(current, "update_mode", None), getattr(field_item, "update_mode", None))
        current.category = _merge_text(getattr(current, "category", None), getattr(field_item, "category", None))
        current.extra_properties = _merge_extra_properties(current.extra_properties, field_item.extra_properties)
    base.fields = list(field_by_key.values())
    return base


def _dedupe_imported_tracking_config(imported: TenantTrackingConfigEditor) -> TenantTrackingConfigEditor:
    empty_current = TenantTrackingConfigDTO(tenant_id=0, enabled=imported.enabled)
    return _merge_tracking_config(empty_current, imported)


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
    extra_properties: dict[str, Any] | None = None,
) -> TenantTrackingTableBase:
    aliases = _merge_list([], [alias] if alias and alias != table_name else [])
    return TenantTrackingTableBase(
        table_name=table_name,
        table_comment=table_comment or None,
        table_role=table_role or None,
        aliases=aliases,
        ai_notes=ai_notes or None,
        extra_properties=dict(extra_properties or {}),
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
    raw_field_name = _text(row.get("field_name"))
    source_field = _text(row.get("source_field"))
    json_path = _normalize_json_path(_text(row.get("json_path")))
    if not raw_field_name and row_type != "physical_field" and source_field and json_path:
        child_name = _json_child_name(source_field, "", json_path)
        if child_name:
            raw_field_name = f"{source_field}.{child_name}"
    field_name = raw_field_name
    if not table_name or not field_name:
        return None

    display_name = _text(row.get("field_display_name"))
    field_type = _text(row.get("field_type"))
    semantic_type = _first_text(row.get("semantic_type"), _semantic_type(field_type))
    configured_role = _text(row.get("field_role"))
    if configured_role.lower() == "event_name":
        semantic_type = "text"
    inferred_source, inferred_path = _json_path_from_field_name(raw_field_name)
    if not source_field and inferred_source:
        source_field = inferred_source
    if not json_path and inferred_path:
        json_path = inferred_path
    elif not json_path and source_field and row_type != "physical_field" and "." not in raw_field_name:
        json_path = _normalize_json_path(raw_field_name)
    if source_field and json_path and row_type != "physical_field" and "." not in raw_field_name:
        field_name = f"{source_field}.{raw_field_name}"

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
    if expression and source_field and json_path:
        _add_warning(
            warnings,
            f"{table_name}.{field_name} 的 expression 列将作为兼容配置保存；运行时会按当前数据源方言重新编译 JSON 表达式。",
        )

    aliases = _aliases_from_row(row, display_name, field_name)
    return TenantTrackingFieldBase(
        table_name=table_name,
        field_name=field_name,
        field_comment=_first_text(row.get("description"), row.get("event_description")) or None,
        field_role=_field_role(row_type, semantic_type, source_field, json_path, configured_role) or None,
        semantic_type=semantic_type or None,
        source_field=source_field or None,
        json_path=json_path or None,
        aliases=aliases,
        value_mappings=None,
        expression=expression or None,
        required=_parse_bool(row.get("required")),
        example_values=_split_list(row.get("example_values")),
        ai_notes=_text(row.get("ai_notes")) or None,
        update_mode=_text(row.get("update_mode")) or None,
        category=_text(row.get("field_category")) or _text(row.get("category")) or None,
        extra_properties=_extra_properties_from_row(row),
    )


def _event_mapping(row: dict[str, Any]) -> dict[str, Any] | None:
    event_name = _first_text(row.get("value"), row.get("event_name"))
    if not event_name:
        return None
    result = {
        "event_name": event_name,
        "event_display_name": _first_text(row.get("value_display_name"), row.get("event_display_name")),
        "event_category": _first_text(row.get("value_category"), row.get("event_category")),
        "collect_side": _text(row.get("collect_side")),
        "description": _first_text(row.get("event_description"), row.get("description")),
        "ai_notes": _text(row.get("ai_notes")),
        "aliases": _split_list(row.get("aliases")),
    }
    return {key: value for key, value in result.items() if value}


def _property_from_field_item(field_item: TenantTrackingFieldBase, row: dict[str, Any]) -> dict[str, Any]:
    result = {
        "property_name": field_item.field_name,
        "property_display_name": _first_alias(field_item),
        "property_type": field_item.semantic_type or _text(row.get("field_type")),
        "source_field": field_item.source_field or "",
        "json_path": field_item.json_path or "",
        "description": field_item.field_comment or "",
        "ai_notes": field_item.ai_notes or "",
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
            TenantTrackingTableBase(
                table_name=table_name,
                table_comment=_text(row.get("table_comment")) or None,
                table_role=_text(row.get("table_role")) or None,
                aliases=_aliases_from_row(row, _text(row.get("table_display_name")), table_name),
                ai_notes=_text(row.get("ai_notes")) or None,
                extra_properties=_extra_properties_from_row(row),
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


def _parse_info_sheet(rows: list[dict[str, Any]], editor: TenantTrackingConfigEditor, warnings: list[str]) -> None:
    for row in rows:
        item = _first_text(row.get("item"), row.get("description"))
        value = _text(row.get("description"))
        if not item:
            continue
        key = item.strip().lower()
        if key in {"config.enabled", "enabled", "启用"}:
            editor.enabled = _parse_bool(value)
        elif key in {"config.notes", "notes", "工作空间说明"}:
            editor.notes = value or None
        elif key in {"config.field_role_mappings", "field_role_mappings", "字段角色映射"}:
            editor.field_role_mappings = _parse_json_list(value, warnings, item)


def _append_field_value_mapping(
    editor: TenantTrackingConfigEditor,
    table_name: str,
    field_name: str,
    value: str,
    display_name: str = "",
    category: str = "",
    description: str = "",
    aliases: Any = None,
) -> None:
    if not table_name or not field_name or not value:
        return
    target = None
    for field_item in editor.fields or []:
        if field_item.table_name == table_name and field_item.field_name == field_name:
            target = field_item
            break
    if target is None:
        target = TenantTrackingFieldBase(
            table_name=table_name,
            field_name=field_name,
            semantic_type="text",
        )
        editor.fields.append(target)

    mapping: dict[str, Any] = {"value": value}
    if display_name:
        mapping["display_name"] = display_name
    if category:
        mapping["category"] = category
    if description:
        mapping["description"] = description
    alias_values = _split_list(aliases)
    if alias_values:
        mapping["aliases"] = alias_values
    values = list(target.value_mappings or []) if isinstance(target.value_mappings, list) else []
    if not any(isinstance(item, dict) and _text(item.get("value")) == value or _text(item) == value for item in values):
        values.append(mapping)
    target.value_mappings = values


def _apply_event_field_defaults(
    editor: TenantTrackingConfigEditor,
    table_name: str,
    field_name: str,
) -> None:
    if not table_name:
        return
    if not editor.default_event_table:
        editor.default_event_table = table_name
    if field_name and not editor.default_event_name_field:
        editor.default_event_name_field = field_name


def _parse_generic_business_sheet(
    rows: list[dict[str, Any]],
    table_name: str,
    editor: TenantTrackingConfigEditor,
    *,
    datasource_type: str | None,
    warnings: list[str],
    physical_schema: dict[str, PhysicalTableInfo],
) -> None:
    last_value_context: dict[str, str] = {}
    last_field_context: dict[str, str] = {}
    for row in rows:
        row_type = _row_type(row.get("row_type"))
        if not row_type and _text(row.get("value")):
            if _text(row.get("field_name")):
                row_type = "field_value"
                row["row_type"] = row_type
            elif last_value_context:
                _add_warning(
                    warnings,
                    f"{table_name} sheet 中有取值行省略 row_type/field_name，已按上一条取值上下文继承；建议补全上下文列，避免重排后导入错误。",
                )
                row_type = last_value_context.get("row_type", "")
                row["row_type"] = row_type
                for key in ("field_name", "field_display_name", "field_role", "semantic_type", "field_type", "source_field", "json_path"):
                    if not _text(row.get(key)) and last_value_context.get(key):
                        row[key] = last_value_context[key]
            elif last_field_context:
                _add_warning(
                    warnings,
                    f"{table_name} sheet 中有取值行省略 row_type/field_name，已按上一条字段上下文继承；建议补全上下文列，避免重排后导入错误。",
                )
                row_type = "field_value"
                row["row_type"] = row_type
                for key in ("field_name", "field_display_name", "field_role", "semantic_type", "field_type", "source_field", "json_path"):
                    if not _text(row.get(key)) and last_field_context.get(key):
                        row[key] = last_field_context[key]
        elif not row_type and (
            _text(row.get("field_name"))
            or _text(row.get("json_path"))
            or _text(row.get("source_field"))
        ) and last_field_context.get("field_name"):
            row_type = "dictionary_field"
            row["row_type"] = row_type
            if not _text(row.get("source_field")) and last_field_context.get("source_field"):
                row["source_field"] = last_field_context["source_field"]
            if not _text(row.get("field_role")) and last_field_context.get("field_role"):
                row["field_role"] = last_field_context["field_role"]
            if not _text(row.get("semantic_type")) and last_field_context.get("semantic_type"):
                row["semantic_type"] = last_field_context["semantic_type"]
            if not _text(row.get("field_type")) and last_field_context.get("field_type"):
                row["field_type"] = last_field_context["field_type"]
        if not row_type and _text(row.get("value")) and last_value_context:
            _add_warning(
                warnings,
                f"{table_name} sheet 中有取值行省略 row_type/field_name，已按上一条取值上下文继承；建议补全上下文列，避免重排后导入错误。",
            )
            row_type = last_value_context.get("row_type", "")
            row["row_type"] = row_type
            for key in ("field_name", "field_role", "semantic_type", "field_type"):
                if not _text(row.get(key)) and last_value_context.get(key):
                    row[key] = last_value_context[key]
        if not row_type:
            _add_warning(warnings, f"{table_name} sheet 中有一行缺少 row_type，已跳过。")
            continue
        if row_type in {"event_value", "field_value"} and not _text(row.get("field_name")):
            inherited_context = last_value_context or last_field_context
            if not inherited_context:
                _add_warning(
                    warnings,
                    f"{table_name} sheet 中 {row_type} 行缺少 field_name 且没有可继承上下文，已跳过。",
                )
                continue
            _add_warning(
                warnings,
                f"{table_name} sheet 中 {row_type} 行缺少 field_name，已按上一条上下文继承；建议补全 field_name。",
            )
            for key in ("field_name", "field_display_name", "field_role", "semantic_type", "field_type", "source_field", "json_path"):
                if not _text(row.get(key)) and inherited_context.get(key):
                    row[key] = inherited_context[key]
        if row_type == "event_value":
            last_value_context = {
                "row_type": "event_value",
                "field_name": _text(row.get("field_name")),
                "field_display_name": _text(row.get("field_display_name")),
                "field_role": _text(row.get("field_role")),
                "semantic_type": _text(row.get("semantic_type")),
                "field_type": _text(row.get("field_type")),
                "source_field": _text(row.get("source_field")),
                "json_path": _text(row.get("json_path")),
            }
            event = _event_mapping(row)
            if event:
                _append_event_mapping(editor.event_name_mappings, event)
            _apply_event_field_defaults(
                editor,
                table_name,
                _text(row.get("field_name")),
            )
            continue

        if row_type == "field_value":
            last_value_context = {
                "row_type": "field_value",
                "field_name": _text(row.get("field_name")),
                "field_display_name": _text(row.get("field_display_name")),
                "field_role": _text(row.get("field_role")),
                "semantic_type": _text(row.get("semantic_type")),
                "field_type": _text(row.get("field_type")),
                "source_field": _text(row.get("source_field")),
                "json_path": _text(row.get("json_path")),
            }
            _append_field_value_mapping(
                editor,
                table_name,
                _text(row.get("field_name")),
                _text(row.get("value")),
                _text(row.get("value_display_name")),
                _text(row.get("value_category")),
                _text(row.get("description")),
                row.get("aliases"),
            )
            continue

        if row_type == "event":
            last_value_context = {}
            last_field_context = {}
            event = _event_mapping(row)
            if event:
                _append_event_mapping(editor.event_name_mappings, event)
            _apply_event_field_defaults(
                editor,
                table_name,
                _text(row.get("field_name")),
            )
            continue

        if row_type in {"physical_field", "dictionary_field"}:
            last_value_context = {}
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
                last_field_context = {
                    "field_name": field_item.field_name,
                    "field_display_name": _first_alias(field_item),
                    "field_role": field_item.field_role or "",
                    "semantic_type": field_item.semantic_type or "",
                    "field_type": field_item.semantic_type or _text(row.get("field_type")),
                    "source_field": field_item.source_field or field_item.field_name if row_type == "physical_field" else field_item.source_field or "",
                    "json_path": field_item.json_path or "",
                }
                if _text(field_item.field_role).lower() == "event_name":
                    _apply_event_field_defaults(editor, table_name, field_item.field_name)
                event_name = _text(row.get("event_name"))
                if event_name:
                    event = {
                        "event_name": event_name,
                        "event_display_name": _text(row.get("event_display_name")),
                        "event_category": _text(row.get("event_category")),
                    }
                    _append_event_mapping(editor.event_name_mappings, event, _property_from_field_item(field_item, row))
            continue

        _add_warning(warnings, f"{table_name} sheet 中存在未知 row_type={row_type}，已跳过。")


def _is_attribute_sheet(rows: list[dict[str, Any]]) -> bool:
    return any(
        "field_name" in row
        and "field_type" in row
        and ("update_mode" in row or "field_category" in row)
        and not _text(row.get("row_type"))
        for row in rows
    )


def _has_legacy_row_type(rows: list[dict[str, Any]]) -> bool:
    return any(_text(row.get("row_type")) for row in rows)


def _parse_attribute_sheet(
    rows: list[dict[str, Any]],
    table_name: str,
    editor: TenantTrackingConfigEditor,
    *,
    datasource_type: str | None,
    warnings: list[str],
    physical_schema: dict[str, PhysicalTableInfo],
) -> None:
    for row in rows:
        field_name = _text(row.get("field_name"))
        field_type = _text(row.get("field_type"))
        if not field_name:
            _add_warning(warnings, f"{table_name} 属性表中有一行缺少属性名，已跳过。")
            continue
        if not field_type:
            _add_warning(warnings, f"{table_name}.{field_name} 缺少属性类型，已跳过。")
            continue
        inferred_source, _ = _json_path_from_field_name(field_name)
        row_type = "dictionary_field" if inferred_source else "physical_field"
        normalized_row = dict(row)
        normalized_row["semantic_type"] = _semantic_type(field_type)
        field_item = _field_item(
            normalized_row,
            table_name,
            row_type=row_type,
            datasource_type=datasource_type,
            warnings=warnings,
            physical_schema=physical_schema,
        )
        if field_item:
            editor.fields.append(field_item)
            table_key = table_name.lower()
            field_key = field_item.field_name.lower()
            if table_key == "event":
                if not editor.default_event_table:
                    editor.default_event_table = table_name
                if field_key in {"event", "event_name", "event_type"} and not editor.default_event_name_field:
                    editor.default_event_name_field = field_item.field_name
                if field_key in {"uid", "user_id", "userid", "role_id", "player_id"} and not editor.default_subject_field:
                    editor.default_subject_field = field_item.field_name
                if field_key in {"time", "event_time", "event_timestamp", "timestamp", "created_at"} and not editor.default_event_time_field:
                    editor.default_event_time_field = field_item.field_name


def _parse_event_parameter_mapping_sheet(
    rows: list[dict[str, Any]],
    editor: TenantTrackingConfigEditor,
    warnings: list[str],
) -> None:
    last_event: dict[str, Any] | None = None
    last_source_field = ""
    for row in rows:
        event_name = _text(row.get("event_name"))
        if not event_name:
            if not last_event:
                _add_warning(warnings, "事件参数对照 sheet 中有一行缺少事件名，已跳过。")
                continue
            event = dict(last_event)
        else:
            event = {
                "event_name": event_name,
                "event_display_name": _text(row.get("event_display_name")),
                "event_category": _text(row.get("event_category")),
                "collect_side": _text(row.get("collect_side")),
                "description": _first_text(row.get("event_description"), row.get("description_2")),
            }
            event = {key: value for key, value in event.items() if value}
            last_event = dict(event)
            last_source_field = _text(row.get("source_field"))
        raw_property_name = _first_text(row.get("property_name"), row.get("field_name"))
        prop: dict[str, Any] | None = None
        if raw_property_name:
            source_value = _text(row.get("source_field")) or last_source_field or "ext"
            source_field, property_name, json_path = _split_event_parameter_source(
                source_value,
                raw_property_name,
                row.get("json_path"),
            )
            internal_name = f"{source_field}.{property_name}" if source_field and property_name else property_name
            prop = {
                "property_name": internal_name,
                "property_display_name": _first_text(row.get("property_display_name"), row.get("field_display_name")),
                "property_type": _first_text(row.get("property_type"), row.get("field_type")),
                "source_field": source_field,
                "json_path": json_path,
                "description": _text(row.get("description")),
            }
            prop = {key: value for key, value in prop.items() if value}
        _append_event_mapping(editor.event_name_mappings, event, prop)


def _event_group_int(value: Any, *, row_number: int, field_name: str, default: int) -> int:
    text = _text(value)
    if not text:
        return default
    try:
        number = float(text)
    except ValueError as exc:
        raise ValueError(f"事件分组 sheet 第 {row_number} 行：{field_name}必须是整数。") from exc
    if not number.is_integer():
        raise ValueError(f"事件分组 sheet 第 {row_number} 行：{field_name}必须是整数。")
    return int(number)


def _event_group_enabled(value: Any, *, row_number: int) -> bool:
    text = _text(value).lower()
    if not text:
        return True
    if text in {"1", "y", "yes", "true", "t", "是", "启用"}:
        return True
    if text in {"0", "n", "no", "false", "f", "否", "停用"}:
        return False
    raise ValueError(f"事件分组 sheet 第 {row_number} 行：启用只能填写是或否。")


def _parse_event_group_sheet(
    rows: list[dict[str, Any]],
) -> tuple[list[TenantTrackingEventGroupBase], dict[tuple[str, str], int]]:
    grouped: dict[str, dict[str, Any]] = {}
    event_row_numbers: dict[tuple[str, str], int] = {}
    for fallback_row_number, row in enumerate(rows, start=2):
        row_number = int(row.get(EXCEL_ROW_NUMBER_KEY) or fallback_row_number)
        group_key = _text(row.get("group_key"))
        group_name = _text(row.get("group_name"))
        event_name = _text(row.get("event_name"))
        if not group_key:
            raise ValueError(f"事件分组 sheet 第 {row_number} 行：缺少分组标识。")
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,127}", group_key):
            raise ValueError(
                f"事件分组 sheet 第 {row_number} 行：分组标识必须以小写字母开头，"
                "且只能包含小写字母、数字和下划线。"
            )
        if not group_name:
            raise ValueError(f"事件分组 sheet 第 {row_number} 行：缺少分组名称。")
        if not event_name:
            raise ValueError(f"事件分组 sheet 第 {row_number} 行：缺少事件名。")

        description = _text(row.get("group_description"))
        sort_order = _event_group_int(
            row.get("group_sort_order"),
            row_number=row_number,
            field_name="分组排序",
            default=0,
        )
        event_order = _event_group_int(
            row.get("event_order"),
            row_number=row_number,
            field_name="事件排序",
            default=row_number - 1,
        )
        enabled = _event_group_enabled(row.get("enabled"), row_number=row_number)
        metadata = (group_name, description, sort_order, enabled)
        current = grouped.get(group_key)
        if current is None:
            current = {"metadata": metadata, "events": [], "seen": set()}
            grouped[group_key] = current
        elif current["metadata"] != metadata:
            raise ValueError(
                f"事件分组 sheet 第 {row_number} 行：分组 {group_key} "
                "的名称、说明、排序或启用状态与前面行不一致。"
            )
        if event_name in current["seen"]:
            raise ValueError(
                f"事件分组 sheet 第 {row_number} 行：分组 {group_key} 包含重复事件 {event_name}。"
            )
        current["seen"].add(event_name)
        current["events"].append((event_order, row_number, event_name))
        event_row_numbers[(group_key, event_name)] = row_number

    result: list[TenantTrackingEventGroupBase] = []
    for group_key, current in grouped.items():
        group_name, description, sort_order, enabled = current["metadata"]
        try:
            result.append(
                TenantTrackingEventGroupBase(
                    group_key=group_key,
                    group_name=group_name,
                    description=description or None,
                    event_names=[
                        event_name
                        for _event_order, _row_number, event_name in sorted(current["events"])
                    ],
                    sort_order=sort_order,
                    enabled=enabled,
                )
            )
        except Exception as exc:
            raise ValueError(f"事件分组 {group_key} 配置无效：{exc}") from exc
    return sorted(result, key=lambda item: (item.sort_order, item.group_key)), event_row_numbers


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
    profile = GENERIC_PROFILE
    imported = TenantTrackingConfigEditor(
        enabled=True,
        tables=[],
        fields=[],
        event_name_mappings=[],
    )
    sheet_to_table: dict[str, str] = {}
    event_group_row_numbers: dict[tuple[str, str], int] = {}

    if INFO_SHEET in excel.sheet_names:
        rows, skipped = _read_sheet_rows(excel, INFO_SHEET)
        skipped_rows += skipped
        _parse_info_sheet(rows, imported, warnings)

    if TABLE_MAP_SHEET in excel.sheet_names:
        rows, skipped = _read_sheet_rows(excel, TABLE_MAP_SHEET)
        skipped_rows += skipped
        sheet_to_table = _parse_table_map(rows, imported, warnings)

    if SQL_RULE_SHEET in excel.sheet_names:
        rows, skipped = _read_sheet_rows(excel, SQL_RULE_SHEET)
        skipped_rows += skipped
        imported.sql_rules = _parse_sql_rules(rows) or None

    if EVENT_PARAMETER_MAPPING_SHEET in excel.sheet_names:
        rows, skipped = _read_sheet_rows(excel, EVENT_PARAMETER_MAPPING_SHEET)
        skipped_rows += skipped
        _parse_event_parameter_mapping_sheet(rows, imported, warnings)

    if EVENT_GROUP_SHEET in excel.sheet_names:
        rows, skipped = _read_sheet_rows(
            excel,
            EVENT_GROUP_SHEET,
            require_recognized_header=True,
            include_row_number=True,
        )
        skipped_rows += skipped
        if rows:
            imported.event_groups, event_group_row_numbers = _parse_event_group_sheet(rows)

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
        if _is_attribute_table(table_name):
            if _is_attribute_sheet(rows):
                _parse_attribute_sheet(
                    rows,
                    table_name,
                    imported,
                    datasource_type=datasource_type,
                    warnings=warnings,
                    physical_schema=schema,
                )
            else:
                detail = "旧 row_type 格式" if _has_legacy_row_type(rows) else "未知格式"
                _add_warning(
                    warnings,
                    f"{table_name} sheet 使用{detail}，已跳过；event/user 表请使用属性名、属性显示名、属性类型、更新方式、属性说明、属性标签格式。",
                )
        else:
            _parse_generic_business_sheet(
                rows,
                table_name,
                imported,
                datasource_type=datasource_type,
                warnings=warnings,
                physical_schema=schema,
            )

    if not imported.tables and not imported.fields and not imported.event_name_mappings:
        raise ValueError("Excel 中没有可识别的表、字段或事件配置，请使用平台导出的物理表 sheet 格式。")

    known_tables = set(schema.keys())
    if known_tables:
        for table in imported.tables:
            if table.table_name not in known_tables:
                _add_warning(
                    warnings,
                    f"{table.table_name} 不在当前绑定数据源 schema 中，配置会保存但不会出现在图表字段列表里。",
                )

    normalized = _dedupe_imported_tracking_config(imported)
    groups_to_validate = normalized.event_groups or list(existing.event_groups or [])
    if groups_to_validate:
        known_event_names = {
            event_name
            for mapping in normalized.event_name_mappings or []
            for event_name in _event_names_from_mapping(mapping)
        }
        for group in normalized.event_groups or []:
            for event_name in group.event_names:
                if event_name in known_event_names:
                    continue
                row_number = event_group_row_numbers.get((group.group_key, event_name))
                if row_number is not None:
                    raise ValueError(
                        f"事件分组 sheet 第 {row_number} 行：分组 {group.group_key} "
                        f"引用的事件 {event_name} 不存在于当前事件参数字典。"
                    )
        validate_tracking_event_groups(groups_to_validate, normalized.event_name_mappings)
    return ParsedTrackingConfig(editor=normalized, profile=profile, warnings=warnings, skipped_rows=skipped_rows)


def import_summary(parsed: ParsedTrackingConfig) -> TenantTrackingImportSummary:
    return TenantTrackingImportSummary(
        profile=parsed.profile,
        table_count=len(parsed.editor.tables or []),
        field_count=len(parsed.editor.fields or []),
        event_count=len(parsed.editor.event_name_mappings or []),
        event_group_count=len(parsed.editor.event_groups or []),
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
    return


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
    expression = "" if source_field and json_path else field_item.expression or ""
    row = {
        "row_type": row_type,
        "field_name": field_item.field_name,
        "field_display_name": _first_alias(field_item),
        "field_type": field_item.semantic_type or "",
        "field_role": field_item.field_role or "",
        "semantic_type": field_item.semantic_type or "",
        "source_field": source_field,
        "json_path": json_path,
        "expression": expression,
        "required": "Y" if field_item.required else "",
        "value": "",
        "value_display_name": "",
        "value_category": "",
        "collect_side": "",
        "event_name": "",
        "event_display_name": "",
        "event_category": "",
        "example_values": "\n".join(str(item) for item in field_item.example_values or []),
        "description": field_item.field_comment or "",
        "ai_notes": field_item.ai_notes or "",
        "aliases": _aliases_text(field_item),
    }
    row.update(_extra_properties(field_item))
    return row


def _semantic_type_for_export(field_item: Any, physical_type: str = "") -> str:
    field_role = _text(getattr(field_item, "field_role", None)).lower()
    semantic_type = _text(getattr(field_item, "semantic_type", None)).lower()
    if field_role == "event_name":
        return "text"
    return semantic_type or _semantic_type(physical_type)


def _business_field_sort_key(field_item: Any) -> tuple[str, str, str]:
    source = _text(getattr(field_item, "source_field", ""))
    json_path = _text(getattr(field_item, "json_path", ""))
    view_key = source if source and json_path else ""
    return (view_key, _text(getattr(field_item, "field_name", "")), _text(getattr(field_item, "semantic_type", "")))


def _event_aliases_from_mapping(item: Any, event_name: str) -> str:
    if not isinstance(item, dict):
        return ""
    aliases = item.get("aliases")
    if isinstance(aliases, dict):
        return "\n".join(_text(alias) for alias in aliases.get(event_name, []) if _text(alias))
    if isinstance(aliases, list):
        return "\n".join(_text(alias) for alias in aliases if _text(alias))
    return _text(aliases)


def _business_event_value_rows(config: TenantTrackingConfigDTO, *, event_field: str) -> list[dict[str, Any]]:
    event_field = event_field or "event"
    rows: list[dict[str, Any]] = []
    for mapping in config.event_name_mappings or []:
        if not isinstance(mapping, dict):
            continue
        for event_name in _event_names_from_mapping(mapping):
            rows.append({
                "row_type": "event_value",
                "field_name": event_field,
                "field_display_name": "",
                "field_type": "",
                "field_role": "event_name",
                "semantic_type": "text",
                "source_field": "",
                "json_path": "",
                "expression": "",
                "required": "",
                "value": event_name,
                "value_display_name": _event_display_from_mapping(mapping, event_name),
                "value_category": _event_category_from_mapping(mapping),
                "collect_side": _event_collect_side_from_mapping(mapping),
                "event_name": "",
                "event_display_name": "",
                "event_category": "",
                "example_values": "",
                "description": _event_description_from_mapping(mapping),
                "ai_notes": _text(mapping.get("ai_notes")),
                "aliases": _event_aliases_from_mapping(mapping, event_name),
            })
    return rows


def _business_event_property_rows(config: TenantTrackingConfigDTO) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for mapping in config.event_name_mappings or []:
        if not isinstance(mapping, dict):
            continue
        properties = mapping.get("properties")
        if not isinstance(properties, list):
            continue
        event_names = _event_names_from_mapping(mapping)
        event_name = event_names[0] if event_names else _text(mapping.get("event_name"))
        for prop in properties:
            if not isinstance(prop, dict):
                continue
            prop_name = _first_text(prop.get("property_name"), prop.get("field_name"), prop.get("name"))
            if not prop_name:
                continue
            source_field = _text(prop.get("source_field"))
            json_path = _normalize_json_path(_text(prop.get("json_path")))
            if not source_field:
                inferred_source, inferred_path = _json_path_from_field_name(prop_name)
                source_field = inferred_source
                json_path = json_path or inferred_path
            expression = "" if source_field and json_path else _text(prop.get("expression"))
            exported_field_name = prop_name
            if source_field and json_path and not prop_name.startswith(f"{source_field}."):
                child_name = _json_child_name(source_field, prop_name, json_path)
                if child_name:
                    exported_field_name = f"{source_field}.{child_name}"
            rows.append({
                "row_type": "dictionary_field",
                "field_name": exported_field_name,
                "field_display_name": _first_text(prop.get("property_display_name"), prop.get("display_name"), prop.get("label")),
                "field_type": _first_text(prop.get("property_type"), prop.get("field_type"), prop.get("type")),
                "field_role": _first_text(prop.get("field_role"), "json_path_metric" if _normalize_type(prop.get("property_type")) == "number" else "json_path_dimension"),
                "semantic_type": _semantic_type(_first_text(prop.get("semantic_type"), prop.get("property_type"), prop.get("field_type"), prop.get("type"))),
                "source_field": source_field,
                "json_path": json_path,
                "expression": expression,
                "required": "Y" if _parse_bool(prop.get("required")) else "",
                "value": "",
                "value_display_name": "",
                "value_category": "",
                "collect_side": "",
                "event_name": event_name,
                "event_display_name": _event_display_from_mapping(mapping, event_name) if event_name else "",
                "event_category": _event_category_from_mapping(mapping),
                "example_values": "\n".join(str(item) for item in prop.get("example_values", []) if _text(item)) if isinstance(prop.get("example_values"), list) else _text(prop.get("example_values")),
                "description": _first_text(prop.get("description"), prop.get("ai_notes")),
                "ai_notes": _text(prop.get("ai_notes")),
                "aliases": "\n".join(str(item) for item in prop.get("aliases", []) if _text(item)) if isinstance(prop.get("aliases"), list) else "",
            })
    return rows


def _split_event_parameter_source(
    source_field: Any,
    property_name: Any,
    json_path: Any = "",
) -> tuple[str, str, str]:
    source = _text(source_field)
    name = _text(property_name)
    path = _normalize_json_path(_text(json_path))
    inferred_source, inferred_path = _json_path_from_field_name(name)
    if inferred_source:
        source = source or inferred_source
        name = name.split(".", 1)[1]
    if path:
        child_name = _json_child_name(source, name, path)
        if child_name:
            name = child_name
    elif name:
        path = _normalize_json_path(name)
    return source, name, path


def _event_parameter_mapping_rows(config: TenantTrackingConfigDTO) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    emitted: set[tuple[str, str, str]] = set()
    for mapping in config.event_name_mappings or []:
        if not isinstance(mapping, dict):
            continue
        event_names = _event_names_from_mapping(mapping)
        if not event_names:
            continue
        properties = mapping.get("properties")
        property_rows = properties if isinstance(properties, list) and properties else [None]
        for event_name in event_names:
            for prop in property_rows:
                prop_dict = prop if isinstance(prop, dict) else {}
                raw_property_name = _first_text(
                    prop_dict.get("property_name"),
                    prop_dict.get("field_name"),
                    prop_dict.get("name"),
                )
                source_field, property_name, _ = _split_event_parameter_source(
                    prop_dict.get("source_field"),
                    raw_property_name,
                    prop_dict.get("json_path"),
                )
                key = (event_name, source_field, property_name)
                if key in emitted:
                    continue
                emitted.add(key)
                rows.append({
                    "event_name": event_name,
                    "event_display_name": _event_display_from_mapping(mapping, event_name),
                    "event_description": _event_description_from_mapping(mapping),
                    "event_category": _event_category_from_mapping(mapping),
                    "collect_side": _event_collect_side_from_mapping(mapping),
                    "source_field": source_field,
                    "property_name": property_name,
                    "property_display_name": _first_text(
                        prop_dict.get("property_display_name"),
                        prop_dict.get("display_name"),
                        prop_dict.get("label"),
                    ),
                    "property_type": _attribute_type_label(
                        prop_dict.get("property_type"),
                        prop_dict.get("semantic_type"),
                        prop_dict.get("field_type"),
                        prop_dict.get("type"),
                    ) if prop_dict else "",
                    "description": _first_text(prop_dict.get("description"), prop_dict.get("ai_notes")),
                })
    return rows


def _event_group_rows(config: TenantTrackingConfigDTO) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    groups = sorted(
        config.event_groups or [],
        key=lambda item: (int(getattr(item, "sort_order", 0) or 0), _text(getattr(item, "group_key", ""))),
    )
    for group in groups:
        event_names = [_text(name) for name in getattr(group, "event_names", []) if _text(name)]
        for event_order, event_name in enumerate(event_names, start=1):
            rows.append(
                {
                    "group_key": _text(getattr(group, "group_key", "")),
                    "group_name": _text(getattr(group, "group_name", "")),
                    "group_description": _text(getattr(group, "description", "")),
                    "group_sort_order": int(getattr(group, "sort_order", 0) or 0),
                    "event_name": event_name,
                    "event_order": event_order,
                    "enabled": "是" if bool(getattr(group, "enabled", True)) else "否",
                }
            )
    return rows


def _field_value_rows(field_item: Any) -> list[dict[str, Any]]:
    values = getattr(field_item, "value_mappings", None)
    if not isinstance(values, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in values:
        value = ""
        display_name = ""
        category = ""
        description = ""
        aliases = ""
        if isinstance(item, dict):
            value = _first_text(item.get("value"), item.get("name"), item.get("key"))
            display_name = _first_text(item.get("display_name"), item.get("label"), item.get("name"))
            category = _first_text(item.get("category"), item.get("metric"))
            description = _first_text(item.get("description"), item.get("ai_notes"))
            aliases = "\n".join(str(alias) for alias in item.get("aliases", []) if _text(alias)) if isinstance(item.get("aliases"), list) else _text(item.get("aliases"))
        else:
            value_text = _text(item)
            if "=" in value_text:
                value, display_name = [part.strip() for part in value_text.split("=", 1)]
            else:
                value = value_text
        if not value:
            continue
        rows.append({
            "row_type": "field_value",
            "field_name": getattr(field_item, "field_name", ""),
            "field_display_name": _first_alias(field_item),
            "field_type": "",
            "field_role": getattr(field_item, "field_role", "") or "",
            "semantic_type": getattr(field_item, "semantic_type", "") or "",
            "source_field": "",
            "json_path": "",
            "expression": "",
            "required": "",
            "value": value,
            "value_display_name": display_name,
            "value_category": category,
            "collect_side": "",
            "event_name": "",
            "event_display_name": "",
            "event_category": "",
            "example_values": "",
            "description": description,
            "ai_notes": "",
            "aliases": aliases,
        })
    return rows


VALUE_ROW_CONTEXT_COLUMNS = (
    "row_type",
    "field_name",
    "field_display_name",
    "field_type",
    "field_role",
    "semantic_type",
    "source_field",
    "json_path",
    "expression",
    "required",
)


def _source_field_from_row(row: dict[str, Any]) -> str:
    source_field = _text(row.get("source_field"))
    if source_field:
        return source_field
    inferred_source, _ = _json_path_from_field_name(_text(row.get("field_name")))
    return inferred_source


def _append_and_mark(result: list[dict[str, Any]], emitted: set[int], row: dict[str, Any]) -> None:
    row_id = id(row)
    if row_id in emitted:
        return
    emitted.add(row_id)
    result.append(row)


def _organize_business_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    physical_rows: list[dict[str, Any]] = []
    dictionary_by_source: dict[str, list[dict[str, Any]]] = {}
    dictionary_without_source: list[dict[str, Any]] = []
    event_values_by_field: dict[str, list[dict[str, Any]]] = {}
    field_values_by_field: dict[str, list[dict[str, Any]]] = {}
    remaining_rows: list[dict[str, Any]] = []

    for row in rows:
        row_type = _text(row.get("row_type"))
        field_name = _text(row.get("field_name"))
        if row_type == "physical_field":
            physical_rows.append(row)
        elif row_type == "dictionary_field":
            source_field = _source_field_from_row(row)
            if source_field:
                dictionary_by_source.setdefault(source_field, []).append(row)
            else:
                dictionary_without_source.append(row)
        elif row_type == "event_value":
            event_values_by_field.setdefault(field_name, []).append(row)
        elif row_type == "field_value":
            field_values_by_field.setdefault(field_name, []).append(row)
        else:
            remaining_rows.append(row)

    result: list[dict[str, Any]] = []
    emitted: set[int] = set()

    def emit_values(field_name: str) -> None:
        for value_row in field_values_by_field.pop(field_name, []):
            _append_and_mark(result, emitted, value_row)

    def emit_dictionary(row: dict[str, Any]) -> None:
        _append_and_mark(result, emitted, row)
        emit_values(_text(row.get("field_name")))

    for physical_row in physical_rows:
        field_name = _text(physical_row.get("field_name"))
        _append_and_mark(result, emitted, physical_row)
        for event_value_row in event_values_by_field.pop(field_name, []):
            _append_and_mark(result, emitted, event_value_row)
        emit_values(field_name)
        for dictionary_row in dictionary_by_source.pop(field_name, []):
            emit_dictionary(dictionary_row)

    for event_group in list(event_values_by_field.values()):
        for event_value_row in event_group:
            _append_and_mark(result, emitted, event_value_row)
    event_values_by_field.clear()

    for dictionary_group in list(dictionary_by_source.values()):
        for dictionary_row in dictionary_group:
            emit_dictionary(dictionary_row)
    dictionary_by_source.clear()

    for dictionary_row in dictionary_without_source:
        emit_dictionary(dictionary_row)

    for value_group in list(field_values_by_field.values()):
        for value_row in value_group:
            _append_and_mark(result, emitted, value_row)
    field_values_by_field.clear()

    for row in remaining_rows:
        _append_and_mark(result, emitted, row)
    return result


def _compact_value_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    last_value_key: tuple[str, str, str, str] | None = None
    last_dictionary_source = ""
    for row in rows:
        row_type = _text(row.get("row_type"))
        field_name = _text(row.get("field_name"))
        source_field = _source_field_from_row(row)
        json_path = _text(row.get("json_path"))
        if row_type == "dictionary_field":
            compact_row = dict(row)
            if source_field and last_dictionary_source == source_field:
                compact_row["row_type"] = ""
                compact_row["source_field"] = ""
            result.append(compact_row)
            last_dictionary_source = source_field
            last_value_key = None
            continue
        if row_type in {"event_value", "field_value"}:
            value_key = (row_type, field_name, source_field, json_path)
            compact_row = dict(row)
            if last_value_key == value_key:
                for column in VALUE_ROW_CONTEXT_COLUMNS:
                    compact_row[column] = ""
            result.append(compact_row)
            last_value_key = value_key
            continue
        result.append(row)
        last_value_key = None
        if row_type == "physical_field":
            last_dictionary_source = ""
    return result


TRACKING_INFO_COLUMNS = ["项目", "说明"]


def _event_names_from_mapping(item: Any) -> list[str]:
    if not isinstance(item, dict):
        text = _text(item)
        return [text] if text else []
    names: list[str] = []
    for key in ("event_name", "eventName", "name", "value"):
        text = _text(item.get(key))
        if text:
            names.append(text)
    events = item.get("events")
    if isinstance(events, list):
        names.extend(_text(value) for value in events if _text(value))
    return _merge_list([], names)


def _event_display_from_mapping(item: Any, event_name: str) -> str:
    if not isinstance(item, dict):
        return event_name
    return _first_text(
        item.get("event_display_name"),
        item.get("display_name"),
        item.get("metric"),
        item.get("name"),
        event_name,
    )


def _event_description_from_mapping(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    return _first_text(item.get("description"), item.get("event_description"), item.get("ai_notes"))


def _event_category_from_mapping(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    return _first_text(item.get("event_category"), item.get("category"), item.get("metric"))


def _event_collect_side_from_mapping(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    return _text(item.get("collect_side"))


def _tracking_table_comment(table_item: Any, table_info: PhysicalTableInfo | None = None) -> str:
    return (
        _text(getattr(table_item, "table_comment", None))
        or (table_info.custom_comment if table_info else "")
        or (table_info.table_comment if table_info else "")
    )


def _table_role(table_item: Any) -> str:
    return _text(getattr(table_item, "table_role", None)).lower()


def _resolve_export_event_table(config: TenantTrackingConfigDTO, all_table_names: list[str]) -> str:
    if config.default_event_table:
        return config.default_event_table
    table_map = _config_table_map(config)
    for table_name, table_item in table_map.items():
        role = _table_role(table_item)
        if role in {"event", "event_fact", "fact_event", "fact_events"}:
            return table_name
    for candidate in ("event", "events", "fact_events"):
        if candidate in all_table_names:
            return candidate
    return all_table_names[0] if all_table_names else "event"


def _resolve_export_field_by_role(config: TenantTrackingConfigDTO, table_name: str, role: str) -> str:
    role = role.lower()
    for field_item in config.fields or []:
        if field_item.table_name != table_name:
            continue
        if _text(getattr(field_item, "field_role", None)).lower() == role:
            return field_item.field_name
    return ""


def _physical_field_name(schema: dict[str, PhysicalTableInfo], table_name: str, candidates: Iterable[str]) -> str:
    table_info = schema.get(table_name)
    if not table_info:
        return ""
    by_lower = {
        _text(field_info.field_name).lower(): field_info.field_name
        for field_info in table_info.fields
        if _text(field_info.field_name)
    }
    for candidate in candidates:
        field_name = by_lower.get(candidate.lower())
        if field_name:
            return field_name
    return ""


def _resolve_export_event_field(
    config: TenantTrackingConfigDTO,
    event_table: str,
    schema: dict[str, PhysicalTableInfo],
) -> str:
    return (
        _text(config.default_event_name_field)
        or _resolve_export_field_by_role(config, event_table, "event_name")
        or _physical_field_name(schema, event_table, ("event", "event_name", "event_type"))
        or "event"
    )


def _resolve_export_subject_field(config: TenantTrackingConfigDTO, event_table: str, schema: dict[str, PhysicalTableInfo]) -> str:
    return (
        _text(config.default_subject_field)
        or _resolve_export_field_by_role(config, event_table, "subject_id")
        or _physical_field_name(schema, event_table, ("uid", "user_id", "userid", "role_id", "player_id"))
    )


def _resolve_export_event_time_field(config: TenantTrackingConfigDTO, event_table: str, schema: dict[str, PhysicalTableInfo]) -> str:
    return (
        _text(config.default_event_time_field)
        or _resolve_export_field_by_role(config, event_table, "event_time")
        or _physical_field_name(schema, event_table, ("time", "event_time", "event_timestamp", "timestamp", "created_at"))
    )


def _resolve_export_user_table(config: TenantTrackingConfigDTO, all_table_names: list[str], event_table: str) -> str:
    table_map = _config_table_map(config)
    for table_name, table_item in table_map.items():
        role = _table_role(table_item)
        if role in {"subject", "subject_profile", "daily_user_snapshot", "user", "profile", "profile_table", "user_profile"}:
            return table_name
    for candidate in ("user", "users", "profile", "subject_profile"):
        if candidate in all_table_names and candidate != event_table:
            return candidate
    for table_name in all_table_names:
        if table_name != event_table:
            return table_name
    return "user"


def _is_attribute_table(table_name: str) -> bool:
    return _text(table_name).lower() in {"event", "user"}


def _field_category(field_item: Any) -> str:
    return _text(getattr(field_item, "category", None))


def _attribute_row_from_field(
    *,
    field_name: str,
    display_name: str = "",
    field_type: str = "",
    description: str = "",
    update_mode: str = "",
    category: str = "",
    extra_properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "field_name": field_name,
        "field_display_name": display_name,
        "field_type": _attribute_type_label(field_type),
        "update_mode": update_mode,
        "description": description,
        "field_category": category,
    }
    row.update(extra_properties or {})
    return row


def _attribute_sheet_rows_for_table(
    table_name: str,
    *,
    physical_fields: list[PhysicalFieldInfo],
    field_map: dict[tuple[str, str], Any],
    template_only: bool,
) -> list[dict[str, Any]]:
    physical_names = {field_info.field_name for field_info in physical_fields}
    rows: list[dict[str, Any]] = []
    for field_info in physical_fields:
        configured = field_map.get((table_name, field_info.field_name))
        if configured and not template_only:
            rows.append(_attribute_row_from_field(
                field_name=configured.field_name,
                display_name=_first_alias(configured),
                field_type=getattr(configured, "semantic_type", None) or field_info.field_type,
                description=getattr(configured, "field_comment", None) or field_info.custom_comment or field_info.field_comment,
                update_mode=_text(getattr(configured, "update_mode", None)),
                category=_field_category(configured),
                extra_properties=_extra_properties(configured),
            ))
            continue
        rows.append(_attribute_row_from_field(
            field_name=field_info.field_name,
            field_type=_semantic_type(field_info.field_type),
            description=field_info.custom_comment or field_info.field_comment,
        ))

    if not template_only:
        configured_fields = [
            configured
            for (field_table, _), configured in field_map.items()
            if field_table == table_name and configured.field_name not in physical_names
        ]
        for configured in sorted(configured_fields, key=_business_field_sort_key):
            rows.append(_attribute_row_from_field(
                field_name=configured.field_name,
                display_name=_first_alias(configured),
                field_type=getattr(configured, "semantic_type", None),
                description=getattr(configured, "field_comment", None),
                update_mode=_text(getattr(configured, "update_mode", None)),
                category=_field_category(configured),
                extra_properties=_extra_properties(configured),
            ))
    return rows


def _append_table_map_defaults(
    table_rows: list[dict[str, Any]],
    *,
    sheet_name: str,
    table_name: str,
    table_item: Any | None,
    table_info: PhysicalTableInfo | None,
    table_role: str,
    subject_field: str = "",
    event_name_field: str = "",
    event_time_field: str = "",
) -> None:
    if not table_name:
        return
    row = {
        "sheet_name": sheet_name,
        "table_name": table_name,
        "table_display_name": _first_alias(table_item) if table_item else "",
        "table_role": _text(getattr(table_item, "table_role", None)) if table_item else table_role,
        "subject_field": subject_field,
        "event_name_field": event_name_field,
        "event_time_field": event_time_field,
        "partition_field": "",
        "table_comment": _tracking_table_comment(table_item, table_info),
        "ai_notes": _text(getattr(table_item, "ai_notes", None)) if table_item else "",
        "aliases": _aliases_text(table_item) if table_item else "",
    }
    row.update(_extra_properties(table_item))
    table_rows.append(row)


def _info_rows(
    config: TenantTrackingConfigDTO,
    *,
    event_table: str,
    user_table: str,
    subject_field: str,
    event_field: str,
    event_time_field: str,
) -> list[dict[str, Any]]:
    return [
        {"项目": "用途", "说明": "本 Excel 是当前项目的数据字典维护文件；导入后会影响 Smart Q&A、分析助手、看板/图表配置和图表解读。"},
        {"项目": "主维护入口", "说明": "每个物理表一个同名 sheet。字段、JSON 子字段、字段取值、事件取值都在对应物理表 sheet 中维护。"},
        {"项目": "行类型", "说明": "physical_field=物理字段；dictionary_field=JSON/派生字典字段；event_value=事件名字段的业务事件取值；field_value=普通字段枚举/值域。"},
        {"项目": "分组维护", "说明": "同一字段下面的后续取值行可以省略 row_type/field_name/字段角色/语义类型等上下文，导入时会继承上一条 event_value 或 field_value。"},
        {"项目": "事件取值", "说明": f"`{event_table}` sheet 中 field_name={event_field or 'event'} 且 row_type=event_value 的行，会写入事件字典；后续同字段事件值可只维护 value、中文名、标签、说明、别名。"},
        {"项目": "JSON 字段", "说明": "JSON 容器字段下面可维护 dictionary_field 子字段；紧跟 physical_field=ext/userinfo 等容器时，子字段可省略 source_field。字段取值紧跟子字段时，可用 field_value 维护 1/3/4 等枚举含义。"},
        {"项目": "图表配置", "说明": "导入后的字段会出现在图表 SQL 构建器字段下拉中；JSON 字段请维护 source_field、json_path 和 semantic_type，SQL 表达式会在运行时按当前数据源方言生成。"},
        {"项目": "SQL 规则", "说明": "`_SQL规则` 中维护跨字段口径、时间窗口、留存/漏斗等复杂规则；不要把复杂业务口径硬编码进平台。"},
        {"项目": "当前默认", "说明": f"事件表={event_table}；主体字段={subject_field or ''}；事件名字段={event_field or ''}；事件时间字段={event_time_field or ''}。"},
        {"项目": "config.enabled", "说明": "Y" if config.enabled else "N"},
        {"项目": "config.notes", "说明": config.notes or ""},
        {"项目": "config.field_role_mappings", "说明": _json_text(config.field_role_mappings)},
    ]


def _user_id_rows(config: TenantTrackingConfigDTO) -> list[dict[str, Any]]:
    return [
        {
            "subject_type": "当前项目",
            "property_name": config.default_subject_field or "uid",
            "property_display_name": "用户ID",
            "description": "当前工作空间默认主体字段；事件人数、活跃人数、参与人数等通常按该字段去重。",
            "ai_notes": "如一个项目存在账号、角色、设备等多 ID，请在此说明主分析主体，并在字段字典中补充其他 ID 字段。",
        }
    ]


def _generic_sheet_rows_for_table(
    table_name: str,
    *,
    physical_fields: list[PhysicalFieldInfo],
    field_map: dict[tuple[str, str], Any],
    template_only: bool,
) -> list[dict[str, Any]]:
    physical_names = {field_info.field_name for field_info in physical_fields}
    rows: list[dict[str, Any]] = []
    for field_info in physical_fields:
        configured = field_map.get((table_name, field_info.field_name))
        if configured and not template_only:
            row = _business_row_from_field(configured, row_type="physical_field")
            row["field_type"] = field_info.field_type or row["field_type"]
            row["semantic_type"] = _semantic_type_for_export(configured, field_info.field_type)
            row["description"] = row["description"] or field_info.custom_comment or field_info.field_comment
            rows.append(row)
        else:
            rows.append({
                "row_type": "physical_field",
                "field_name": field_info.field_name,
                "field_display_name": "",
                "field_type": field_info.field_type,
                "field_role": "",
                "semantic_type": _semantic_type(field_info.field_type),
                "source_field": "",
                "json_path": "",
                "expression": "",
                "required": "",
                "value": "",
                "value_display_name": "",
                "value_category": "",
                "collect_side": "",
                "event_name": "",
                "event_display_name": "",
                "event_category": "",
                "example_values": "",
                "description": field_info.custom_comment or field_info.field_comment,
                "ai_notes": "",
            })
        configured_for_values = field_map.get((table_name, field_info.field_name))
        if configured_for_values and not template_only:
            rows.extend(_field_value_rows(configured_for_values))
    if not template_only:
        configured_fields = [
            configured
            for (field_table, _), configured in field_map.items()
            if field_table == table_name and configured.field_name not in physical_names
        ]
        for configured in sorted(configured_fields, key=_business_field_sort_key):
            rows.append(_business_row_from_field(configured, row_type="dictionary_field"))
            rows.extend(_field_value_rows(configured))
    return rows


def _json_source_field_for_template(physical_fields: list[PhysicalFieldInfo]) -> str:
    for field_info in physical_fields:
        text = f"{field_info.field_name} {field_info.field_type} {field_info.field_comment} {field_info.custom_comment}".lower()
        if "json" in text:
            return field_info.field_name
    return ""


def _template_example_rows(
    *,
    event_field: str,
    json_source_field: str,
) -> list[dict[str, Any]]:
    source_field = json_source_field or "ext"
    return [
        {
            "row_type": "event_value",
            "field_name": event_field or "event",
            "field_display_name": "",
            "field_type": "",
            "field_role": "event_name",
            "semantic_type": "text",
            "source_field": "",
            "json_path": "",
            "expression": "",
            "required": "",
            "value": "login",
            "value_display_name": "登录",
            "value_category": "基础事件",
            "collect_side": "client",
            "event_name": "",
            "event_display_name": "",
            "event_category": "",
            "example_values": "",
            "description": "事件取值样例；把 value 改成当前项目真实上报的事件名。",
            "ai_notes": "",
            "aliases": "",
        },
        {
            "row_type": "event_value",
            "field_name": event_field or "event",
            "field_display_name": "",
            "field_type": "",
            "field_role": "event_name",
            "semantic_type": "text",
            "source_field": "",
            "json_path": "",
            "expression": "",
            "required": "",
            "value": "pay_success",
            "value_display_name": "支付成功",
            "value_category": "付费事件",
            "collect_side": "server",
            "event_name": "",
            "event_display_name": "",
            "event_category": "",
            "example_values": "",
            "description": "事件取值样例；如果没有付费事件可删除。",
            "ai_notes": "",
            "aliases": "",
        },
        {
            "row_type": "dictionary_field",
            "field_name": f"{source_field}.battleResult",
            "field_display_name": "战斗结果",
            "field_type": "text",
            "field_role": "json_path_dimension",
            "semantic_type": "text",
            "source_field": source_field,
            "json_path": "$.battleResult",
            "expression": "",
            "required": "",
            "value": "",
            "value_display_name": "",
            "value_category": "",
            "collect_side": "",
            "event_name": "battle_end",
            "event_display_name": "战斗结束",
            "event_category": "玩法事件",
            "example_values": "win\nlose",
            "description": "JSON 子字段样例；source_field 必须是当前表中承载事件参数的 JSON 字段。",
            "ai_notes": "",
            "aliases": "",
        },
        {
            "row_type": "field_value",
            "field_name": f"{source_field}.battleResult",
            "field_display_name": "战斗结果",
            "field_type": "",
            "field_role": "json_path_dimension",
            "semantic_type": "text",
            "source_field": source_field,
            "json_path": "$.battleResult",
            "expression": "",
            "required": "",
            "value": "1",
            "value_display_name": "胜利",
            "value_category": "战斗结果",
            "collect_side": "",
            "event_name": "",
            "event_display_name": "",
            "event_category": "",
            "example_values": "",
            "description": "字段取值样例；把 1/3/4 改成当前项目真实上报值。",
            "ai_notes": "",
            "aliases": "",
        },
        {
            "row_type": "field_value",
            "field_name": f"{source_field}.battleResult",
            "field_display_name": "战斗结果",
            "field_type": "",
            "field_role": "json_path_dimension",
            "semantic_type": "text",
            "source_field": source_field,
            "json_path": "$.battleResult",
            "expression": "",
            "required": "",
            "value": "3",
            "value_display_name": "失败",
            "value_category": "战斗结果",
            "collect_side": "",
            "event_name": "",
            "event_display_name": "",
            "event_category": "",
            "example_values": "",
            "description": "",
            "ai_notes": "",
            "aliases": "",
        },
    ]


def _dedupe_business_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for row in rows:
        key = (
            _text(row.get("row_type")),
            _text(row.get("field_name")),
            _text(row.get("event_name")),
            _text(row.get("value")),
            _text(row.get("json_path")),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _export_header_label(sheet_name: str, column: str, columns: list[str] | None = None) -> str:
    if columns and columns[:len(ATTRIBUTE_COLUMNS)] == ATTRIBUTE_COLUMNS and column in ATTRIBUTE_COLUMNS:
        return ATTRIBUTE_EXPORT_COLUMN_LABELS.get(column, column)
    if columns and columns[:len(EVENT_PARAMETER_MAPPING_COLUMNS)] == EVENT_PARAMETER_MAPPING_COLUMNS:
        if column == "source_field":
            return "数据源字段"
        if column == "description":
            return "属性说明"
        return EXPORT_COLUMN_LABELS.get(column, column)
    if column in BUSINESS_COLUMNS and sheet_name not in SYSTEM_SHEETS:
        return BUSINESS_EXPORT_COLUMN_LABELS.get(column, column)
    return EXPORT_COLUMN_LABELS.get(column, column)


def _write_tracking_sheet(writer, sheet_name: str, rows: list[dict[str, Any]], columns: list[str]) -> None:
    df = pd.DataFrame(rows, columns=columns)
    df.columns = [_export_header_label(sheet_name, column, columns) for column in columns]
    df.to_excel(writer, sheet_name=sheet_name, index=False)
    workbook = writer.book
    worksheet = writer.sheets[sheet_name]
    header_format = workbook.add_format({
        "bold": True,
        "bg_color": "#D9EAF7",
        "font_color": "#1F4E79",
        "border": 1,
        "align": "center",
        "valign": "vcenter",
    })
    text_format = workbook.add_format({"text_wrap": True, "valign": "top"})
    for col_index, column in enumerate(columns):
        header_label = _export_header_label(sheet_name, column, columns)
        worksheet.write(0, col_index, header_label, header_format)
        max_len = max([len(str(header_label))] + [len(str(row.get(column, ""))) for row in rows[:200]])
        min_width = EVENT_GROUP_MIN_WIDTHS.get(column, 12) if sheet_name == EVENT_GROUP_SHEET else 12
        worksheet.set_column(col_index, col_index, min(max(max_len + 2, min_width), 44), text_format)
    if columns == EVENT_PARAMETER_MAPPING_COLUMNS and rows:
        merge_format = workbook.add_format({"text_wrap": True, "valign": "top"})
        merge_columns = ["event_name", "event_display_name", "event_description", "event_category", "collect_side"]
        start_index = 0
        while start_index < len(rows):
            current_key = tuple(_text(rows[start_index].get(column)) for column in merge_columns)
            end_index = start_index + 1
            while end_index < len(rows) and tuple(_text(rows[end_index].get(column)) for column in merge_columns) == current_key:
                end_index += 1
            if current_key[0] and end_index - start_index > 1:
                first_row = start_index + 1
                last_row = end_index
                for col_index, column in enumerate(merge_columns):
                    worksheet.merge_range(first_row, col_index, last_row, col_index, rows[start_index].get(column, ""), merge_format)
            start_index = end_index
    if rows:
        worksheet.freeze_panes(1, 0)


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
        all_table_names = ["event", "user"]

    event_table = _resolve_export_event_table(config, all_table_names)
    user_table = _resolve_export_user_table(config, all_table_names, event_table)
    event_field = _resolve_export_event_field(config, event_table, schema)
    subject_field = _resolve_export_subject_field(config, event_table, schema)
    event_time_field = _resolve_export_event_time_field(config, event_table, schema)

    for table_name in all_table_names:
        sheet_name_by_table[table_name] = _safe_sheet_name(table_name, used_sheet_names)

    table_rows: list[dict[str, Any]] = []
    for table_name in all_table_names:
        sheet_name = sheet_name_by_table[table_name]
        table_info = schema.get(table_name)
        configured = table_map.get(table_name)
        row = {
            "sheet_name": sheet_name,
            "table_name": table_name,
            "table_display_name": _first_alias(configured) if configured else "",
            "table_role": getattr(configured, "table_role", "") or "",
            "subject_field": subject_field if table_name == event_table else "",
            "event_name_field": event_field if table_name == event_table else "",
            "event_time_field": event_time_field if table_name == event_table else "",
            "partition_field": "",
            "table_comment": (
                getattr(configured, "table_comment", "") or
                (table_info.custom_comment if table_info else "") or
                (table_info.table_comment if table_info else "")
            ),
            "ai_notes": getattr(configured, "ai_notes", "") or "",
            "aliases": _aliases_text(configured) if configured else "",
        }
        row.update(_extra_properties(configured))
        table_rows.append(row)

    sheets: list[tuple[str, list[dict[str, Any]], list[str]]] = [
        (
            INFO_SHEET,
            _info_rows(
                config,
                event_table=event_table,
                user_table=user_table,
                subject_field=subject_field,
                event_field=event_field,
                event_time_field=event_time_field,
            ),
            TRACKING_INFO_COLUMNS,
        ),
        (TABLE_MAP_SHEET, table_rows, _columns_with_extra(TABLE_MAP_COLUMNS, table_rows)),
        (EVENT_PARAMETER_MAPPING_SHEET, _event_parameter_mapping_rows(config), EVENT_PARAMETER_MAPPING_COLUMNS),
        (EVENT_GROUP_SHEET, _event_group_rows(config), EVENT_GROUP_COLUMNS),
    ]

    for table_name in all_table_names:
        physical_fields = schema.get(table_name).fields if schema.get(table_name) else []
        if _is_attribute_table(table_name):
            rows = _attribute_sheet_rows_for_table(
                table_name,
                physical_fields=physical_fields,
                field_map=field_map,
                template_only=template_only,
            )
            sheets.append((sheet_name_by_table[table_name], rows, _columns_with_extra(ATTRIBUTE_COLUMNS, rows)))
            continue

        rows = _generic_sheet_rows_for_table(
            table_name,
            physical_fields=physical_fields,
            field_map=field_map,
            template_only=template_only,
        )
        if not template_only and table_name == event_table:
            event_value_rows = _business_event_value_rows(config, event_field=event_field)
            event_property_rows = _business_event_property_rows(config)
            if event_value_rows or event_property_rows:
                physical_rows = [row for row in rows if row.get("row_type") == "physical_field"]
                other_rows = [row for row in rows if row.get("row_type") != "physical_field"]
                rows = physical_rows + event_value_rows + other_rows + event_property_rows
        if template_only and table_name == event_table:
            rows.extend(_template_example_rows(
                event_field=event_field,
                json_source_field=_json_source_field_for_template(physical_fields),
            ))
        rows = _dedupe_business_rows(rows)
        rows = _organize_business_rows(rows)
        sheets.append((sheet_name_by_table[table_name], rows, _columns_with_extra(BUSINESS_COLUMNS, rows)))

    sheets.extend([
        (SQL_RULE_SHEET, [{"rule_name": "示例", "scope": "", "rule_text": config.sql_rules or "", "priority": ""}] if config.sql_rules and not template_only else [], SQL_RULE_COLUMNS),
    ])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter", engine_kwargs={"options": {"strings_to_numbers": False}}) as writer:
        for sheet_name, rows, columns in sheets:
            _write_tracking_sheet(writer, sheet_name, rows, columns)
    output.seek(0)
    return io.BytesIO(output.getvalue())
