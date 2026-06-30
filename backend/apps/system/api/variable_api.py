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
    是什么：save_variable 是 backend/apps/system/api/variable_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：创建、初始化或组装系统管理相关对象和数据，并返回或写入对应状态。
    """
    return save(session, user, trans, variable)


@router.post("/delete",response_model=None, summary=f"{PLACEHOLDER_PREFIX}variable_delete")
@require_permissions(permission=AppPermission(role=['admin']))
async def delete_variable(session: SessionDep, user: CurrentUser, ids: List[int]):
    """
    是什么：delete_variable 是 backend/apps/system/api/variable_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：删除或清理系统管理相关数据、缓存或临时状态。
    """
    return delete(session, user, ids)


@router.post("/listAll",response_model=None, summary=f"{PLACEHOLDER_PREFIX}variable_list")
@require_permissions(permission=AppPermission(role=['admin']))
async def list_all_data(session: SessionDep, user: CurrentUser, trans: Trans, variable: SystemVariable = None):
    """
    是什么：list_all_data 是 backend/apps/system/api/variable_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：读取或查询系统管理相关数据，整理后返回给调用方。
    """
    return list_all(session, trans, user, variable)


@router.post("/listPage/{pageNum}/{pageSize}",response_model=None, summary=f"{PLACEHOLDER_PREFIX}variable_page")
@require_permissions(permission=AppPermission(role=['admin']))
async def pager(session: SessionDep, user: CurrentUser, trans: Trans, pageNum: int, pageSize: int,
                        variable: SystemVariable = None):
    """
    是什么：pager 是 backend/apps/system/api/variable_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 pager 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    return await list_page(session, trans, user, pageNum, pageSize, variable)
