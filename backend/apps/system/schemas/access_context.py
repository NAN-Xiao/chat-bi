from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from apps.system.crud.tenant import DEFAULT_TENANT_ID, TENANT_ADMIN_ROLES, normalize_tenant_role
from apps.system.crud.user import is_platform_admin, is_platform_workspace_delegate
from apps.system.schemas.semantic_scope import SemanticRecordScopeEnum


WORKSPACE_CONTEXT_REQUIRED_MESSAGE = "当前账号尚未加入工作空间，请先创建或加入工作空间后再访问工作空间侧业务功能。"


@dataclass(frozen=True)
class AccessContext:
    tenant_id: int | None
    tenant_role: str
    is_platform_admin: bool
    is_platform_workspace_delegate: bool
    has_workspace_context: bool

    @property
    def is_global_platform(self) -> bool:
        """
        是什么：AccessContext.is_global_platform 是 backend/apps/system/schemas/access_context.py 中的同步方法。
        谁调用：由 Python 属性访问语法或依赖该属性的业务代码调用。
        做了什么：围绕 is_global_platform 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
        """
        return self.is_platform_admin and not self.is_platform_workspace_delegate

    @property
    def can_manage_platform_scope(self) -> bool:
        """
        是什么：AccessContext.can_manage_platform_scope 是 backend/apps/system/schemas/access_context.py 中的同步方法。
        谁调用：由 Python 属性访问语法或依赖该属性的业务代码调用。
        做了什么：围绕 can_manage_platform_scope 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
        """
        return self.is_global_platform

    @property
    def can_manage_workspace_scope(self) -> bool:
        """
        是什么：AccessContext.can_manage_workspace_scope 是 backend/apps/system/schemas/access_context.py 中的同步方法。
        谁调用：由 Python 属性访问语法或依赖该属性的业务代码调用。
        做了什么：围绕 can_manage_workspace_scope 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
        """
        if self.is_platform_workspace_delegate:
            return self.has_workspace_context
        if self.is_global_platform:
            return False
        return self.has_workspace_context and self.tenant_role in TENANT_ADMIN_ROLES

    @property
    def management_scope(self) -> SemanticRecordScopeEnum:
        """
        是什么：AccessContext.management_scope 是 backend/apps/system/schemas/access_context.py 中的同步方法。
        谁调用：由 Python 属性访问语法或依赖该属性的业务代码调用。
        做了什么：围绕 management_scope 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
        """
        return (
            SemanticRecordScopeEnum.PLATFORM
            if self.is_global_platform
            else SemanticRecordScopeEnum.TENANT
        )

    @property
    def management_tenant_id(self) -> int:
        """
        是什么：AccessContext.management_tenant_id 是 backend/apps/system/schemas/access_context.py 中的同步方法。
        谁调用：由 Python 属性访问语法或依赖该属性的业务代码调用。
        做了什么：围绕 management_tenant_id 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
        """
        if self.is_global_platform:
            return DEFAULT_TENANT_ID
        if not self.has_workspace_context:
            raise HTTPException(status_code=403, detail=WORKSPACE_CONTEXT_REQUIRED_MESSAGE)
        return require_tenant_id(self.tenant_id)


def current_tenant_id(current_user: Any | None) -> int | None:
    """
    是什么：current_tenant_id 是 backend/apps/system/schemas/access_context.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 current_tenant_id 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    if current_user is None:
        return None
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is None or tenant_id == "":
        return None
    try:
        return int(tenant_id)
    except (TypeError, ValueError):
        return None


def require_tenant_id(tenant_id: Any | None) -> int:
    """
    是什么：require_tenant_id 是 backend/apps/system/schemas/access_context.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    if tenant_id is None or tenant_id == "":
        raise HTTPException(status_code=403, detail=WORKSPACE_CONTEXT_REQUIRED_MESSAGE)
    try:
        return int(tenant_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=403, detail=WORKSPACE_CONTEXT_REQUIRED_MESSAGE) from exc


def require_current_tenant_id(current_user: Any | None) -> int:
    """
    是什么：require_current_tenant_id 是 backend/apps/system/schemas/access_context.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    if current_user is None:
        raise HTTPException(status_code=403, detail=WORKSPACE_CONTEXT_REQUIRED_MESSAGE)
    return require_tenant_id(getattr(current_user, "tenant_id", None))


def resolve_access_context(current_user: Any | None) -> AccessContext:
    """
    是什么：resolve_access_context 是 backend/apps/system/schemas/access_context.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 resolve_access_context 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    raw_tenant_id = getattr(current_user, "tenant_id", None) if current_user is not None else None
    tenant_role = (
        getattr(current_user, "workspace_role", None)
        or getattr(current_user, "tenant_role", None)
    )
    return AccessContext(
        tenant_id=current_tenant_id(current_user),
        tenant_role=normalize_tenant_role(tenant_role),
        is_platform_admin=is_platform_admin(current_user),
        is_platform_workspace_delegate=is_platform_workspace_delegate(current_user),
        has_workspace_context=raw_tenant_id not in (None, ""),
    )


def is_global_platform_context(current_user: Any | None) -> bool:
    """
    是什么：is_global_platform_context 是 backend/apps/system/schemas/access_context.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 is_global_platform_context 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    return resolve_access_context(current_user).is_global_platform


def has_workspace_context(current_user: Any | None) -> bool:
    """
    是什么：has_workspace_context 是 backend/apps/system/schemas/access_context.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 has_workspace_context 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    return resolve_access_context(current_user).has_workspace_context


def can_manage_platform_scope(current_user: Any | None) -> bool:
    """
    是什么：can_manage_platform_scope 是 backend/apps/system/schemas/access_context.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 can_manage_platform_scope 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    return resolve_access_context(current_user).can_manage_platform_scope


def can_manage_workspace_scope(current_user: Any | None) -> bool:
    """
    是什么：can_manage_workspace_scope 是 backend/apps/system/schemas/access_context.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 can_manage_workspace_scope 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    return resolve_access_context(current_user).can_manage_workspace_scope


def management_scope(current_user: Any | None) -> SemanticRecordScopeEnum:
    """
    是什么：management_scope 是 backend/apps/system/schemas/access_context.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 management_scope 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    return resolve_access_context(current_user).management_scope


def management_tenant_id(current_user: Any | None) -> int:
    """
    是什么：management_tenant_id 是 backend/apps/system/schemas/access_context.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 management_tenant_id 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    return resolve_access_context(current_user).management_tenant_id
