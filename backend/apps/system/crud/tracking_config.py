"""
脚本说明：这个脚本封装系统管理的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
import copy
import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete
from sqlmodel import Session, select

from apps.datasource.crud.permission_scope import bump_semantic_scope_epoch
from apps.datasource.models.datasource import CoreField, CoreTable
from apps.datasource.models.semantic_scope import SemanticScopeType
from apps.system.crud.tracking_expression import compile_tracking_json_expression
from apps.system.models.tenant import (
    TenantTrackingConfigModel,
    TenantTrackingEventGroupModel,
    TenantTrackingFieldModel,
    TenantTrackingTableModel,
)
from apps.system.schemas.tenant_schema import (
    TenantTrackingConfigDTO,
    TenantTrackingConfigEditor,
    TenantTrackingEventCatalogDTO,
    TenantTrackingEventCatalogGroup,
    TenantTrackingEventCatalogItem,
    TenantTrackingEventCatalogProperty,
    TenantTrackingEventGroupBase,
    TenantTrackingEventGroupDTO,
    TenantTrackingFieldDTO,
    TenantTrackingTableDTO,
)
from common.sql_json_paths import canonical_json_field_name, normalize_json_path
from common.utils.snowflake import snowflake
from common.utils.time import get_timestamp

TRACKING_FIELD_PROMPT_BUDGET = 16_000
_DATASOURCE_REFERENCE_PATTERN = re.compile(
    r"\bdatasource[\s_-]*id[`'\"]?\s*(?:=|:|：)\s*[`'\"]?(\d+)\b",
    flags=re.IGNORECASE,
)
_DATASOURCE_KEY_PATTERN = re.compile(r"^datasource[\s_-]*id$", flags=re.IGNORECASE)


def _nested_datasource_reference_ids(value: Any):
    if isinstance(value, str):
        for match in _DATASOURCE_REFERENCE_PATTERN.finditer(value):
            yield int(match.group(1))
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and _DATASOURCE_KEY_PATTERN.fullmatch(key.strip()):
                raw_id = str(item).strip() if not isinstance(item, bool) else ""
                if raw_id.isdigit():
                    yield int(raw_id)
            yield from _nested_datasource_reference_ids(key)
            yield from _nested_datasource_reference_ids(item)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _nested_datasource_reference_ids(item)
        return
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        yield from _nested_datasource_reference_ids(model_dump(mode="python"))


def validate_tracking_datasource_references(
        config: TenantTrackingConfigDTO | TenantTrackingConfigEditor,
        datasource_id: int | None,
) -> None:
    """校验数据字典正文不能声明当前工作空间之外的数据源。"""
    referenced_ids = set(_nested_datasource_reference_ids(config))
    if not referenced_ids:
        return
    if datasource_id is None:
        raise ValueError(
            "当前工作空间未绑定数据源，数据字典内容不能声明 datasource_id="
            + ",".join(str(value) for value in sorted(referenced_ids))
            + "。"
        )
    mismatched_ids = referenced_ids - {int(datasource_id)}
    if mismatched_ids:
        raise ValueError(
            "数据字典内容引用的数据源 "
            + ",".join(str(value) for value in sorted(mismatched_ids))
            + f" 与当前数据源 {int(datasource_id)} 不一致。"
        )


def validate_tracking_event_groups(
    event_groups: list[TenantTrackingEventGroupBase],
    event_name_mappings: list[Any],
) -> None:
    """校验事件分组只能引用当前工作空间事件字典中的事件。"""
    known_events = {
        event_name
        for mapping in event_name_mappings or []
        for event_name in _event_names_from_mapping(mapping)
    }
    seen_group_keys: set[str] = set()
    for group in event_groups or []:
        if group.group_key in seen_group_keys:
            raise ValueError(f"事件分组存在重复分组标识 {group.group_key}。")
        seen_group_keys.add(group.group_key)
        seen_events: set[str] = set()
        if not group.event_names:
            raise ValueError(f"事件分组 {group.group_key} 至少需要一个事件。")
        for raw_event_name in group.event_names:
            event_name = _plain_text(raw_event_name)
            if not event_name:
                raise ValueError(f"事件分组 {group.group_key} 包含空事件名。")
            if event_name in seen_events:
                raise ValueError(f"事件分组 {group.group_key} 包含重复事件 {event_name}。")
            seen_events.add(event_name)
            if event_name not in known_events:
                raise ValueError(
                    f"事件分组 {group.group_key} 引用的事件 {event_name} "
                    "不存在于当前事件参数字典。"
                )


def _clean_text(value: str | None, max_len: int | None = None) -> str | None:
    """
    是什么：_clean_text 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理不再需要的数据、缓存或临时内容清理掉。
    """
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    return cleaned[:max_len] if max_len else cleaned


def _tracking_field_json_identity(item: Any) -> tuple[str | None, str | None]:
    source_field = _clean_text(getattr(item, "source_field", None), 255)
    raw_json_path = _clean_text(getattr(item, "json_path", None), 1000)
    if not raw_json_path:
        return source_field, None

    table_name = _clean_text(getattr(item, "table_name", None), 255) or "（空表）"
    field_name = _clean_text(getattr(item, "field_name", None), 255) or "（空字段）"
    json_path = normalize_json_path(raw_json_path)
    if not json_path:
        raise ValueError(f"{table_name}.{field_name} 配置了无效 JSON 路径 {raw_json_path}。")
    if not source_field:
        raise ValueError(f"{table_name}.{field_name} 配置了 JSON 路径但没有来源字段。")

    expected_name = canonical_json_field_name(source_field, json_path)
    if not expected_name or field_name != expected_name:
        raise ValueError(
            f"{table_name}.{field_name} 的生成字段名与来源字段、JSON路径不一致，"
            f"应为 {expected_name or '有效的规范字段名'}。"
        )
    return source_field, json_path


def _plain_text(value: Any) -> str:
    text = str(value or "").strip()
    return text


def _first_plain_text(*values: Any) -> str:
    for value in values:
        text = _plain_text(value)
        if text:
            return text
    return ""


def _normalize_tracking_type(value: Any) -> str:
    return (
        _plain_text(value)
        .lower()
        .removesuffix("类型")
        .replace("_", "")
        .replace("-", "")
        .replace(" ", "")
    )


def _is_tracking_container_type(value: Any) -> bool:
    normalized = _normalize_tracking_type(value)
    return normalized in {
        "对象组",
        "对象",
        "对象数组",
        "数组",
        "json",
        "jsonb",
        "object",
        "objectarray",
        "array",
    }


def _event_names_from_mapping(item: Any) -> list[str]:
    if not isinstance(item, dict):
        text = _plain_text(item)
        return [text] if text else []
    names: list[str] = []
    for key in ("event_name", "eventName", "name", "value"):
        text = _plain_text(item.get(key))
        if text:
            names.append(text)
    events = item.get("events")
    if isinstance(events, list):
        names.extend(_plain_text(value) for value in events if _plain_text(value))
    merged: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name and name not in seen:
            seen.add(name)
            merged.append(name)
    return merged


def _tracking_event_properties(
    mapping: dict[str, Any],
    *,
    event_table: str,
    event_name_field: str,
    event_name: str,
) -> list[TenantTrackingEventCatalogProperty]:
    properties = mapping.get("properties")
    if not isinstance(properties, list):
        return []
    result: list[TenantTrackingEventCatalogProperty] = []
    seen: set[str] = set()
    for item in properties:
        if not isinstance(item, dict):
            continue
        property_name = _first_plain_text(item.get("property_name"), item.get("field_name"), item.get("name"))
        if not property_name or property_name in seen:
            continue
        property_type = _first_plain_text(item.get("property_type"), item.get("semantic_type"), item.get("field_type"), item.get("type"))
        if _is_tracking_container_type(property_type):
            continue
        seen.add(property_name)
        result.append(
            TenantTrackingEventCatalogProperty(
                value=f"tracking-property:{event_table}.{event_name_field}:{event_name}:{property_name}",
                property_name=property_name,
                display_name=_first_plain_text(
                    item.get("property_display_name"),
                    item.get("display_name"),
                    item.get("label"),
                    property_name,
                ),
                property_type=property_type,
                source_field=_plain_text(item.get("source_field")),
                json_path=_plain_text(item.get("json_path")),
                description=_first_plain_text(item.get("description"), item.get("ai_notes")),
                event_name=event_name,
                event_table=event_table,
                event_name_field=event_name_field,
            )
        )
    return result


def build_tracking_event_catalog(config: TenantTrackingConfigDTO) -> TenantTrackingEventCatalogDTO:
    event_table = _plain_text(config.default_event_table)
    event_name_field = _plain_text(config.default_event_name_field)
    if not event_table or not event_name_field:
        return TenantTrackingEventCatalogDTO(
            tenant_id=config.tenant_id,
            datasource_id=config.datasource_id,
            event_table=event_table,
            event_name_field=event_name_field,
            groups=[],
        )
    groups: dict[str, TenantTrackingEventCatalogGroup] = {}
    for mapping in config.event_name_mappings or []:
        if not isinstance(mapping, dict):
            continue
        category = _first_plain_text(mapping.get("event_category"), mapping.get("category"), mapping.get("metric")) or "默认分组"
        group = groups.setdefault(
            category,
            TenantTrackingEventCatalogGroup(label=category, value=category, events=[]),
        )
        for event_name in _event_names_from_mapping(mapping):
            display_name = _first_plain_text(
                mapping.get("event_display_name"),
                mapping.get("display_name"),
                mapping.get("metric"),
                mapping.get("name"),
                event_name,
            )
            if any(item.event_name == event_name for item in group.events):
                continue
            group.events.append(
                TenantTrackingEventCatalogItem(
                    value=f"tracking-event:{event_table}.{event_name_field}:{event_name}",
                    event_name=event_name,
                    display_name=display_name,
                    category=category,
                    description=_first_plain_text(mapping.get("description"), mapping.get("event_description"), mapping.get("ai_notes")),
                    event_table=event_table,
                    event_name_field=event_name_field,
                    properties=_tracking_event_properties(
                        mapping,
                        event_table=event_table,
                        event_name_field=event_name_field,
                        event_name=event_name,
                    ),
                )
            )
    return TenantTrackingEventCatalogDTO(
        tenant_id=int(config.tenant_id),
        datasource_id=config.datasource_id,
        event_table=event_table,
        event_name_field=event_name_field,
        groups=list(groups.values()),
    )


def _json_value(value: Any, default):
    """
    是什么：_json_value 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if value in (None, ""):
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _json_list(value: Any) -> list:
    """
    是什么：_json_list 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    parsed = _json_value(value, [])
    return parsed if isinstance(parsed, list) else []


def _sanitize_event_name_mappings(value: Any) -> list[Any]:
    sanitized: list[Any] = []
    for item in _json_list(value):
        if not isinstance(item, dict):
            sanitized.append(copy.deepcopy(item))
            continue
        cleaned = copy.deepcopy(item)
        cleaned.pop("collect_side", None)
        cleaned.pop("collectSide", None)
        sanitized.append(cleaned)
    return sanitized


def _json_list_or_dict(value: Any):
    """
    是什么：_json_list_or_dict 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    parsed = _json_value(value, None)
    return parsed if isinstance(parsed, (list, dict)) else None


