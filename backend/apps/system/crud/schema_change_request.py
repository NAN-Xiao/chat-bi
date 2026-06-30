import json
import re
from typing import Any

from sqlmodel import Session, select

from apps.system.models.tenant import TenantSchemaChangeRequestModel
from common.utils.snowflake import snowflake
from common.utils.time import get_timestamp


SCHEMA_CHANGE_TYPE_CREATE_TABLE = "create_table"
SCHEMA_CHANGE_TYPE_ALTER_TABLE = "alter_table"
SCHEMA_CHANGE_TYPES = {
    SCHEMA_CHANGE_TYPE_CREATE_TABLE,
    SCHEMA_CHANGE_TYPE_ALTER_TABLE,
}
SCHEMA_CHANGE_STATUS_PENDING = "pending"
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def clean_optional_text(value: str | None, max_len: int | None = None) -> str | None:
    """
    是什么：clean_optional_text 是 backend/apps/system/crud/schema_change_request.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：删除或清理系统管理相关数据、缓存或临时状态。
    """
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    return cleaned[:max_len] if max_len else cleaned


def validate_identifier(value: str | None, label: str) -> str:
    """
    是什么：validate_identifier 是 backend/apps/system/crud/schema_change_request.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    cleaned = (value or "").strip()
    if not IDENTIFIER_RE.fullmatch(cleaned):
        raise ValueError(f"{label} must start with a letter or underscore and contain only letters, numbers, and underscores")
    return cleaned


def normalize_change_type(value: str | None) -> str:
    """
    是什么：normalize_change_type 是 backend/apps/system/crud/schema_change_request.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：解析、转换或格式化系统管理相关数据，生成后续流程可使用的结构。
    """
    normalized = (value or "").strip().lower()
    if normalized not in SCHEMA_CHANGE_TYPES:
        raise ValueError("Schema change type is invalid")
    return normalized


def normalize_field_payload(fields: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """
    是什么：normalize_field_payload 是 backend/apps/system/crud/schema_change_request.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：解析、转换或格式化系统管理相关数据，生成后续流程可使用的结构。
    """
    normalized_fields: list[dict[str, Any]] = []
    for index, field in enumerate(fields or []):
        field_name = validate_identifier(field.get("field_name"), f"Field #{index + 1} name")
        field_type = clean_optional_text(field.get("field_type"), 128)
        if not field_type:
            raise ValueError(f"Field {field_name} type is required")
        normalized_fields.append(
            {
                "field_name": field_name,
                "field_type": field_type,
                "field_comment": clean_optional_text(field.get("field_comment")),
                "required": bool(field.get("required", False)),
            }
        )
    if not normalized_fields:
        raise ValueError("At least one field is required")
    names = [field["field_name"] for field in normalized_fields]
    if len(names) != len(set(names)):
        raise ValueError("Field names must be unique")
    return normalized_fields


def create_schema_change_request(
        session: Session,
        *,
        tenant_id: int,
        datasource_id: int | None,
        requested_by_user_id: int,
        change_type: str,
        table_name: str,
        table_comment: str | None = None,
        fields: list[dict[str, Any]] | None = None,
        request_comment: str | None = None,
        source_table_name: str | None = None,
) -> TenantSchemaChangeRequestModel:
    """
    是什么：create_schema_change_request 是 backend/apps/system/crud/schema_change_request.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：创建、初始化或组装系统管理相关对象和数据，并返回或写入对应状态。
    """
    normalized_type = normalize_change_type(change_type)
    normalized_table_name = validate_identifier(table_name, "Table name")
    payload = {
        "table_name": normalized_table_name,
        "table_comment": clean_optional_text(table_comment),
        "fields": normalize_field_payload(fields),
    }
    if source_table_name:
        payload["source_table_name"] = validate_identifier(source_table_name, "Source table name")

    now = get_timestamp()
    row = TenantSchemaChangeRequestModel(
        id=snowflake.generate_id(),
        tenant_id=int(tenant_id),
        datasource_id=int(datasource_id) if datasource_id is not None else None,
        change_type=normalized_type,
        status=SCHEMA_CHANGE_STATUS_PENDING,
        table_name=normalized_table_name,
        payload=json.dumps(payload, ensure_ascii=False),
        requested_by_user_id=int(requested_by_user_id),
        request_comment=clean_optional_text(request_comment),
        create_time=now,
        update_time=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_schema_change_requests(
        session: Session,
        *,
        tenant_id: int,
        datasource_id: int | None = None,
        limit: int = 20,
) -> list[TenantSchemaChangeRequestModel]:
    """
    是什么：list_schema_change_requests 是 backend/apps/system/crud/schema_change_request.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询系统管理相关数据，整理后返回给调用方。
    """
    statement = (
        select(TenantSchemaChangeRequestModel)
        .where(TenantSchemaChangeRequestModel.tenant_id == int(tenant_id))
        .order_by(TenantSchemaChangeRequestModel.create_time.desc())
        .limit(max(1, min(int(limit or 20), 100)))
    )
    if datasource_id is not None:
        statement = statement.where(TenantSchemaChangeRequestModel.datasource_id == int(datasource_id))
    return list(session.exec(statement).all())


def parse_schema_change_payload(row: TenantSchemaChangeRequestModel) -> dict[str, Any]:
    """
    是什么：parse_schema_change_payload 是 backend/apps/system/crud/schema_change_request.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：解析、转换或格式化系统管理相关数据，生成后续流程可使用的结构。
    """
    try:
        parsed = json.loads(row.payload or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
