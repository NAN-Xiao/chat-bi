from contextvars import ContextVar
from functools import wraps
from inspect import signature
from typing import Optional
from fastapi import HTTPException, Request
from pydantic import BaseModel
import re
from starlette.middleware.base import BaseHTTPMiddleware
from sqlmodel import Session, select
from apps.chat.models.chat_model import Chat
from common.core.db import engine
from apps.system.crud.tenant import TENANT_ADMIN_ROLES, normalize_tenant_role
from apps.system.crud.user import is_platform_admin, is_system_admin
from apps.system.schemas.access_context import require_current_tenant_id
from apps.system.schemas.system_schema import UserInfoDTO

from common.utils.locale import I18n
i18n = I18n()

class AppPermission(BaseModel):
    role: Optional[list[str]] = None
    type: Optional[str] = None
    keyExpression: Optional[str] = None

def _required_project_role(role_list: Optional[list[str]]) -> Optional[str]:
    """
    是什么：_required_project_role 是 backend/apps/system/schemas/permission.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    if not role_list:
        return None
    for role in ("project_editor", "project_viewer"):
        if role in role_list:
            return role
    return None


def _is_system_admin(current_user: UserInfoDTO) -> bool:
    """
    是什么：_is_system_admin 是 backend/apps/system/schemas/permission.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _is_system_admin 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    return is_system_admin(current_user)


def _is_platform_admin(current_user: UserInfoDTO) -> bool:
    """
    是什么：_is_platform_admin 是 backend/apps/system/schemas/permission.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _is_platform_admin 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    return is_platform_admin(current_user)


def _is_tenant_admin(current_user: UserInfoDTO) -> bool:
    """
    是什么：_is_tenant_admin 是 backend/apps/system/schemas/permission.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _is_tenant_admin 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    tenant_role = normalize_tenant_role(getattr(current_user, "tenant_role", None))
    return _is_platform_admin(current_user) or tenant_role in TENANT_ADMIN_ROLES


def _has_admin_permission(current_user: UserInfoDTO) -> bool:
    """
    是什么：_has_admin_permission 是 backend/apps/system/schemas/permission.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_admin_permission 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    return _is_tenant_admin(current_user) or _is_system_admin(current_user)


def _resource_is_empty(resource) -> bool:
    """
    是什么：_resource_is_empty 是 backend/apps/system/schemas/permission.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _resource_is_empty 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    if resource is None or resource == "":
        return True
    if isinstance(resource, (list, tuple, set, dict)) and len(resource) == 0:
        return True
    return False


def _deny_permission(trans):
    """
    是什么：_deny_permission 是 backend/apps/system/schemas/permission.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _deny_permission 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    raise HTTPException(
        status_code=403,
        detail=trans('i18n_permission.permission_resource_limit'),
    )


def _resolve_part(value, part: str):
    """
    是什么：_resolve_part 是 backend/apps/system/schemas/permission.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _resolve_part 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    if value is None:
        raise ValueError("resource path contains null value")
    if isinstance(value, dict):
        if part not in value:
            raise ValueError(f"resource path key not found: {part}")
        return value[part]
    if hasattr(value, part):
        return getattr(value, part)
    raise ValueError(f"resource path attribute not found: {part}")


def _resolve_key_expression(func, args, kwargs, key_expression: str):
    """
    是什么：_resolve_key_expression 是 backend/apps/system/schemas/permission.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _resolve_key_expression 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    expression = (key_expression or "").strip()
    if not expression:
        raise ValueError("resource keyExpression is empty")

    sig = signature(func)
    bound_args = sig.bind_partial(*args, **kwargs)
    bound_args.apply_defaults()

    match = re.match(r"^args\[(\d+)\](?:\.(.+))?$", expression)
    if match:
        index = int(match.group(1))
        if index >= len(bound_args.args):
            raise ValueError("resource args index out of range")
        value = bound_args.args[index]
        remaining = match.group(2)
        parts = remaining.split('.') if remaining else []
    else:
        parts = expression.split('.')
        if not parts or parts[0] not in bound_args.arguments:
            raise ValueError("resource base argument not found")
        value = bound_args.arguments[parts[0]]
        parts = parts[1:]

    for part in parts:
        if not part:
            raise ValueError("resource path contains empty segment")
        value = _resolve_part(value, part)

    return value


async def check_project_permission(
        current_user: UserInfoDTO,
        type,
        resource,
        role_list: Optional[list[str]] = None,
) -> bool:
    """
    是什么：check_project_permission 是 backend/apps/system/schemas/permission.py 中的异步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    if _has_admin_permission(current_user) and type not in {'ds', 'datasource', 'table', 'field'}:
        return True

    if _resource_is_empty(resource):
        return False

    if type == 'ds' or type == 'datasource':
        from apps.datasource.crud.permission import has_datasource_access, has_datasource_role

        with Session(engine) as session:
            required_role = _required_project_role(role_list)
            if required_role:
                return has_datasource_role(session, current_user, resource, required_role)
            return has_datasource_access(session, current_user, resource)

    if type == 'table':
        from apps.datasource.crud.permission import has_datasource_role
        from apps.datasource.models.datasource import CoreTable

        try:
            table_id = int(resource)
        except (TypeError, ValueError):
            return False
        with Session(engine) as session:
            row = session.exec(select(CoreTable.ds_id).where(CoreTable.id == table_id)).first()
            if row is None:
                return False
            required_role = _required_project_role(role_list) or "project_viewer"
            return has_datasource_role(session, current_user, row, required_role)

    if type == 'field':
        from apps.datasource.crud.permission import has_datasource_role
        from apps.datasource.models.datasource import CoreField

        try:
            field_id = int(resource)
        except (TypeError, ValueError):
            return False
        with Session(engine) as session:
            row = session.exec(select(CoreField.ds_id).where(CoreField.id == field_id)).first()
            if row is None:
                return False
            required_role = _required_project_role(role_list) or "project_viewer"
            return has_datasource_role(session, current_user, row, required_role)

    if type == 'chat':
        try:
            requested_ids = resource if isinstance(resource, list) else [resource]
            chat_ids = {int(item) for item in requested_ids}
        except (TypeError, ValueError):
            return False
        tenant_id = require_current_tenant_id(current_user)
        filters = [
            Chat.id.in_(chat_ids),
            Chat.tenant_id == tenant_id,
        ]
        if not _has_admin_permission(current_user):
            filters.append(Chat.create_by == current_user.id)
        with Session(engine) as session:
            owned_count = session.exec(
                select(Chat.id).where(*filters)
            ).all()
            return chat_ids.issubset({int(item) for item in owned_count})

    return False
        
 
