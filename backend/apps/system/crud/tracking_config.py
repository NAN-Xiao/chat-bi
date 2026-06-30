"""
脚本说明：这个脚本封装系统管理的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
import json
from typing import Any

from sqlalchemy import delete
from sqlmodel import Session, select

from apps.system.models.tenant import (
    TenantTrackingConfigModel,
    TenantTrackingFieldModel,
    TenantTrackingTableModel,
)
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


def _config_dto(row: TenantTrackingConfigModel | None, tenant_id: int) -> TenantTrackingConfigDTO:
    """
    是什么：_config_dto 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if row is None:
        return TenantTrackingConfigDTO(tenant_id=tenant_id)
    return TenantTrackingConfigDTO(
        id=_row_id(row),
        tenant_id=int(row.tenant_id),
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
        table_name=row.table_name,
        field_name=row.field_name,
        field_comment=row.field_comment,
        field_role=row.field_role,
        semantic_type=row.semantic_type,
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


def get_tracking_config(session: Session, tenant_id: int) -> TenantTrackingConfigDTO:
    """
    是什么：get_tracking_config 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    config = session.exec(
        select(TenantTrackingConfigModel).where(TenantTrackingConfigModel.tenant_id == int(tenant_id))
    ).first()
    tables = session.exec(
        select(TenantTrackingTableModel)
        .where(TenantTrackingTableModel.tenant_id == int(tenant_id))
        .order_by(TenantTrackingTableModel.table_name, TenantTrackingTableModel.id)
    ).all()
    fields = session.exec(
        select(TenantTrackingFieldModel)
        .where(TenantTrackingFieldModel.tenant_id == int(tenant_id))
        .order_by(
            TenantTrackingFieldModel.table_name,
            TenantTrackingFieldModel.field_name,
            TenantTrackingFieldModel.id,
        )
    ).all()
    dto = _config_dto(config, int(tenant_id))
    dto.tables = [_table_dto(row) for row in tables]
    dto.fields = [_field_dto(row) for row in fields]
    return dto


def save_tracking_config(
    session: Session,
    tenant_id: int,
    editor: TenantTrackingConfigEditor,
    *,
    current_user_id: int | None = None,
) -> TenantTrackingConfigDTO:
    """
    是什么：save_tracking_config 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存系统管理需要的东西，让后续流程能继续往下走。
    """
    now = get_timestamp()
    config = session.exec(
        select(TenantTrackingConfigModel).where(TenantTrackingConfigModel.tenant_id == int(tenant_id))
    ).first()
    if config is None:
        config = TenantTrackingConfigModel(
            id=snowflake.generate_id(),
            tenant_id=int(tenant_id),
            create_by=current_user_id,
            create_time=now,
        )

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
        delete(TenantTrackingTableModel).where(TenantTrackingTableModel.tenant_id == int(tenant_id))
    )
    for item in editor.tables or []:
        table_name = _clean_text(item.table_name, 255)
        if not table_name:
            continue
        session.add(
            TenantTrackingTableModel(
                id=snowflake.generate_id(),
                tenant_id=int(tenant_id),
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
        delete(TenantTrackingFieldModel).where(TenantTrackingFieldModel.tenant_id == int(tenant_id))
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
                table_name=table_name,
                field_name=field_name,
                field_comment=_clean_text(item.field_comment),
                field_role=_clean_text(item.field_role, 64),
                semantic_type=_clean_text(item.semantic_type, 64),
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
    return get_tracking_config(session, int(tenant_id))


def _format_json_for_prompt(value: Any) -> str:
    """
    是什么：_format_json_for_prompt 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if value in (None, [], {}):
        return ""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def build_tracking_prompt_context(config: TenantTrackingConfigDTO) -> tuple[str, list[str]]:
    """
    是什么：build_tracking_prompt_context 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存系统管理需要的东西，让后续流程能继续往下走。
    """
    if not config.enabled:
        return "", []

    lines: list[str] = [
        "<Workspace-Tracking-Rules>",
        "以下是当前工作空间维护的打点/事件字段规范。它只约束当前工作空间；生成 SQL 时必须结合当前数据库 Schema 使用。",
        "如果这里配置的表或字段没有出现在当前 Schema 中，不得编造字段，应说明缺少可用字段或请求补充配置。",
    ]
    summary_parts = []
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
            if item.semantic_type:
                parts.append(f"type={item.semantic_type}")
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
            if item.expression:
                parts.append(f"expression={item.expression}")
            if item.ai_notes:
                parts.append(f"notes={item.ai_notes}")
            line = "; ".join(parts)
            lines.append(line)
            summary_parts.append(line)

    if len(lines) <= 3:
        return "", []
    lines.append("</Workspace-Tracking-Rules>\n")
    return "\n".join(lines), summary_parts


def find_tracking_prompt_context(session: Session, tenant_id: int | None) -> tuple[str, list[str]]:
    """
    是什么：find_tracking_prompt_context 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    if tenant_id is None:
        return "", []
    config = get_tracking_config(session, int(tenant_id))
    return build_tracking_prompt_context(config)
