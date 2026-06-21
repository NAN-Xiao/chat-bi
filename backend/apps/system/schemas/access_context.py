from dataclasses import dataclass
from typing import Any

from apps.system.crud.tenant import DEFAULT_TENANT_ID, TENANT_ADMIN_ROLES, normalize_tenant_role
from apps.system.crud.user import is_platform_admin, is_platform_workspace_delegate
from apps.system.schemas.semantic_scope import SemanticRecordScopeEnum


@dataclass(frozen=True)
class AccessContext:
    tenant_id: int | None
    tenant_role: str
    is_platform_admin: bool
    is_platform_workspace_delegate: bool
    has_workspace_context: bool

    @property
    def is_global_platform(self) -> bool:
        return self.is_platform_admin and not self.is_platform_workspace_delegate

    @property
    def can_manage_platform_scope(self) -> bool:
        return self.is_global_platform

    @property
    def can_manage_workspace_scope(self) -> bool:
        if self.is_platform_workspace_delegate:
            return True
        if self.is_global_platform:
            return False
        return self.tenant_role in TENANT_ADMIN_ROLES

    @property
    def management_scope(self) -> SemanticRecordScopeEnum:
        return (
            SemanticRecordScopeEnum.PLATFORM
            if self.is_global_platform
            else SemanticRecordScopeEnum.TENANT
        )

    @property
    def management_tenant_id(self) -> int:
        return DEFAULT_TENANT_ID if self.is_global_platform else int(self.tenant_id or DEFAULT_TENANT_ID)


def current_tenant_id(current_user: Any | None) -> int | None:
    if current_user is None:
        return None
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is None or tenant_id == "":
        return DEFAULT_TENANT_ID
    try:
        return int(tenant_id)
    except (TypeError, ValueError):
        return None


def resolve_access_context(current_user: Any | None) -> AccessContext:
    raw_tenant_id = getattr(current_user, "tenant_id", None) if current_user is not None else None
    return AccessContext(
        tenant_id=current_tenant_id(current_user),
        tenant_role=normalize_tenant_role(getattr(current_user, "tenant_role", None)),
        is_platform_admin=is_platform_admin(current_user),
        is_platform_workspace_delegate=is_platform_workspace_delegate(current_user),
        has_workspace_context=raw_tenant_id not in (None, ""),
    )


def is_global_platform_context(current_user: Any | None) -> bool:
    return resolve_access_context(current_user).is_global_platform


def has_workspace_context(current_user: Any | None) -> bool:
    return resolve_access_context(current_user).has_workspace_context


def can_manage_platform_scope(current_user: Any | None) -> bool:
    return resolve_access_context(current_user).can_manage_platform_scope


def can_manage_workspace_scope(current_user: Any | None) -> bool:
    return resolve_access_context(current_user).can_manage_workspace_scope


def management_scope(current_user: Any | None) -> SemanticRecordScopeEnum:
    return resolve_access_context(current_user).management_scope


def management_tenant_id(current_user: Any | None) -> int:
    return resolve_access_context(current_user).management_tenant_id
