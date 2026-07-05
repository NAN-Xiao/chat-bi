"""
脚本说明：这个脚本封装系统管理的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
import json
import copy
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete
from sqlalchemy import or_
from sqlmodel import Session, select

from apps.datasource.models.datasource import CoreField, CoreTable
from apps.system.models.tenant import (
    TenantTrackingConfigModel,
    TenantTrackingFieldModel,
    TenantTrackingTableModel,
)
from apps.system.crud.tracking_expression import compile_tracking_json_expression
from apps.system.schemas.tenant_schema import (
    TenantTrackingConfigDTO,
    TenantTrackingConfigEditor,
    TenantTrackingFieldDTO,
    TenantTrackingTableDTO,
)
from common.utils.snowflake import snowflake
from common.utils.time import get_timestamp


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


def _json_list_or_dict(value: Any):
    """
    是什么：_json_list_or_dict 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    parsed = _json_value(value, None)
    return parsed if isinstance(parsed, (list, dict)) else None


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
        event_name_mappings=_json_list(row.event_name_mappings),
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
        aliases=_json_list(row.aliases),
        value_mappings=_json_list_or_dict(row.value_mappings),
        expression=row.expression,
        required=bool(row.required),
        example_values=_json_list(row.example_values),
        ai_notes=row.ai_notes,
        create_by=row.create_by,
        update_by=row.update_by,
        create_time=row.create_time,
        update_time=row.update_time,
    )


def _datasource_filter(model: Any, datasource_id: int | None):
    if datasource_id is None:
        return model.datasource_id.is_(None)
    return model.datasource_id == int(datasource_id)


def _datasource_read_filter(model: Any, datasource_id: int | None, include_legacy: bool):
    if datasource_id is None:
        return model.datasource_id.is_(None)
    if include_legacy:
        return or_(model.datasource_id == int(datasource_id), model.datasource_id.is_(None))
    return model.datasource_id == int(datasource_id)


def get_tracking_config(
    session: Session,
    tenant_id: int,
    datasource_id: int | None = None,
    *,
    include_legacy: bool = True,
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
            _datasource_read_filter(TenantTrackingConfigModel, datasource_id, include_legacy),
        )
        .order_by(TenantTrackingConfigModel.datasource_id.is_(None), TenantTrackingConfigModel.id)
    )
    config = session.exec(statement).first()
    read_legacy = (
        include_legacy
        and datasource_id is not None
        and (config is None or getattr(config, "datasource_id", None) is None)
    )
    tables = session.exec(
        select(TenantTrackingTableModel)
        .where(
            TenantTrackingTableModel.tenant_id == int(tenant_id),
            _datasource_read_filter(TenantTrackingTableModel, datasource_id, read_legacy),
        )
        .order_by(TenantTrackingTableModel.table_name, TenantTrackingTableModel.id)
    ).all()
    fields = session.exec(
        select(TenantTrackingFieldModel)
        .where(
            TenantTrackingFieldModel.tenant_id == int(tenant_id),
            _datasource_read_filter(TenantTrackingFieldModel, datasource_id, read_legacy),
        )
        .order_by(
            TenantTrackingFieldModel.table_name,
            TenantTrackingFieldModel.field_name,
            TenantTrackingFieldModel.id,
        )
    ).all()
    dto = _config_dto(config, int(tenant_id), datasource_id)
    dto.tables = [_table_dto(row) for row in tables]
    dto.fields = [_field_dto(row) for row in fields]
    if dto.datasource_id is None and datasource_id is not None and (config is None or include_legacy):
        dto.datasource_id = int(datasource_id)
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
    now = get_timestamp()
    config = session.exec(
        select(TenantTrackingConfigModel).where(
            TenantTrackingConfigModel.tenant_id == int(tenant_id),
            _datasource_filter(TenantTrackingConfigModel, datasource_id),
        )
    ).first()
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
    config.event_name_mappings = _json_list(editor.event_name_mappings)
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
    for item in editor.fields or []:
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
                source_field=_clean_text(item.source_field, 255),
                json_path=_clean_text(item.json_path, 1000),
                aliases=_json_list(item.aliases),
                value_mappings=_json_list_or_dict(item.value_mappings),
                expression=_clean_text(item.expression),
                required=bool(item.required),
                example_values=_json_list(item.example_values),
                ai_notes=_clean_text(item.ai_notes),
                create_by=current_user_id,
                update_by=current_user_id,
                create_time=now,
                update_time=now,
            )
        )

    session.commit()
    return get_tracking_config(session, int(tenant_id), datasource_id, include_legacy=False)