def _json_dict(value: Any) -> dict:
    """
    是什么：把数据库或 DTO 中的 JSON 对象整理成字典，非法内容按空字典处理。
    """
    parsed = _json_value(value, {})
    return parsed if isinstance(parsed, dict) else {}


def _normalized_semantic_type(field_role: str | None, semantic_type: str | None) -> str | None:
    role = (field_role or "").strip().lower()
    if role == "event_name":
        return "text"
    return semantic_type


@dataclass(frozen=True)
class TrackingSchemaValidation:
    warnings: list[str]
    invalid_tables: list[str]
    invalid_fields: list[str]


def project_tracking_config_for_ai_context(
    config: TenantTrackingConfigDTO,
) -> TenantTrackingConfigDTO:
    """Return a copy containing only workspace metadata allowed in AI context."""
    if hasattr(config, "model_copy"):
        projected = config.model_copy(deep=True)
    else:
        projected = copy.deepcopy(config)
    projected.default_event_table = None
    projected.default_subject_field = None
    projected.default_event_name_field = None
    projected.default_event_time_field = None
    projected.event_name_mappings = []
    projected.event_groups = []
    return projected


def datasource_physical_schema(session: Session, datasource_id: int | None) -> dict[str, set[str]]:
    """
    是什么：读取当前数据源缓存 schema，用于判断工作空间数据字典是否仍匹配当前数据源。
    """
    if datasource_id is None:
        return {}
    tables = session.exec(
        select(CoreTable).where(CoreTable.ds_id == int(datasource_id)).order_by(CoreTable.table_name, CoreTable.id)
    ).all()
    table_ids = [int(table.id) for table in tables if table.id is not None]
    fields_by_table: dict[int, set[str]] = {table_id: set() for table_id in table_ids}
    if table_ids:
        fields = session.exec(
            select(CoreField).where(CoreField.table_id.in_(table_ids)).order_by(CoreField.table_id, CoreField.id)
        ).all()
        for field in fields:
            if field.field_name:
                fields_by_table.setdefault(int(field.table_id), set()).add(field.field_name)
    return {
        table.table_name: fields_by_table.get(int(table.id), set())
        for table in tables
        if table.table_name and table.id is not None
    }


