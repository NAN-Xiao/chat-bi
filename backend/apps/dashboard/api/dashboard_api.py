from typing import List

import asyncio

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException

from apps.dashboard.crud.dashboard_service import list_resource, load_resource, \
    create_resource, create_canvas, validate_name, delete_resource, update_resource, update_canvas, preview_sql, \
    share_resource, list_shared_resources, load_shared_resource, delete_shared_resource, use_shared_resource, \
    list_default_resources, load_default_resource, copy_default_resource, set_default_resource, sort_default_resources, \
    move_resource, reorder_resources, \
    copy_dashboard_to_platform_template, list_platform_dashboard_templates, load_platform_dashboard_template, \
    update_platform_dashboard_template, delete_platform_dashboard_template, copy_platform_template_to_workspace_dashboard
from apps.dashboard.models.dashboard_model import (
    CreateDashboard,
    BaseDashboard,
    QueryDashboard,
    DashboardDefaultCopyRequest,
    DashboardDefaultRequest,
    DashboardDefaultSortRequest,
    DashboardReorderRequest,
    DashboardPlatformTemplateCopyRequest,
    DashboardPlatformTemplateUseRequest,
    DashboardSqlPreview,
    DashboardShareRequest,
    DashboardShareListQuery,
    SharedDashboardQuery,
    SharedDashboardUseRequest,
)
from apps.swagger.i18n import PLACEHOLDER_PREFIX
from apps.system.schemas.business_access import require_chatbi_business_user
from apps.system.schemas.permission import AppPermission, require_permissions
from common.audit.models.log_model import OperationType, OperationModules
from common.audit.schemas.logger_decorator import LogConfig, system_log
from common.core.deps import SessionDep, CurrentUser

router = APIRouter(
    tags=["Dashboard"],
    prefix="/dashboard",
    dependencies=[Depends(require_chatbi_business_user)],
)

platform_router = APIRouter(
    tags=["Dashboard"],
    prefix="/dashboard/platform-template",
)


@router.post("/list_resource", summary=f"{PLACEHOLDER_PREFIX}list_resource_api")
async def list_resource_api(session: SessionDep, dashboard: QueryDashboard, current_user: CurrentUser):
    """
    是什么：list_resource_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：读取或查询仪表盘相关数据，整理后返回给调用方。
    """
    return list_resource(session=session, dashboard=dashboard, current_user=current_user)


@router.post("/load_resource", summary=f"{PLACEHOLDER_PREFIX}load_resource_api")
def load_resource_api(session: SessionDep, current_user: CurrentUser, dashboard: QueryDashboard):
    """
    是什么：load_resource_api 是 backend/apps/dashboard/api/dashboard_api.py 中的同步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：读取或查询仪表盘相关数据，整理后返回给调用方。
    """
    return load_resource(session=session, dashboard=dashboard, current_user=current_user)


@router.get("/default/list", summary=f"{PLACEHOLDER_PREFIX}dashboard_default_list")
async def list_default_resource_api(session: SessionDep, current_user: CurrentUser):
    """
    是什么：list_default_resource_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：读取或查询仪表盘相关数据，整理后返回给调用方。
    """
    return list_default_resources(session=session, current_user=current_user)


@router.post("/default/load", summary=f"{PLACEHOLDER_PREFIX}dashboard_default")
def load_default_resource_api(session: SessionDep, current_user: CurrentUser, dashboard: QueryDashboard):
    """
    是什么：load_default_resource_api 是 backend/apps/dashboard/api/dashboard_api.py 中的同步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：读取或查询仪表盘相关数据，整理后返回给调用方。
    """
    return load_default_resource(session=session, dashboard=dashboard, current_user=current_user)


@router.post("/default/copy", response_model=BaseDashboard, summary=f"{PLACEHOLDER_PREFIX}dashboard_default_copy")
@system_log(LogConfig(
    operation_type=OperationType.CREATE,
    module=OperationModules.DASHBOARD,
    result_id_expr="id"
))
async def copy_default_resource_api(session: SessionDep, user: CurrentUser, request: DashboardDefaultCopyRequest):
    """
    是什么：copy_default_resource_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 copy_default_resource_api 的语义处理仪表盘相关逻辑，并把结果返回或写入状态。
    """
    return copy_default_resource(session=session, user=user, request=request)