def _format_json_for_prompt(value: Any) -> str:
    """
    是什么：_format_json_for_prompt 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if value in (None, [], {}):
        return ""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def build_tracking_prompt_context(
    config: TenantTrackingConfigDTO,
    validation_warnings: list[str] | None = None,
    *,
    datasource_type: str | None = None,
) -> tuple[str, list[str]]:
    """
    是什么：build_tracking_prompt_context 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存系统管理需要的东西，让后续流程能继续往下走。
    """
    if datasource_type:
        config, compile_warnings = compile_tracking_config_expressions(config, datasource_type)
        validation_warnings = list(validation_warnings or []) + compile_warnings

    if not config.enabled:
        return "", []

    lines: list[str] = [
        "<Workspace-Tracking-Rules>",
        "以下是当前工作空间维护的打点/事件字段规范。它只约束当前工作空间；生成 SQL 时必须结合当前数据库 Schema 使用。",
        "如果这里配置的表或字段没有出现在当前 Schema 中，不得编造字段，应说明缺少可用字段或请求补充配置。",
    ]
    summary_parts = []
    if validation_warnings:
        lines.append("\n## 当前数据源 schema 校验提示")
        for warning in validation_warnings[:20]:
            lines.append(f"- {warning}")
            summary_parts.append(f"schema校验: {warning}")
    defaults = [
        ("默认事件表", config.default_event_table),
        ("默认主体字段", config.default_subject_field),
        ("默认事件名字段", config.default_event_name_field),
        ("默认事件时间字段", config.default_event_time_field),
    ]
    default_lines = [f"- {label}: `{value}`" for label, value in defaults if value]
    if default_lines:
        lines.append("\n## 默认字段")
        lines.extend(default_lines)
        summary_parts.extend(default_lines)
    if config.field_role_mappings:
        value = _format_json_for_prompt(config.field_role_mappings)
        lines.append("\n## 字段角色映射")
        lines.append(value)
        summary_parts.append(f"字段角色映射: {value}")
    if config.event_name_mappings:
        value = _format_json_for_prompt(config.event_name_mappings)
        lines.append("\n## 事件名映射")
        lines.append(value)
        summary_parts.append(f"事件名映射: {value}")
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

    if config.fields:
        lines.append("\n## 字段注释与角色")
        for item in config.fields:
            parts = [f"- `{item.table_name}.{item.field_name}`"]
            if item.field_role:
                parts.append(f"role={item.field_role}")
            semantic_type = _normalized_semantic_type(item.field_role, item.semantic_type)
            if semantic_type:
                parts.append(f"type={semantic_type}")
            if item.source_field:
                parts.append(f"source={item.source_field}")
            if item.json_path:
                parts.append(f"json_path={item.json_path}")
            if item.required:
                parts.append("required=true")
            if item.field_comment:
                parts.append(f"comment={item.field_comment}")
            aliases = _format_json_for_prompt(item.aliases)
            if aliases:
                parts.append(f"aliases={aliases}")
            mappings = _format_json_for_prompt(item.value_mappings)
            if mappings:
                parts.append(f"value_mappings={mappings}")
            examples = _format_json_for_prompt(item.example_values)
            if examples:
                parts.append(f"examples={examples}")
            expression = item.expression
            if item.source_field and item.json_path and not datasource_type:
                expression = None
            if expression:
                parts.append(f"expression={expression}")
            if item.ai_notes:
                parts.append(f"notes={item.ai_notes}")
            line = "; ".join(parts)
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
    include_legacy: bool = False,
    datasource_type: str | None = None,
) -> tuple[str, list[str]]:
    """
    是什么：find_tracking_prompt_context 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    if tenant_id is None:
        return "", []
    config = get_tracking_config(session, int(tenant_id), datasource_id, include_legacy=include_legacy)
    validation_warnings: list[str] = []
    if datasource_id is not None:
        physical_schema = datasource_physical_schema(session, int(datasource_id))
        config, validation = filter_tracking_config_for_physical_schema(config, physical_schema)
        validation_warnings = validation.warnings
    return build_tracking_prompt_context(config, validation_warnings, datasource_type=datasource_type)
