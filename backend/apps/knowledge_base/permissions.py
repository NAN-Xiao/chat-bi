"""Scope and role checks shared by management services and future routes."""

from __future__ import annotations

from typing import Any

from apps.knowledge_base.errors import KnowledgeBusinessError
from apps.knowledge_base.models import (
    KnowledgeBase,
    KnowledgeBaseVisibilityScopeEnum,
)
from apps.system.crud.tenant import (
    DEFAULT_TENANT_ID,
    TENANT_ADMIN_ROLES,
    normalize_tenant_role,
)
from apps.system.crud.user import is_platform_admin, is_platform_workspace_delegate
from apps.system.schemas.access_context import current_tenant_id


class KnowledgePermissionService:
    """Enforce platform/workspace ownership without trusting request tenant IDs."""

    def is_global_platform_admin(self, user: Any | None) -> bool:
        return bool(is_platform_admin(user) and not is_platform_workspace_delegate(user))

    def can_manage_workspace(self, user: Any | None, tenant_id: int) -> bool:
        if is_platform_workspace_delegate(user):
            return current_tenant_id(user) == tenant_id
        if self.is_global_platform_admin(user):
            return False
        return (
            current_tenant_id(user) == tenant_id
            and normalize_tenant_role(getattr(user, "tenant_role", None)) in TENANT_ADMIN_ROLES
        )

    def can_read_workspace(self, user: Any | None, tenant_id: int) -> bool:
        return current_tenant_id(user) == tenant_id

    def require_manage(self, user: Any | None, record: KnowledgeBase) -> None:
        scope = KnowledgeBaseVisibilityScopeEnum(record.visibility_scope)
        if scope == KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC:
            if not self.is_global_platform_admin(user) or int(record.tenant_id) != DEFAULT_TENANT_ID:
                raise self._forbidden()
            return
        if int(record.tenant_id) != int(current_tenant_id(user) or -1):
            raise self._not_found()
        if not self.can_manage_workspace(user, int(record.tenant_id)):
            raise self._forbidden()

    def require_read(self, user: Any | None, record: KnowledgeBase) -> None:
        scope = KnowledgeBaseVisibilityScopeEnum(record.visibility_scope)
        if scope == KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC:
            if int(record.tenant_id) != DEFAULT_TENANT_ID or user is None:
                raise self._not_found()
            return
        if not self.can_read_workspace(user, int(record.tenant_id)):
            raise self._not_found()

    def require_workspace_override(self, user: Any | None, record: KnowledgeBase) -> int:
        if KnowledgeBaseVisibilityScopeEnum(record.visibility_scope) != KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_SCOPE_INVALID",
                message="只有平台公共知识支持工作空间启停。",
                status_code=400,
                error_type="VALIDATION",
            )
        tenant_id = current_tenant_id(user)
        if tenant_id is None or not self.can_manage_workspace(user, tenant_id):
            raise self._forbidden()
        return tenant_id

    @staticmethod
    def _forbidden() -> KnowledgeBusinessError:
        return KnowledgeBusinessError(
            code="KNOWLEDGE_FORBIDDEN",
            message="您没有权限执行此操作。",
            status_code=403,
            error_type="FORBIDDEN",
        )

    @staticmethod
    def _not_found() -> KnowledgeBusinessError:
        return KnowledgeBusinessError(
            code="KNOWLEDGE_NOT_FOUND",
            message="知识不存在或已被删除。",
            status_code=404,
            error_type="NOT_FOUND",
        )
