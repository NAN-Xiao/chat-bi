"""Shared routing helpers for the phase-aware knowledge management API."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from apps.knowledge_base.cutover import KnowledgeCapabilities
from apps.knowledge_base.errors import KnowledgeBusinessError
from apps.knowledge_base.models import (
    KnowledgeBase,
    KnowledgeBaseStatusEnum,
    KnowledgeBaseVisibilityScopeEnum,
)
from apps.knowledge_base.permissions import KnowledgePermissionService
from apps.system.crud.tenant import DEFAULT_TENANT_ID
from apps.system.crud.user import is_platform_admin, is_platform_workspace_delegate
from apps.system.models.tenant import TenantModel
from apps.system.schemas.access_context import current_tenant_id


def serialize_error(error: KnowledgeBusinessError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "code": error.code,
            "message": error.message,
            "field_path": error.field_path,
            "error_type": error.error_type,
            "suggestion": error.suggestion,
            "details": error.details,
        },
    )


def unexpected_error() -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "code": "KNOWLEDGE_OPERATION_FAILED",
            "message": "操作失败，请稍后重试。",
            "field_path": None,
            "error_type": "INTERNAL",
            "suggestion": "请稍后重试；如果问题持续，请联系管理员。",
        },
    )


def v2_write_error(capabilities: KnowledgeCapabilities) -> KnowledgeBusinessError | None:
    if capabilities.v2_write_enabled:
        return None
    if capabilities.management_mode == "UPGRADING":
        return KnowledgeBusinessError(
            code="KNOWLEDGE_UPGRADE_IN_PROGRESS",
            message="知识库升级中，请稍后重试。",
            status_code=409,
            error_type="CONFLICT",
        )
    if capabilities.phase.value == "LEGACY_OPEN":
        return KnowledgeBusinessError(
            code="KNOWLEDGE_V2_NOT_READY",
            message="知识库管理尚未升级完成，请稍后重试。",
            status_code=409,
            error_type="CONFLICT",
        )
    return KnowledgeBusinessError(
        code="KNOWLEDGE_MANAGEMENT_UNAVAILABLE",
        message="知识库管理暂时不可用，请稍后重试。",
        status_code=503,
        error_type="UNAVAILABLE",
    )


def validate_workspace_tenant(session: Session, tenant_id: int) -> int:
    if int(tenant_id) == DEFAULT_TENANT_ID:
        raise KnowledgeBusinessError(
            code="KNOWLEDGE_WORKSPACE_INVALID",
            message="目标工作空间不存在或已停用。",
            status_code=404,
            error_type="NOT_FOUND",
        )
    tenant = session.get(TenantModel, int(tenant_id))
    if tenant is None or int(getattr(tenant, "status", 0) or 0) != 1:
        raise KnowledgeBusinessError(
            code="KNOWLEDGE_WORKSPACE_INVALID",
            message="目标工作空间不存在或已停用。",
            status_code=404,
            error_type="NOT_FOUND",
        )
    return int(tenant.id)


def visible_tenant_ids(user: Any | None, tenant_id: int | None = None) -> tuple[int, ...]:
    if tenant_id is not None:
        if is_platform_admin(user) and not is_platform_workspace_delegate(user):
            return (int(tenant_id),)
        if current_tenant_id(user) == int(tenant_id):
            return (int(tenant_id),)
        raise KnowledgeBusinessError(
            code="KNOWLEDGE_WORKSPACE_FORBIDDEN",
            message="不能访问其他工作空间的知识库。",
            status_code=403,
            error_type="FORBIDDEN",
        )
    tenant_id = current_tenant_id(user)
    if is_platform_admin(user) and not is_platform_workspace_delegate(user):
        return (DEFAULT_TENANT_ID,)
    if tenant_id is None:
        return (DEFAULT_TENANT_ID,)
    if tenant_id == DEFAULT_TENANT_ID:
        return (DEFAULT_TENANT_ID,)
    return (tenant_id, DEFAULT_TENANT_ID)


def resolve_record(
    session: Session,
    *,
    knowledge_base_id: int,
    user: Any | None,
    tenant_id: int | None = None,
) -> KnowledgeBase:
    statement = select(KnowledgeBase).where(KnowledgeBase.id == knowledge_base_id)
    if not (is_platform_admin(user) and not is_platform_workspace_delegate(user) and tenant_id is None):
        statement = statement.where(KnowledgeBase.tenant_id.in_(visible_tenant_ids(user, tenant_id)))
    rows = session.exec(statement.order_by(KnowledgeBase.tenant_id.desc())).all()
    if not rows:
        raise KnowledgeBusinessError(
            code="KNOWLEDGE_NOT_FOUND",
            message="知识不存在或已被删除。",
            status_code=404,
            error_type="NOT_FOUND",
        )
    permission = KnowledgePermissionService()
    for row in rows:
        try:
            permission.require_read(user, row)
            return row
        except KnowledgeBusinessError:
            continue
    raise KnowledgeBusinessError(
        code="KNOWLEDGE_NOT_FOUND",
        message="知识不存在或已被删除。",
        status_code=404,
        error_type="NOT_FOUND",
    )


def record_tenant_id(record: KnowledgeBase, user: Any | None) -> int:
    scope = KnowledgeBaseVisibilityScopeEnum(record.visibility_scope)
    if scope == KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC:
        return DEFAULT_TENANT_ID
    if is_platform_admin(user) and not is_platform_workspace_delegate(user):
        return int(record.tenant_id)
    tenant_id = current_tenant_id(user)
    if tenant_id is None or int(record.tenant_id) != tenant_id:
        raise KnowledgeBusinessError(
            code="KNOWLEDGE_NOT_FOUND",
            message="知识不存在或已被删除。",
            status_code=404,
            error_type="NOT_FOUND",
        )
    return tenant_id


def serialize_record(record: KnowledgeBase, *, can_manage: bool) -> dict[str, Any]:
    return {
        "id": int(record.id),
        "tenant_id": int(record.tenant_id),
        "name": record.name,
        "description": record.description,
        "visibility_scope": KnowledgeBaseVisibilityScopeEnum(record.visibility_scope).value,
        "active": bool(record.active),
        "status": KnowledgeBaseStatusEnum(record.status).value,
        "file_id": record.file_id,
        "file_name": record.file_name,
        "file_ext": record.file_ext,
        "error_message": record.error_message,
        "create_time": record.create_time,
        "update_time": record.update_time,
        "archived": bool(record.archived),
        "knowledge_type": record.knowledge_type,
        "stable_key": record.stable_key,
        "draft_version_id": record.draft_version_id,
        "current_version_id": record.current_version_id,
        "publishing_version_id": record.publishing_version_id,
        "can_manage": can_manage,
    }