def _schema_field_names(physical_schema: dict[str, Any], table_name: str) -> set[str] | None:
    if table_name not in physical_schema:
        return None
    table_info = physical_schema.get(table_name)
    if isinstance(table_info, set):
        return {str(item) for item in table_info if str(item or "").strip()}
    fields = getattr(table_info, "fields", None)
    if fields is None:
        return set()
    return {
        str(getattr(field, "field_name", "")).strip()
        for field in fields
        if str(getattr(field, "field_name", "") or "").strip()
    }


def _field_source_name(field: Any) -> str:
    source = (getattr(field, "source_field", None) or "").strip()
    if source:
        return source
    field_name = (getattr(field, "field_name", None) or "").strip()
    if "." in field_name:
        return field_name.split(".", 1)[0].strip()
    return field_name


def _tracking_field_schema_issue(field: Any, physical_names: set[str] | None) -> str | None:
    table_name = (getattr(field, "table_name", None) or "").strip()
    field_name = (getattr(field, "field_name", None) or "").strip()
    if physical_names is None:
        return f"{table_name}.{field_name} 所属表不在当前数据源 schema 中"
    source_field = _field_source_name(field)
    json_path = (getattr(field, "json_path", None) or "").strip()
    if json_path and not source_field:
        return f"{table_name}.{field_name} 配置了 JSON 路径但没有来源字段"
    if source_field and source_field not in physical_names:
        return f"{table_name}.{field_name} 的来源字段 {source_field} 不在当前数据源 schema 中"
    if not source_field and field_name and field_name not in physical_names:
        return f"{table_name}.{field_name} 不在当前数据源 schema 中"
    return None


