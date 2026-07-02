"""
脚本说明：这个脚本封装系统管理的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""

from sqlmodel import Session, func, select
from apps.system.crud.tenant import user_belongs_to_tenant
from apps.system.schemas.auth import CacheName, CacheNamespace
from apps.system.schemas.system_schema import EMAIL_REGEX, PWD_REGEX, BaseUserDTO, UserInfoDTO
from common.core.app_cache import cache, clear_cache
from common.utils.utils import AppLogUtil
from ..models.user import UserModel
from common.core.security import hash_password, verify_stored_password

SYSTEM_ROLE_SYSTEM_ADMIN = "system_admin"
SYSTEM_ROLE_COLLAB_ADMIN = "collab_admin"
SYSTEM_ROLE_VIEWER = "viewer"
SYSTEM_ADMIN_ROLES = {
    SYSTEM_ROLE_SYSTEM_ADMIN,
    SYSTEM_ROLE_COLLAB_ADMIN,
}
SYSTEM_ROLE_ORDER = {
    SYSTEM_ROLE_VIEWER: 10,
    SYSTEM_ROLE_COLLAB_ADMIN: 20,
    SYSTEM_ROLE_SYSTEM_ADMIN: 30,
}


def normalize_system_role(role: str | None) -> str:
    """
    是什么：normalize_system_role 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if not role:
        return SYSTEM_ROLE_VIEWER
    normalized = str(role).strip().lower()
    return normalized if normalized in SYSTEM_ROLE_ORDER else SYSTEM_ROLE_VIEWER


def is_system_admin(user) -> bool:
    """
    是什么：is_system_admin 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if user is None:
        return False
    if hasattr(user, "system_role"):
        return normalize_system_role(getattr(user, "system_role", None)) in SYSTEM_ADMIN_ROLES
    return bool(getattr(user, "isAdmin", False))


def is_platform_admin(user) -> bool:
    """
    是什么：is_platform_admin 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return is_system_admin(user)


def is_platform_workspace_delegate(user) -> bool:
    """
    是什么：is_platform_workspace_delegate 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return (
        is_platform_admin(user)
        and getattr(user, "tenant_id", None) not in (None, "")
        and getattr(user, "workspace_status", None) == "platform_workspace_delegate"
    )


def is_super_admin(user) -> bool:
    """
    是什么：is_super_admin 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if user is None or not hasattr(user, "system_role"):
        return False
    return normalize_system_role(getattr(user, "system_role", None)) == SYSTEM_ROLE_SYSTEM_ADMIN


def is_collab_admin(user) -> bool:
    """
    是什么：is_collab_admin 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if user is None or not hasattr(user, "system_role"):
        return False
    return normalize_system_role(getattr(user, "system_role", None)) == SYSTEM_ROLE_COLLAB_ADMIN


def is_high_privilege_system_role(role: str | None) -> bool:
    """
    是什么：is_high_privilege_system_role 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return normalize_system_role(role) in SYSTEM_ADMIN_ROLES


def is_high_privilege_user(user) -> bool:
    """
    是什么：is_high_privilege_user 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if user is None or not hasattr(user, "system_role"):
        return False
    return is_high_privilege_system_role(getattr(user, "system_role", None))


def apply_user_role_flags(user_info: UserInfoDTO) -> UserInfoDTO:
    """
    是什么：apply_user_role_flags 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    user_info.system_role = normalize_system_role(getattr(user_info, "system_role", None))
    user_info.isAdmin = is_system_admin(user_info)
    user_info.global_role = "platform_admin" if is_platform_admin(user_info) else "normal_user"
    return user_info


def get_db_user(*, session: Session, user_id: int) -> UserModel:
    """
    是什么：get_db_user 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    db_user = session.get(UserModel, user_id)
    return db_user

def get_user_by_account(*, session: Session, account: str) -> BaseUserDTO | None:
    """
    是什么：get_user_by_account 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    statement = select(UserModel).where(UserModel.account == account)
    db_user = session.exec(statement).first()
    if not db_user:
        return None
    return BaseUserDTO.model_validate(db_user.model_dump())

@cache(
    namespace=CacheNamespace.AUTH_INFO,
    cacheName=CacheName.USER_INFO,
    keyExpression="user_id",
    scope="tenant",
    tenantExpression="tenant_id",
)
async def get_user_info(*, session: Session, user_id: int, tenant_id: int | None = None) -> UserInfoDTO | None:
    """
    是什么：get_user_info 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    _ = tenant_id
    db_user: UserModel = get_db_user(session = session, user_id = user_id)
    if not db_user:
        return None
    userInfo = UserInfoDTO.model_validate(db_user.model_dump())
    return apply_user_role_flags(userInfo)

def authenticate(*, session: Session, account: str, password: str) -> BaseUserDTO | None:
    """
    是什么：authenticate 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    statement = select(UserModel).where(UserModel.account == account)
    db_user = session.exec(statement).first()
    if not db_user:
        return None
    valid_password, needs_rehash = verify_stored_password(password, db_user.password)
    if not valid_password:
        return None
    if needs_rehash:
        db_user.password = hash_password(password)
        session.add(db_user)
    return BaseUserDTO.model_validate(db_user.model_dump())

@clear_cache(
    namespace=CacheNamespace.AUTH_INFO,
    cacheName=CacheName.USER_INFO,
    keyExpression="user_id",
    scope="tenant",
    tenantExpression="tenant_ids",
)
async def clear_user_info_cache(
    *,
    user_id: int,
    tenant_ids: list[int],
    session: Session | None = None,
):
    """
    是什么：clear_user_info_cache 清理指定用户在多个租户分片下的鉴权缓存。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：用户状态、密码、资料和成员关系变化后，按目标用户租户边界失效缓存。
    """
    _ = session
    AppLogUtil.info(f"User cache for [{user_id}] has been cleaned in tenants {tenant_ids}")


def check_account_exists(*, session: Session, account: str) -> bool:
    """
    是什么：check_account_exists 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    return session.exec(select(func.count()).select_from(UserModel).where(UserModel.account == account)).one() > 0


def check_user_in_tenant(*, session: Session, user_id: int, tenant_id: int | None) -> bool:
    """
    是什么：check_user_in_tenant 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    return user_belongs_to_tenant(session, user_id, tenant_id)
def check_email_exists(*, session: Session, email: str) -> bool:
    """
    是什么：check_email_exists 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    return session.exec(select(func.count()).select_from(UserModel).where(UserModel.email == email)).one() > 0



def check_email_format(email: str) -> bool:
    """
    是什么：check_email_format 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    return bool(EMAIL_REGEX.fullmatch(email))

def check_pwd_format(pwd: str) -> bool:
    """
    是什么：check_pwd_format 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    return bool(PWD_REGEX.fullmatch(pwd))
