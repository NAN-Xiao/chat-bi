"""
脚本说明：这个脚本放系统管理的接口，把前端请求接进来并交给后面的业务逻辑处理。
"""
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
    是什么：get_login_args 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    return await get_groups(session, "login")


@router.get("")
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def get_args(session: SessionDep) -> list[SysArgModel]:
    """
    是什么：get_args 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    return await get_parameter_args(session)


@router.post("", )
@require_permissions(permission=AppPermission(role=['platform_admin']))
@system_log(LogConfig(operation_type=OperationType.UPDATE, module=OperationModules.PARAMS_SETTING))
async def save_args(session: SessionDep, request: Request):
    """
    是什么：save_args 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：创建或保存系统管理需要的东西，让后续流程能继续往下走。
    """
    return await save_parameter_args(session=session, request=request)


@router.get("/chat")
async def get_chat_args(session: SessionDep) -> list[SysArgModel]:
    """
    是什么：get_chat_args 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    return await get_groups(session, "chat")