def filter_tracking_config_for_physical_schema(
    config: TenantTrackingConfigDTO,
    physical_schema: dict[str, Any],
) -> tuple[TenantTrackingConfigDTO, TrackingSchemaValidation]:
    """
    是什么：把已经漂移到当前数据源 schema 之外的数据字典配置从 AI 消费配置中剔除，并保留明确提示。
    """
    if not physical_schema:
        return config, TrackingSchemaValidation(warnings=[], invalid_tables=[], invalid_fields=[])

    if hasattr(config, "model_copy"):
        filtered = config.model_copy(deep=True)
    else:
        filtered = copy.deepcopy(config)
    warnings: list[str] = []
    invalid_tables: list[str] = []
    invalid_fields: list[str] = []

    table_names = set(physical_schema.keys())
    valid_tables = []
    for table in filtered.tables or []:
        table_name = (getattr(table, "table_name", None) or "").strip()
        if table_name and table_name not in table_names:
            invalid_tables.append(table_name)
            warnings.append(f"表 {table_name} 不在当前数据源 schema 中，已从数据字典上下文中移除。")
            continue
        valid_tables.append(table)
    filtered.tables = valid_tables

    if getattr(filtered, "default_event_table", None) and filtered.default_event_table not in table_names:
        warnings.append(f"默认事件表 {filtered.default_event_table} 不在当前数据源 schema 中，已忽略。")
        filtered.default_event_table = None

    default_table = getattr(filtered, "default_event_table", None)
    default_fields = _schema_field_names(physical_schema, default_table) if default_table else None
    if default_fields is not None:
        default_checks = [
            ("默认主体字段", "default_subject_field"),
            ("默认事件名字段", "default_event_name_field"),
            ("默认事件时间字段", "default_event_time_field"),
        ]
        for label, attr in default_checks:
            value = getattr(filtered, attr, None)
            if value and value not in default_fields:
                warnings.append(f"{label} {default_table}.{value} 不在当前数据源 schema 中，已忽略。")
                setattr(filtered, attr, None)

    valid_fields = []
    for field in filtered.fields or []:
        table_name = (getattr(field, "table_name", None) or "").strip()
        field_name = (getattr(field, "field_name", None) or "").strip()
        issue = _tracking_field_schema_issue(field, _schema_field_names(physical_schema, table_name))
        if issue:
            invalid_fields.append(f"{table_name}.{field_name}")
            warnings.append(f"{issue}，已从数据字典上下文中移除。")
            continue
        valid_fields.append(field)
    filtered.fields = valid_fields

    return filtered, TrackingSchemaValidation(
        warnings=warnings,
        invalid_tables=invalid_tables,
        invalid_fields=invalid_fields,
    )


def compile_tracking_config_expressions(
    config: TenantTrackingConfigDTO,
    datasource_type: str | None,
) -> tuple[TenantTrackingConfigDTO, list[str]]:
    """
    是什么：按当前数据源方言为 JSON 字典字段补运行时 expression，不把结果写回存储。
    """
    if hasattr(config, "model_copy"):
        compiled = config.model_copy(deep=True)
    else:
        compiled = copy.deepcopy(config)
    warnings: list[str] = []
    for field in compiled.fields or []:
        source_field = (getattr(field, "source_field", None) or "").strip()
        json_path = (getattr(field, "json_path", None) or "").strip()
        if not source_field or not json_path:
            continue
        expression = compile_tracking_json_expression(
            getattr(field, "table_name", None) or "",
            source_field,
            json_path,
            _normalized_semantic_type(
                getattr(field, "field_role", None),
                getattr(field, "semantic_type", None),
            ),
            datasource_type,
        )
        if expression:
            field.expression = expression
            continue
        field.expression = None
        warnings.append(
            f"{getattr(field, 'table_name', '')}.{getattr(field, 'field_name', '')} "
            "配置了 JSON 路径，但当前数据源方言无法编译表达式，已从 Agent 上下文中移除 expression。"
        )
    return compiled, warnings


def _row_id(row) -> int | None:
    """
    是什么：_row_id 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    value = getattr(row, "id", None)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _config_dto(row: TenantTrackingConfigModel | None, tenant_id: int, datasource_id: int | None = None) -> TenantTrackingConfigDTO:
    """
    是什么：_config_dto 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if row is None:
        return TenantTrackingConfigDTO(tenant_id=tenant_id, datasource_id=datasource_id)
    return TenantTrackingConfigDTO(
        id=_row_id(row),
        tenant_id=int(row.tenant_id),
        datasource_id=int(row.datasource_id) if row.datasource_id is not None else None,
        enabled=bool(row.enabled),
        default_event_table=row.default_event_table,
        default_subject_field=row.default_subject_field,
        default_event_name_field=row.default_event_name_field,
        default_event_time_field=row.default_event_time_field,
        field_role_mappings=_json_list(row.field_role_mappings),
        event_name_mappings=_sanitize_event_name_mappings(row.event_name_mappings),
        sql_rules=row.sql_rules,
        notes=row.notes,
        create_by=row.create_by,
        update_by=row.update_by,
        create_time=row.create_time,
        update_time=row.update_time,
    )


