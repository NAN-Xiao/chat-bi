"""
脚本说明：这个脚本定义系统管理的输入输出结构，帮接口和业务代码统一数据格式。
"""
from fastapi import HTTPException

from apps.system.crud.user import is_platform_admin, is_platform_workspace_delegate
from apps.system.schemas.system_schema import UserInfoDTO
from common.core.deps import CurrentUser, Trans


CHATBI_FORBIDDEN_MESSAGE = "SaaS 管理员用于 SaaS 后台运营管理，不能访问工作空间侧 ChatBI 业务功能。"
TENANT_REQUIRED_MESSAGE = "当前账号尚未加入工作空间，请先创建或加入工作空间后再访问工作空间侧业务功能。"


def ensure_chatbi_business_user(current_user: UserInfoDTO, trans=None) -> None:
    """
    是什么：ensure_chatbi_business_user 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    if is_platform_workspace_delegate(current_user):
        if not getattr(current_user, "tenant_id", None):
            raise HTTPException(status_code=403, detail=TENANT_REQUIRED_MESSAGE)
        return
    if is_platform_admin(current_user):
        message = (
            trans("i18n_permission.platform_admin_chatbi_forbidden")
            if trans
            else CHATBI_FORBIDDEN_MESSAGE
        )
        raise HTTPException(status_code=403, detail=message)
    if not getattr(current_user, "tenant_id", None):
        raise HTTPException(status_code=403, detail=TENANT_REQUIRED_MESSAGE)


async def require_chatbi_business_user(current_user: CurrentUser, trans: Trans):
    """
    是什么：require_chatbi_business_user 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    ensure_chatbi_business_user(current_user, trans)


def ensure_chatbi_business_or_platform_admin(current_user: UserInfoDTO, trans=None) -> None:
    """
    是什么：ensure_chatbi_business_or_platform_admin 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    if is_platform_admin(current_user):
        return
    ensure_chatbi_business_user(current_user, trans)


async def require_chatbi_business_or_platform_admin(current_user: CurrentUser, trans: Trans):
    """
    是什么：require_chatbi_business_or_platform_admin 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    ensure_chatbi_business_or_platform_admin(current_user, trans)