@router.post("/default/set", summary=f"{PLACEHOLDER_PREFIX}dashboard_default_set")
@system_log(LogConfig(
    operation_type=OperationType.UPDATE,
    module=OperationModules.DASHBOARD,
    resource_id_expr="request.dashboard_id"
))
async def set_default_resource_api(session: SessionDep, user: CurrentUser, request: DashboardDefaultRequest):
    """
    是什么：set_default_resource_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：更新仪表盘相关状态、配置或持久化数据，并保持后续流程可继续使用。
    """
    return set_default_resource(session=session, user=user, request=request)


@router.post("/default/sort", summary=f"{PLACEHOLDER_PREFIX}dashboard_default_sort")
@system_log(LogConfig(
    operation_type=OperationType.UPDATE,
    module=OperationModules.DASHBOARD,
))
async def sort_default_resource_api(session: SessionDep, user: CurrentUser, request: DashboardDefaultSortRequest):
    """
    是什么：sort_default_resource_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 sort_default_resource_api 的语义处理仪表盘相关逻辑，并把结果返回或写入状态。
    """
    return sort_default_resources(session=session, user=user, request=request)


@router.post("/reorder", summary=f"{PLACEHOLDER_PREFIX}dashboard_reorder")
@system_log(LogConfig(
    operation_type=OperationType.UPDATE,
    module=OperationModules.DASHBOARD,
))
async def reorder_resource_api(session: SessionDep, user: CurrentUser, request: DashboardReorderRequest):
    """
    是什么：reorder_resource_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 reorder_resource_api 的语义处理仪表盘相关逻辑，并把结果返回或写入状态。
    """
    return reorder_resources(session=session, user=user, request=request)


@router.get("/platform-delegate/template/list", summary=f"{PLACEHOLDER_PREFIX}platform_dashboard_template_list")
async def list_platform_dashboard_template_api(session: SessionDep, user: CurrentUser):
    """
    是什么：list_platform_dashboard_template_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：读取或查询仪表盘相关数据，整理后返回给调用方。
    """
    return list_platform_dashboard_templates(session=session, user=user)


@platform_router.get("/list", summary=f"{PLACEHOLDER_PREFIX}platform_dashboard_template_list")
async def list_platform_dashboard_template_admin_api(session: SessionDep, user: CurrentUser):
    """
    是什么：list_platform_dashboard_template_admin_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：读取或查询仪表盘相关数据，整理后返回给调用方。
    """
    return list_platform_dashboard_templates(session=session, user=user)


@platform_router.post("/load", summary=f"{PLACEHOLDER_PREFIX}platform_dashboard_template_load")
async def load_platform_dashboard_template_admin_api(session: SessionDep, user: CurrentUser, dashboard: QueryDashboard):
    """
    是什么：load_platform_dashboard_template_admin_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：读取或查询仪表盘相关数据，整理后返回给调用方。
    """
    return load_platform_dashboard_template(
        session=session,
        user=user,
        template_id=dashboard.id,
        include_data=dashboard.include_data,
    )