def require_permissions(permission: AppPermission):
    """
    是什么：require_permissions 是 backend/apps/system/schemas/permission.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    def decorator(func):
        """
        是什么：decorator 是 backend/apps/system/schemas/permission.py 中的同步函数。
        谁调用：由外层函数 require_permissions 在执行内部流程时调用。
        做了什么：围绕 decorator 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
        """
        @wraps(func)
        async def wrapper(*args, **kwargs):
            """
            是什么：wrapper 是 backend/apps/system/schemas/permission.py 中的异步函数。
            谁调用：由外层函数 decorator 在执行内部流程时调用。
            做了什么：围绕 wrapper 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
            """
            request = RequestContext.get_request()
            
            current_user: UserInfoDTO = getattr(request.state, 'current_user', None)
            if not current_user:
                raise HTTPException(
                    status_code=401,
                    detail="用户未认证"
                )
            trans = i18n(request)
            
            role_list = permission.role
            keyExpression = permission.keyExpression
            resource_type = permission.type
            
            if role_list:
                if 'platform_admin' in role_list and not _is_platform_admin(current_user):
                    raise HTTPException(status_code=403, detail=trans('i18n_permission.only_admin'))
                if (
                    ('admin' in role_list or 'tenant_admin' in role_list)
                    and not _has_admin_permission(current_user)
                ):
                    raise HTTPException(status_code=403, detail=trans('i18n_permission.only_admin'))
                if (
                    any(role in role_list for role in ('project_editor', 'project_viewer'))
                    and not resource_type
                    and not _has_admin_permission(current_user)
                ):
                    raise HTTPException(status_code=403, detail=trans('i18n_permission.only_project_role'))
            is_admin = _has_admin_permission(current_user)
            if is_admin and not permission.type:
                return await func(*args, **kwargs)
            if not resource_type:
                return await func(*args, **kwargs)

            if not keyExpression:
                _deny_permission(trans)

            try:
                value = _resolve_key_expression(func, args, kwargs, keyExpression)
            except Exception:
                _deny_permission(trans)

            if _resource_is_empty(value):
                _deny_permission(trans)

            if await check_project_permission(current_user, resource_type, value, role_list):
                return await func(*args, **kwargs)
            _deny_permission(trans)
        
        return wrapper
    return decorator

class RequestContext:
    
    _current_request: ContextVar[Request] = ContextVar("_current_request")
    @classmethod
    def set_request(cls, request: Request):
        """
        是什么：RequestContext.set_request 是 backend/apps/system/schemas/permission.py 中的同步方法。
        谁调用：由类本身、子类或框架按照类方法约定调用。
        做了什么：更新系统管理相关状态、配置或持久化数据，并保持后续流程可继续使用。
        """
        return cls._current_request.set(request)
    
    @classmethod
    def get_request(cls) -> Request:
        """
        是什么：RequestContext.get_request 是 backend/apps/system/schemas/permission.py 中的同步方法。
        谁调用：由类本身、子类或框架按照类方法约定调用。
        做了什么：读取或查询系统管理相关数据，整理后返回给调用方。
        """
        try:
            return cls._current_request.get()
        except LookupError:
            raise RuntimeError(
                "No request context found. "
                "Make sure RequestContextMiddleware is installed."
            )
    
    @classmethod
    def reset(cls, token):
        """
        是什么：RequestContext.reset 是 backend/apps/system/schemas/permission.py 中的同步方法。
        谁调用：由类本身、子类或框架按照类方法约定调用。
        做了什么：删除或清理系统管理相关数据、缓存或临时状态。
        """
        cls._current_request.reset(token)

class RequestContextMiddleware(BaseHTTPMiddleware):
    
    async def dispatch(self, request: Request, call_next):
        """
        是什么：RequestContextMiddleware.dispatch 是 backend/apps/system/schemas/permission.py 中的异步方法。
        谁调用：由持有 RequestContextMiddleware 实例的业务代码、框架回调或测试代码调用。
        做了什么：执行系统管理主流程，协调下游服务并处理结果或异常。
        """
        token = RequestContext.set_request(request)
        try:
            response = await call_next(request)
            return response
        finally:
            RequestContext.reset(token)