def _table_dto(row: TenantTrackingTableModel) -> TenantTrackingTableDTO:
    """
    是什么：_table_dto 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return TenantTrackingTableDTO(
        id=_row_id(row),
        tenant_id=int(row.tenant_id),
        datasource_id=int(row.datasource_id) if row.datasource_id is not None else None,
        table_name=row.table_name,
        table_comment=row.table_comment,
        table_role=row.table_role,
        aliases=_json_list(row.aliases),
        ai_notes=row.ai_notes,
        extra_properties=_json_dict(getattr(row, "extra_properties", None)),
        create_by=row.create_by,
        update_by=row.update_by,
        create_time=row.create_time,
        update_time=row.update_time,
    )


def _field_dto(row: TenantTrackingFieldModel) -> TenantTrackingFieldDTO:
    """
    是什么：_field_dto 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return TenantTrackingFieldDTO(
        id=_row_id(row),
        tenant_id=int(row.tenant_id),
        datasource_id=int(row.datasource_id) if row.datasource_id is not None else None,
        table_name=row.table_name,
        field_name=row.field_name,
        field_comment=row.field_comment,
        field_role=row.field_role,
        semantic_type=_normalized_semantic_type(row.field_role, row.semantic_type),
        source_field=row.source_field,
        json_path=row.json_path,
        update_mode=getattr(row, "update_mode", None),
        category=getattr(row, "category", None),
        aliases=_json_list(row.aliases),
        value_mappings=_json_list_or_dict(row.value_mappings),
        expression=row.expression,
        required=bool(row.required),
        example_values=_json_list(row.example_values),
        ai_notes=row.ai_notes,
        extra_properties=_json_dict(getattr(row, "extra_properties", None)),
        create_by=row.create_by,
        update_by=row.update_by,
        create_time=row.create_time,
        update_time=row.update_time,
    )


def _event_group_dto(row: TenantTrackingEventGroupModel) -> TenantTrackingEventGroupDTO:
    """把事件分组数据库记录转换为当前工作空间 DTO。"""
    return TenantTrackingEventGroupDTO(
        id=_row_id(row),
        tenant_id=int(row.tenant_id),
        datasource_id=int(row.datasource_id) if row.datasource_id is not None else None,
        group_key=row.group_key,
        group_name=row.group_name,
        description=row.description,
        event_names=[_plain_text(item) for item in _json_list(row.event_names) if _plain_text(item)],
        sort_order=int(row.sort_order or 0),
        enabled=bool(row.enabled),
        create_by=row.create_by,
        update_by=row.update_by,
        create_time=row.create_time,
        update_time=row.update_time,
    )


def _datasource_filter(model: Any, datasource_id: int | None):
    if datasource_id is None:
        return model.datasource_id.is_(None)
    return model.datasource_id == int(datasource_id)


def _tracking_scope_statements(
    tenant_id: int,
    datasource_id: int | None,
    *,
    for_update: bool = False,
):
    config_statement = select(TenantTrackingConfigModel).where(
        TenantTrackingConfigModel.tenant_id == int(tenant_id),
        _datasource_filter(TenantTrackingConfigModel, datasource_id),
    )
    event_group_statement = (
        select(TenantTrackingEventGroupModel)
        .where(
            TenantTrackingEventGroupModel.tenant_id == int(tenant_id),
            _datasource_filter(TenantTrackingEventGroupModel, datasource_id),
        )
        .order_by(TenantTrackingEventGroupModel.sort_order, TenantTrackingEventGroupModel.group_key)
    )
    if for_update:
        config_statement = config_statement.with_for_update()
        event_group_statement = event_group_statement.with_for_update()
    return config_statement, event_group_statement