@platform_router.post("/update", summary=f"{PLACEHOLDER_PREFIX}platform_dashboard_template_update")
@system_log(LogConfig(
    operation_type=OperationType.UPDATE,
    module=OperationModules.DASHBOARD,
    resource_id_expr="dashboard.id"
))
async def update_platform_dashboard_template_admin_api(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    """
    是什么：update_platform_dashboard_template_admin_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：更新仪表盘相关状态、配置或持久化数据，并保持后续流程可继续使用。
    """
    return update_platform_dashboard_template(session=session, user=user, dashboard=dashboard)


@platform_router.post("/delete", summary=f"{PLACEHOLDER_PREFIX}platform_dashboard_template_delete")
@system_log(LogConfig(
    operation_type=OperationType.DELETE,
    module=OperationModules.DASHBOARD,
    resource_id_expr="dashboard.id",
    remark_expr="dashboard.name"
))
async def delete_platform_dashboard_template_admin_api(session: SessionDep, user: CurrentUser, dashboard: QueryDashboard):
    """
    是什么：delete_platform_dashboard_template_admin_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：删除或清理仪表盘相关数据、缓存或临时状态。
    """
    return delete_platform_dashboard_template(session=session, user=user, template_id=dashboard.id)


@router.post("/platform-delegate/template/copy-from-dashboard", summary=f"{PLACEHOLDER_PREFIX}platform_dashboard_template_copy")
@system_log(LogConfig(
    operation_type=OperationType.CREATE,
    module=OperationModules.DASHBOARD,
    result_id_expr="id"
))
async def copy_dashboard_to_platform_template_api(
        session: SessionDep,
        user: CurrentUser,
        request: DashboardPlatformTemplateCopyRequest,
):
    """
    是什么：copy_dashboard_to_platform_template_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 copy_dashboard_to_platform_template_api 的语义处理仪表盘相关逻辑，并把结果返回或写入状态。
    """
    return copy_dashboard_to_platform_template(
        session=session,
        user=user,
        dashboard_id=request.dashboard_id,
        name=request.name,
    )


@router.post("/platform-delegate/template/copy-to-workspace", summary=f"{PLACEHOLDER_PREFIX}platform_dashboard_template_use")
@system_log(LogConfig(
    operation_type=OperationType.CREATE,
    module=OperationModules.DASHBOARD,
    result_id_expr="id"
))
async def copy_platform_template_to_workspace_dashboard_api(
        session: SessionDep,
        user: CurrentUser,
        request: DashboardPlatformTemplateUseRequest,
):
    """
    是什么：copy_platform_template_to_workspace_dashboard_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 copy_platform_template_to_workspace_dashboard_api 的语义处理仪表盘相关逻辑，并把结果返回或写入状态。
    """
    return copy_platform_template_to_workspace_dashboard(
        session=session,
        user=user,
        template_id=request.template_id,
        template_ids=request.template_ids,
        name=request.name,
    )


@router.post("/create_resource", response_model=BaseDashboard, summary=f"{PLACEHOLDER_PREFIX}create_resource_api")
async def create_resource_api(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    """
    是什么：create_resource_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：创建、初始化或组装仪表盘相关对象和数据，并返回或写入对应状态。
    """
    return create_resource(session, user, dashboard)


@router.post("/update_resource", response_model=BaseDashboard, summary=f"{PLACEHOLDER_PREFIX}update_resource")
@system_log(LogConfig(
    operation_type=OperationType.UPDATE,
    module=OperationModules.DASHBOARD,
    resource_id_expr="dashboard.id"
))
async def update_resource_api(session: SessionDep, user: CurrentUser, dashboard: QueryDashboard):
    """
    是什么：update_resource_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：更新仪表盘相关状态、配置或持久化数据，并保持后续流程可继续使用。
    """
    return update_resource(session=session, user=user, dashboard=dashboard)


@router.delete("/move_resource/{resource_id}", response_model=BaseDashboard, summary=f"{PLACEHOLDER_PREFIX}move_resource")
@system_log(LogConfig(
    operation_type=OperationType.UPDATE,
    module=OperationModules.DASHBOARD,
    resource_id_expr="resource_id"
))
async def move_resource_api(session: SessionDep, user: CurrentUser, resource_id: str, dashboard: QueryDashboard):
    """
    是什么：move_resource_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 move_resource_api 的语义处理仪表盘相关逻辑，并把结果返回或写入状态。
    """
    dashboard.id = resource_id
    return move_resource(session=session, user=user, dashboard=dashboard)


@router.delete("/delete_resource/{resource_id}/{name}", summary=f"{PLACEHOLDER_PREFIX}delete_resource_api")
@system_log(LogConfig(
    operation_type=OperationType.DELETE,
    module=OperationModules.DASHBOARD,
    resource_id_expr="resource_id",
    remark_expr="name"
))
async def delete_resource_api(session: SessionDep, current_user: CurrentUser, resource_id: str, name: str):
    """
    是什么：delete_resource_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：删除或清理仪表盘相关数据、缓存或临时状态。
    """
    return delete_resource(session, current_user, resource_id)


@router.post("/create_canvas", response_model=BaseDashboard, summary=f"{PLACEHOLDER_PREFIX}create_canvas_api")
@system_log(LogConfig(
    operation_type=OperationType.CREATE,
    module=OperationModules.DASHBOARD,
    result_id_expr="id"
))
async def create_canvas_api(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    """
    是什么：create_canvas_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：创建、初始化或组装仪表盘相关对象和数据，并返回或写入对应状态。
    """
    return create_canvas(session, user, dashboard)


@router.post("/update_canvas", response_model=BaseDashboard, summary=f"{PLACEHOLDER_PREFIX}update_canvas_api")
@system_log(LogConfig(
    operation_type=OperationType.UPDATE,
    module=OperationModules.DASHBOARD,
    resource_id_expr="dashboard.id"
))
async def update_canvas_api(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    """
    是什么：update_canvas_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：更新仪表盘相关状态、配置或持久化数据，并保持后续流程可继续使用。
    """
    return update_canvas(session, user, dashboard)


@router.post("/check_name", summary=f"{PLACEHOLDER_PREFIX}check_name_api")
async def check_name_api(session: SessionDep, user: CurrentUser, dashboard: QueryDashboard):
    """
    是什么：check_name_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：校验仪表盘相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    return validate_name(session, user, dashboard)


@router.post("/sql_preview", summary=f"{PLACEHOLDER_PREFIX}dashboard_sql_preview")
@require_permissions(permission=AppPermission(type='ds', keyExpression="request.datasource"))
async def sql_preview_api(session: SessionDep, current_user: CurrentUser, request: DashboardSqlPreview):
    """
    是什么：sql_preview_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 sql_preview_api 的语义处理仪表盘相关逻辑，并把结果返回或写入状态。
    """
    return await asyncio.to_thread(
        preview_sql,
        session=session,
        current_user=current_user,
        request=request,
    )


@router.post("/share", summary=f"{PLACEHOLDER_PREFIX}dashboard_share")
@system_log(LogConfig(
    operation_type=OperationType.CREATE,
    module=OperationModules.DASHBOARD,
    result_id_expr="id"
))
async def share_resource_api(session: SessionDep, user: CurrentUser, request: DashboardShareRequest):
    """
    是什么：share_resource_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 share_resource_api 的语义处理仪表盘相关逻辑，并把结果返回或写入状态。
    """
    return share_resource(session=session, user=user, request=request)


@router.post("/share/list", summary=f"{PLACEHOLDER_PREFIX}dashboard_share_list")
async def list_shared_resource_api(
        session: SessionDep,
        current_user: CurrentUser,
        query: DashboardShareListQuery,
):
    """
    是什么：list_shared_resource_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：读取或查询仪表盘相关数据，整理后返回给调用方。
    """
    return list_shared_resources(session=session, current_user=current_user, query=query)


@router.post("/share/load", summary=f"{PLACEHOLDER_PREFIX}dashboard_share_load")
async def load_shared_resource_api(
        session: SessionDep,
        current_user: CurrentUser,
        query: SharedDashboardQuery,
):
    """
    是什么：load_shared_resource_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：读取或查询仪表盘相关数据，整理后返回给调用方。
    """
    return load_shared_resource(session=session, current_user=current_user, query=query)


@router.post("/share/delete", summary=f"{PLACEHOLDER_PREFIX}dashboard_share_delete")
@system_log(LogConfig(
    operation_type=OperationType.DELETE,
    module=OperationModules.DASHBOARD,
    resource_id_expr="query.id"
))
async def delete_shared_resource_api(
        session: SessionDep,
        current_user: CurrentUser,
        query: SharedDashboardQuery,
):
    """
    是什么：delete_shared_resource_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：删除或清理仪表盘相关数据、缓存或临时状态。
    """
    return delete_shared_resource(session=session, current_user=current_user, query=query)


@router.post("/share/use", summary=f"{PLACEHOLDER_PREFIX}dashboard_share_use")
@system_log(LogConfig(
    operation_type=OperationType.CREATE,
    module=OperationModules.DASHBOARD,
    result_id_expr="id"
))
async def use_shared_resource_api(
        session: SessionDep,
        user: CurrentUser,
        request: SharedDashboardUseRequest,
):
    """
    是什么：use_shared_resource_api 是 backend/apps/dashboard/api/dashboard_api.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 use_shared_resource_api 的语义处理仪表盘相关逻辑，并把结果返回或写入状态。
    """
    return use_shared_resource(session=session, user=user, request=request)
