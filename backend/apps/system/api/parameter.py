from fastapi import APIRouter, Request

from apps.system.crud.parameter_manage import get_groups, get_parameter_args, save_parameter_args
from apps.system.models.system_model import SysArgModel
from apps.system.schemas.permission import AppPermission, require_permissions
from common.core.deps import SessionDep

router = APIRouter(tags=["system/parameter"], prefix="/system/parameter", include_in_schema=False)
from common.audit.models.log_model import OperationType, OperationModules
from common.audit.schemas.logger_decorator import LogConfig, system_log

@router.get("/login")
async def get_login_args(session: SessionDep) -> list[SysArgModel]:
    """
    是什么：get_login_args 是 backend/apps/system/api/parameter.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：读取或查询系统管理相关数据，整理后返回给调用方。
    """
    return await get_groups(session, "login")


@router.get("")
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def get_args(session: SessionDep) -> list[SysArgModel]:
    """
    是什么：get_args 是 backend/apps/system/api/parameter.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：读取或查询系统管理相关数据，整理后返回给调用方。
    """
    return await get_parameter_args(session)


@router.post("", )
@require_permissions(permission=AppPermission(role=['platform_admin']))
@system_log(LogConfig(operation_type=OperationType.UPDATE, module=OperationModules.PARAMS_SETTING))
async def save_args(session: SessionDep, request: Request):
    """
    是什么：save_args 是 backend/apps/system/api/parameter.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：创建、初始化或组装系统管理相关对象和数据，并返回或写入对应状态。
    """
    return await save_parameter_args(session=session, request=request)


@router.get("/chat")
async def get_chat_args(session: SessionDep) -> list[SysArgModel]:
    """
    是什么：get_chat_args 是 backend/apps/system/api/parameter.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：读取或查询系统管理相关数据，整理后返回给调用方。
    """
    return await get_groups(session, "chat")
