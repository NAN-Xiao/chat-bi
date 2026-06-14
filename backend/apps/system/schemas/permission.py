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
from apps.system.schemas.system_schema import UserInfoDTO

from common.utils.locale import I18n
i18n = I18n()

class SqlbotPermission(BaseModel):
    role: Optional[list[str]] = None
    type: Optional[str] = None
    keyExpression: Optional[str] = None

def _required_project_role(role_list: Optional[list[str]]) -> Optional[str]:
    if not role_list:
        return None
    for role in ("project_admin", "project_editor", "project_viewer"):
        if role in role_list:
            return role
    return None


async def check_project_permission(
        current_user: UserInfoDTO,
        type,
        resource,
        role_list: Optional[list[str]] = None,
) -> bool:
    if not resource or (isinstance(resource, list) and len(resource) == 0):
        return True

    if type == 'ds' or type == 'datasource':
        from apps.datasource.crud.permission import has_datasource_access, has_datasource_role

        with Session(engine) as session:
            required_role = _required_project_role(role_list)
            if required_role:
                return has_datasource_role(session, current_user, resource, required_role)
            return has_datasource_access(session, current_user, resource)

    if type == 'chat':
        try:
            requested_ids = resource if isinstance(resource, list) else [resource]
            chat_ids = {int(item) for item in requested_ids}
        except (TypeError, ValueError):
            return False
        if current_user.isAdmin:
            return True
        with Session(engine) as session:
            owned_count = session.exec(
                select(Chat.id).where(Chat.id.in_(chat_ids), Chat.create_by == current_user.id)
            ).all()
            return chat_ids.issubset({int(item) for item in owned_count})

    return True
        
 
def require_permissions(permission: SqlbotPermission):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = RequestContext.get_request()
            
            current_user: UserInfoDTO = getattr(request.state, 'current_user', None)
            if not current_user:
                raise HTTPException(
                    status_code=401,
                    detail="用户未认证"
                )
            trans = i18n(request)
            
            if current_user.isAdmin and not permission.type:
                return await func(*args, **kwargs)
            role_list = permission.role
            keyExpression = permission.keyExpression
            resource_type = permission.type
            
            if role_list:
                if 'admin' in role_list and not current_user.isAdmin:
                    #raise Exception('no permission to execute, only for admin')
                    raise Exception(trans('i18n_permission.only_admin'))
                if (
                    any(role in role_list for role in ('project_admin', 'project_editor', 'project_viewer'))
                    and not resource_type
                    and not current_user.isAdmin
                ):
                    raise Exception(trans('i18n_permission.only_project_admin'))
            if not resource_type:
                return await func(*args, **kwargs)
            if keyExpression:
                sig = signature(func)
                bound_args = sig.bind_partial(*args, **kwargs)
                bound_args.apply_defaults()
                
                if keyExpression.startswith("args["):
                    if match := re.match(r"args\[(\d+)\]", keyExpression):
                        index = int(match.group(1))
                        value = bound_args.args[index]
                        if await check_project_permission(current_user, resource_type, value, role_list):
                            return await func(*args, **kwargs)
                        #raise Exception('no permission to execute or resource do not exist!')
                        raise Exception(trans('i18n_permission.permission_resource_limit'))
                            
                parts = keyExpression.split('.')
                if not bound_args.arguments.get(parts[0]):
                    return await func(*args, **kwargs)
                value = bound_args.arguments[parts[0]]
                for part in parts[1:]:
                    value = getattr(value, part)
                if await check_project_permission(current_user, resource_type, value, role_list):
                    return await func(*args, **kwargs)
                raise Exception(trans('i18n_permission.permission_resource_limit'))
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator

class RequestContext:
    
    _current_request: ContextVar[Request] = ContextVar("_current_request")
    @classmethod
    def set_request(cls, request: Request):
        return cls._current_request.set(request)
    
    @classmetho