"""
脚本说明：这个脚本放系统管理的接口，把前端请求接进来并交给后面的业务逻辑处理。
"""
# 作者：Junjun
# 日期：2026/1/26
from typing import List
from fastapi import APIRouter

from apps.swagger.i18n import PLACEHOLDER_PREFIX
from apps.system.crud.system_variable import save, delete, list_all, list_page
from apps.system.models.system_variable_model import SystemVariable
from common.core.config import settings
from common.core.deps import SessionDep, CurrentUser, Trans
from apps.system.schemas.permission import AppPermission, require_permissions

router = APIRouter(tags=["System_variable"], prefix="/sys_variable")
path = settings.EXCEL_PATH


@router.post("/save", response_model=None, summary=f"{PLACEHOLDER_PREFIX}variable_save")
@require_permissions(permission=AppPermission(role=['admin']))
async def save_variable(session: SessionDep, user: CurrentUser, trans: Trans, variable: SystemVariable):
    """
    是什么：save_variable 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：创建或保存系统管理需要的东西，让后续流程能继续往下走。
    """
    return save(session, user, trans, variable)


@router.post("/delete",response_model=None, summary=f"{PLACEHOLDER_PREFIX}variable_delete")
@require_permissions(permission=AppPermission(role=['admin']))
async def delete_variable(session: SessionDep, user: CurrentUser, ids: List[int]):
    """
    是什么：delete_variable 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理不再需要的数据、缓存或临时内容清理掉。
    """
    return delete(session, user, ids)


@router.post("/listAll",response_model=None, summary=f"{PLACEHOLDER_PREFIX}variable_list")
@require_permissions(permission=AppPermission(role=['admin']))
async def list_all_data(session: SessionDep, user: CurrentUser, trans: Trans, variable: SystemVariable = None):
    """
    是什么：list_all_data 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    return list_all(session, trans, user, variable)


@router.post("/listPage/{pageNum}/{pageSize}",response_model=None, summary=f"{PLACEHOLDER_PREFIX}variable_page")
@require_permissions(permission=AppPermission(role=['admin']))
async def pager(session: SessionDep, user: CurrentUser, trans: Trans, pageNum: int, pageSize: int,
                        variable: SystemVariable = None):
    """
    是什么：pager 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return await list_page(session, trans, user, pageNum, pageSize, variable)