def get_tracking_config(
    session: Session,
    tenant_id: int,
    datasource_id: int | None = None,
) -> TenantTrackingConfigDTO:
    """
    是什么：get_tracking_config 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    statement = (
        select(TenantTrackingConfigModel)
        .where(
            TenantTrackingConfigModel.tenant_id == int(tenant_id),
            _datasource_filter(TenantTrackingConfigModel, datasource_id),
        )
        .order_by(TenantTrackingConfigModel.id)
    )
    config = session.exec(statement).first()
    tables = session.exec(
        select(TenantTrackingTableModel)
        .where(
            TenantTrackingTableModel.tenant_id == int(tenant_id),
            _datasource_filter(TenantTrackingTableModel, datasource_id),
        )
        .order_by(TenantTrackingTableModel.table_name, TenantTrackingTableModel.id)
    ).all()
    fields = session.exec(
        select(TenantTrackingFieldModel)
        .where(
            TenantTrackingFieldModel.tenant_id == int(tenant_id),
            _datasource_filter(TenantTrackingFieldModel, datasource_id),
        )
        .order_by(
            TenantTrackingFieldModel.table_name,
            TenantTrackingFieldModel.field_name,
            TenantTrackingFieldModel.id,
        )
    ).all()
    event_groups = session.exec(
        select(TenantTrackingEventGroupModel)
        .where(
            TenantTrackingEventGroupModel.tenant_id == int(tenant_id),
            _datasource_filter(TenantTrackingEventGroupModel, datasource_id),
        )
        .order_by(
            TenantTrackingEventGroupModel.sort_order,
            TenantTrackingEventGroupModel.group_key,
            TenantTrackingEventGroupModel.id,
        )
    ).all()
    dto = _config_dto(config, int(tenant_id), datasource_id)
    dto.tables = [_table_dto(row) for row in tables]
    dto.fields = [_field_dto(row) for row in fields]
    dto.event_groups = [_event_group_dto(row) for row in event_groups]
    validate_tracking_datasource_references(
        dto,
        datasource_id if datasource_id is not None else dto.datasource_id,
    )
    return dto


def save_tracking_config(
    session: Session,
    tenant_id: int,
    editor: TenantTrackingConfigEditor,
    *,
    datasource_id: int | None = None,
    current_user_id: int | None = None,
) -> TenantTrackingConfigDTO:
    """
    是什么：save_tracking_config 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存系统管理需要的东西，让后续流程能继续往下走。
    """
    validate_tracking_datasource_references(editor, datasource_id)
    requested_event_groups = list(editor.event_groups or [])
    if requested_event_groups and datasource_id is None:
        raise ValueError("事件分组必须在工作空间已绑定数据源后保存。")

    fields_to_save = list(editor.fields or [])
    field_json_identities = [
        _tracking_field_json_identity(item)
        for item in fields_to_save
    ]

    now = get_timestamp()
    config_statement, event_group_statement = _tracking_scope_statements(
        tenant_id,
        datasource_id,
        for_update=True,
    )
    config = session.exec(config_statement).first()
    existing_event_group_rows = session.exec(event_group_statement).all()
    groups_to_validate = requested_event_groups or [
        TenantTrackingEventGroupBase(
            group_key=row.group_key,
            group_name=row.group_name,
            description=row.description,
            event_names=_json_list(row.event_names),
            sort_order=int(row.sort_order or 0),
            enabled=bool(row.enabled),
        )
        for row in existing_event_group_rows
    ]
    validate_tracking_event_groups(groups_to_validate, list(editor.event_name_mappings or []))

    if config is None:
        config = TenantTrackingConfigModel(
            id=snowflake.generate_id(),
            tenant_id=int(tenant_id),
            datasource_id=int(datasource_id) if datasource_id is not None else None,
            create_by=current_user_id,
            create_time=now,
        )

    config.datasource_id = int(datasource_id) if datasource_id is not None else None
    config.enabled = bool(editor.enabled)
    config.default_event_table = _clean_text(editor.default_event_table, 255)
    config.default_subject_field = _clean_text(editor.default_subject_field, 255)
    config.default_event_name_field = _clean_text(editor.default_event_name_field, 255)
    config.default_event_time_field = _clean_text(editor.default_event_time_field, 255)
    config.field_role_mappings = _json_list(editor.field_role_mappings)
    config.event_name_mappings = _sanitize_event_name_mappings(editor.event_name_mappings)
    config.sql_rules = _clean_text(editor.sql_rules)
    config.notes = _clean_text(editor.notes)
    config.update_by = current_user_id
    config.update_time = now
    session.add(config)

    session.exec(
        delete(TenantTrackingTableModel).where(
            TenantTrackingTableModel.tenant_id == int(tenant_id),
            _datasource_filter(TenantTrackingTableModel, datasource_id),
        )
    )
    for item in editor.tables or []:
        table_name = _clean_text(item.table_name, 255)
        if not table_name:
            continue
        session.add(
            TenantTrackingTableModel(
                id=snowflake.generate_id(),
                tenant_id=int(tenant_id),
                datasource_id=int(datasource_id) if datasource_id is not None else None,
                table_name=table_name,
                table_comment=_clean_text(item.table_comment),
                table_role=_clean_text(item.table_role, 64),
                aliases=_json_list(item.aliases),
                ai_notes=_clean_text(item.ai_notes),
                extra_properties=_json_dict(getattr(item, "extra_properties", None)),
                create_by=current_user_id,
                update_by=current_user_id,
                create_time=now,
                update_time=now,
            )
        )

    session.exec(
        delete(TenantTrackingFieldModel).where(
            TenantTrackingFieldModel.tenant_id == int(tenant_id),
            _datasource_filter(TenantTrackingFieldModel, datasource_id),
        )
    )
    for item, (source_field, json_path) in zip(
        fields_to_save,
        field_json_identities,
        strict=True,
    ):
        table_name = _clean_text(item.table_name, 255)
        field_name = _clean_text(item.field_name, 255)
        if not table_name or not field_name:
            continue
        session.add(
            TenantTrackingFieldModel(
                id=snowflake.generate_id(),
                tenant_id=int(tenant_id),
                datasource_id=int(datasource_id) if datasource_id is not None else None,
                table_name=table_name,
                field_name=field_name,
                field_comment=_clean_text(item.field_comment),
                field_role=_clean_text(item.field_role, 64),
                semantic_type=_normalized_semantic_type(
                    _clean_text(item.field_role, 64),
                    _clean_text(item.semantic_type, 64),
                ),
                source_field=source_field,
                json_path=json_path,
                update_mode=_clean_text(getattr(item, "update_mode", None), 64),
                category=_clean_text(getattr(item, "category", None), 255),
                aliases=_json_list(item.aliases),
                value_mappings=_json_list_or_dict(item.value_mappings),
                expression=_clean_text(item.expression),
                required=bool(item.required),
                example_values=_json_list(item.example_values),
                ai_notes=_clean_text(item.ai_notes),
                extra_properties=_json_dict(getattr(item, "extra_properties", None)),
                create_by=current_user_id,
                update_by=current_user_id,
                create_time=now,
                update_time=now,
            )
        )

    if requested_event_groups:
        session.exec(
            delete(TenantTrackingEventGroupModel).where(
                TenantTrackingEventGroupModel.tenant_id == int(tenant_id),
                _datasource_filter(TenantTrackingEventGroupModel, datasource_id),
            )
        )
        for item in requested_event_groups:
            session.add(
                TenantTrackingEventGroupModel(
                    id=snowflake.generate_id(),
                    tenant_id=int(tenant_id),
                    datasource_id=int(datasource_id) if datasource_id is not None else None,
                    group_key=_plain_text(item.group_key),
                    group_name=_plain_text(item.group_name),
                    description=_clean_text(item.description),
                    event_names=[_plain_text(name) for name in item.event_names],
                    sort_order=int(item.sort_order or 0),
                    enabled=bool(item.enabled),
                    create_by=current_user_id,
                    update_by=current_user_id,
                    create_time=now,
                    update_time=now,
                )
            )

    bump_semantic_scope_epoch(
        session,
        scope_type=SemanticScopeType.TRACKING,
        tenant_id=int(tenant_id),
        datasource_id=int(datasource_id) if datasource_id is not None else None,
    )
    session.commit()
    return get_tracking_config(session, int(tenant_id), datasource_id)


def _format_json_for_prompt(value: Any) -> str:
    """
    是什么：_format_json_for_prompt 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if value in (None, [], {}):
        return ""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _tracking_field_match_texts(field: TenantTrackingFieldDTO) -> list[str]:
    texts: list[str] = []
    for value in (
        field.field_name,
        field.field_comment,
        field.field_role,
        field.semantic_type,
        field.source_field,
        field.json_path,
        field.ai_notes,
    ):
        if isinstance(value, str) and value.strip():
            texts.append(value.strip())
    for value in (field.aliases, field.value_mappings, field.example_values):
        if value not in (None, [], {}):
            texts.append(_format_json_for_prompt(value))
    return texts


