"""
脚本说明：这个脚本定义系统管理的输入输出结构，帮接口和业务代码统一数据格式。
"""
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from apps.system.crud.tenant import DEFAULT_TENANT_ID, TENANT_ADMIN_ROLES, normalize_tenant_role
from apps.system.crud.user import is_platform_admin, is_platform_workspace_delegate
from apps.system.schemas.semantic_scope import SemanticRecordScopeEnum


WORKSPACE_CONTEXT_REQUIRED_MESSAGE = "当前账号尚未加入工作空间，请先创建或加入工作空间后再访问工作空间侧业务功能。"


@dataclass(frozen=True)
class AccessContext:
    """
    类说明：AccessContext 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    tenant_id: int | None
    tenant_role: str
    is_platform_admin: bool
    is_platform_workspace_delegate: bool
    has_workspace_context: bool

    @property
    def is_global_platform(self) -> bool:
        """
        是什么：AccessContext.is_global_platform 是 AccessContext 里的一个步骤，帮它完成系统管理相关的一件事。
        谁调用：其他代码像读取属性一样访问它时，Python 会调用它。
        做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return self.is_platform_admin and not self.is_platform_workspace_delegate

    @property
    def can_manage_platform_scope(self) -> bool:
        """
        是什么：AccessContext.can_manage_platform_scope 是 AccessContext 里的一个步骤，帮它完成系统管理相关的一件事。
        谁调用：其他代码像读取属性一样访问它时，Python 会调用它。
        做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return self.is_global_platform

    @property
    def can_manage_workspace_scope(self) -> bool:
        """
        是什么：AccessContext.can_manage_workspace_scope 是 AccessContext 里的一个步骤，帮它完成系统管理相关的一件事。
        谁调用：其他代码像读取属性一样访问它时，Python 会调用它。
        做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        if self.is_platform_workspace_delegate:
            return self.has_workspace_context
        if self.is_global_platform:
            return False
        return self.has_workspace_context and self.tenant_role in TENANT_ADMIN_ROLES

    @property
    def management_scope(self) -> SemanticRecordScopeEnum:
        """
        是什么：AccessContext.management_scope 是 AccessContext 里的一个步骤，帮它完成系统管理相关的一件事。
        谁调用：其他代码像读取属性一样访问它时，Python 会调用它。
        做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return (
            SemanticRecordScopeEnum.PLATFORM
            if self.is_global_platform
            else SemanticRecordScopeEnum.TENANT
        )

    @property
    def management_tenant_id(self) -> int:
        """
        是什么：AccessContext.management_tenant_id 是 AccessContext 里的一个步骤，帮它完成系统管理相关的一件事。
        谁调用：其他代码像读取属性一样访问它时，Python 会调用它。
        做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        if self.is_global_platform:
            return DEFAULT_TENANT_ID
        if not self.has_workspace_context:
            raise HTTPException(status_code=403, detail=WORKSPACE_CONTEXT_REQUIRED_MESSAGE)
        return require_tenant_id(self.tenant_id)


def current_tenant_id(current_user: Any | None) -> int | None:
    """
    是什么：current_tenant_id 是从当前用户里取租户 ID 的小工具。
    谁调用：需要知道当前用户属于哪个租户的接口会调用它。
    做了什么：把用户上下文里的租户 ID 取出来，方便后面做权限和数据隔离。
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
    是什么：require_tenant_id 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    if tenant_id is None or tenant_id == "":
        raise HTTPException(status_code=403, detail=WORKSPACE_CONTEXT_REQUIRED_MESSAGE)
    try:
        return int(tenant_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=403, detail=WORKSPACE_CONTEXT_REQUIRED_MESSAGE) from exc


def require_current_tenant_id(current_user: Any | None) -> int:
    """
    是什么：require_current_tenant_id 是从当前用户里取租户 ID 的小工具。
    谁调用：需要知道当前用户属于哪个租户的接口会调用它。
    做了什么：把用户上下文里的租户 ID 取出来，方便后面做权限和数据隔离。
    """
    if current_user is None:
        raise HTTPException(status_code=403, detail=WORKSPACE_CONTEXT_REQUIRED_MESSAGE)
    return require_tenant_id(getattr(current_user, "tenant_id", None))


def resolve_access_context(current_user: Any | None) -> AccessContext:
    """
    是什么：resolve_access_context 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
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
    是什么：is_global_platform_context 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return resolve_access_context(current_user).is_global_platform


def has_workspace_context(current_user: Any | None) -> bool:
    """
    是什么：has_workspace_context 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return resolve_access_context(current_user).has_workspace_context


def can_manage_platform_scope(current_user: Any | None) -> bool:
    """
    是什么：can_manage_platform_scope 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return resolve_access_context(current_user).can_manage_platform_scope


def can_manage_workspace_scope(current_user: Any | None) -> bool:
    """
    是什么：can_manage_workspace_scope 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return resolve_access_context(current_user).can_manage_workspace_scope


def management_scope(current_user: Any | None) -> SemanticRecordScopeEnum:
    """
    是什么：management_scope 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return resolve_access_context(current_user).management_scope


def management_tenant_id(current_user: Any | None) -> int:
    """
    是什么：management_tenant_id 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return resolve_access_context(current_user).management_tenant_id