def _tracking_field_matches_question(field: TenantTrackingFieldDTO, question: str) -> bool:
    normalized_question = question.casefold().strip()
    if not normalized_question:
        return False
    for text in _tracking_field_match_texts(field):
        normalized_text = text.casefold().strip()
        if len(normalized_text) >= 2 and normalized_text in normalized_question:
            return True
    return False


def _tracking_field_matches_data_skill(field: TenantTrackingFieldDTO, data_skill_text: str) -> bool:
    normalized_skill = data_skill_text.casefold().strip()
    if not normalized_skill:
        return False
    candidates = [field.field_name]
    if field.source_field and field.json_path:
        candidates.append(f"{field.source_field}.{field.json_path.removeprefix('$.')}")
    for candidate in candidates:
        normalized_candidate = str(candidate or "").casefold().strip()
        if len(normalized_candidate) >= 2 and normalized_candidate in normalized_skill:
            return True
    return False


def _tracking_field_is_default(field: TenantTrackingFieldDTO, config: TenantTrackingConfigDTO) -> bool:
    default_table = config.default_event_table
    default_fields = {
        config.default_subject_field,
        config.default_event_name_field,
        config.default_event_time_field,
    }
    if default_table and field.table_name == default_table and field.field_name in default_fields:
        return True
    return field.field_role in {"subject_id", "event_name", "event_time", "partition_date", "snapshot_date"}


def _tracking_field_context_line(field: TenantTrackingFieldDTO, datasource_type: str | None) -> str:
    parts = [f"- `{field.table_name}.{field.field_name}`"]
    if field.field_role:
        parts.append(f"role={field.field_role}")
    semantic_type = _normalized_semantic_type(field.field_role, field.semantic_type)
    if semantic_type:
        parts.append(f"type={semantic_type}")
    if field.source_field:
        parts.append(f"source={field.source_field}")
    if field.json_path:
        parts.append(f"json_path={field.json_path}")
    if field.required:
        parts.append("required=true")
    if field.field_comment:
        parts.append(f"comment={field.field_comment}")
    aliases = _format_json_for_prompt(field.aliases)
    if aliases:
        parts.append(f"aliases={aliases}")
    mappings = _format_json_for_prompt(field.value_mappings)
    if mappings:
        parts.append(f"value_mappings={mappings}")
    examples = _format_json_for_prompt(field.example_values)
    if examples:
        parts.append(f"examples={examples}")
    expression = field.expression
    if field.source_field and field.json_path and not datasource_type:
        expression = None
    if expression:
        parts.append(f"expression={expression}")
    if field.ai_notes:
        parts.append(f"notes={field.ai_notes}")
    return "; ".join(parts)


def _lightweight_tracking_field(field: TenantTrackingFieldDTO) -> TenantTrackingFieldDTO:
    projected = copy.deepcopy(field)
    projected.field_comment = None
    projected.aliases = []
    projected.value_mappings = []
    projected.expression = None
    projected.example_values = []
    projected.ai_notes = None
    return projected


def _project_tracking_fields(
    config: TenantTrackingConfigDTO,
    question: str | None,
    *,
    datasource_type: str | None,
    data_skill_text: str | None = None,
    budget: int = TRACKING_FIELD_PROMPT_BUDGET,
) -> list[TenantTrackingFieldDTO]:
    fields = config.fields or []
    if not question or not question.strip():
        return copy.deepcopy(fields)

    ranked: list[tuple[int, int, TenantTrackingFieldDTO]] = []
    for index, field in enumerate(fields):
        is_default = _tracking_field_is_default(field, config)
        is_question_match = _tracking_field_matches_question(field, question)
        is_data_skill_match = _tracking_field_matches_data_skill(field, data_skill_text or "")
        priority = 3 if is_default else 2 if is_question_match else 1 if is_data_skill_match else 0
        if priority:
            ranked.append((priority, index, field))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected: list[TenantTrackingFieldDTO] = []
    used_chars = 0

    def add(field: TenantTrackingFieldDTO) -> bool:
        nonlocal used_chars
        line = _tracking_field_context_line(field, datasource_type)
        separator_chars = 1 if selected else 0
        if used_chars + separator_chars + len(line) > budget:
            return False
        selected.append(field)
        used_chars += separator_chars + len(line)
        return True

    for _priority, _index, field in ranked:
        if not add(copy.deepcopy(field)):
            add(_lightweight_tracking_field(field))
    return selected


def build_tracking_prompt_context(
    config: TenantTrackingConfigDTO,
    validation_warnings: list[str] | None = None,
    *,
    datasource_type: str | None = None,
    question: str | None = None,
    data_skill_text: str | None = None,
) -> tuple[str, list[str]]:
    """
    为 AI 构建工作空间级表、字段和 SQL 规则上下文。

    事件字典由管理与目录接口维护，不再作为 AI Prompt 的语义来源。
    """
    config = project_tracking_config_for_ai_context(config)
    if datasource_type:
        config, compile_warnings = compile_tracking_config_expressions(config, datasource_type)
        validation_warnings = list(validation_warnings or []) + compile_warnings

    if not config.enabled:
        return "", []

    lines: list[str] = [
        "<Workspace-Tracking-Rules>",
        "以下是当前工作空间维护的表、字段和 SQL 规则。它只约束当前工作空间；生成 SQL 时必须结合当前数据库 Schema 使用。",
        "如果这里配置的表或字段没有出现在当前 Schema 中，不得编造字段，应说明缺少可用字段或请求补充配置。",
    ]
    summary_parts = []
    if validation_warnings:
        lines.append("\n## 当前数据源 schema 校验提示")
        for warning in validation_warnings[:20]:
            lines.append(f"- {warning}")
            summary_parts.append(f"schema校验: {warning}")
    if config.field_role_mappings:
        value = _format_json_for_prompt(config.field_role_mappings)
        lines.append("\n## 字段角色映射")
        lines.append(value)
        summary_parts.append(f"字段角色映射: {value}")
    if config.sql_rules:
        lines.append("\n## SQL 约束")
        lines.append(config.sql_rules)
        summary_parts.append(f"SQL 约束: {config.sql_rules}")
    if config.notes:
        lines.append("\n## 工作空间说明")
        lines.append(config.notes)
        summary_parts.append(f"说明: {config.notes}")

    if config.tables:
        lines.append("\n## 表注释")
        for item in config.tables:
            parts = [f"- `{item.table_name}`"]
            if item.table_role:
                parts.append(f"role={item.table_role}")
            if item.table_comment:
                parts.append(f"comment={item.table_comment}")
            aliases = _format_json_for_prompt(item.aliases)
            if aliases:
                parts.append(f"aliases={aliases}")
            if item.ai_notes:
                parts.append(f"notes={item.ai_notes}")
            line = "; ".join(parts)
            lines.append(line)
            summary_parts.append(line)

    projected_fields = _project_tracking_fields(
        config,
        question,
        datasource_type=datasource_type,
        data_skill_text=data_skill_text,
    )
    if projected_fields:
        lines.append("\n## 字段注释与角色")
        for item in projected_fields:
            line = _tracking_field_context_line(item, datasource_type)
            lines.append(line)
            summary_parts.append(line)

    if len(lines) <= 3:
        return "", []
    lines.append("</Workspace-Tracking-Rules>\n")
    return "\n".join(lines), summary_parts


def find_tracking_prompt_context(
    session: Session,
    tenant_id: int | None,
    datasource_id: int | None = None,
    *,
    datasource_type: str | None = None,
    question: str | None = None,
    data_skill_text: str | None = None,
) -> tuple[str, list[str]]:
    """
    是什么：find_tracking_prompt_context 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    if tenant_id is None:
        return "", []
    config = project_tracking_config_for_ai_context(
        get_tracking_config(session, int(tenant_id), datasource_id)
    )
    validation_warnings: list[str] = []
    if datasource_id is not None:
        physical_schema = datasource_physical_schema(session, int(datasource_id))
        config, validation = filter_tracking_config_for_physical_schema(config, physical_schema)
        validation_warnings = validation.warnings
    return build_tracking_prompt_context(
        config,
        validation_warnings,
        datasource_type=datasource_type,
        question=question,
        data_skill_text=data_skill_text,
    )
