from typing import List

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException

from apps.dashboard.crud.dashboard_service import list_resource, load_resource, \
    create_resource, create_canvas, validate_name, delete_resource, update_resource, update_canvas, preview_sql, \
    share_resource, list_shared_resources, load_shared_resource, delete_shared_resource, use_shared_resource, \
    list_default_resources, load_default_resource, copy_default_resource, set_default_resource, sort_default_resources, \
    move_resource, \
    list_platform_delegate_drafts, load_platform_delegate_draft, update_platform_delegate_draft, \
    create_platform_delegate_maintenance_draft, publish_platform_delegate_draft, delete_platform_delegate_draft, \
    copy_dashboard_to_platform_template, list_platform_dashboard_templates, copy_platform_template_to_delegate_draft
from apps.dashboard.models.dashboard_model import (
    CreateDashboard,
    BaseDashboard,
    QueryDashboard,
    DashboardDefaultCopyRequest,
    DashboardDefaultRequest,
    DashboardDefaultSortRequest,
    DashboardPlatformDelegateDraftRequest,
    DashboardPlatformDelegatePublishRequest,
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


@router.post("/list_resource", summary=f"{PLACEHOLDER_PREFIX}list_resource_api")
async def list_resource_api(session: SessionDep, dashboard: QueryDashboard, current_user: CurrentUser):
    return list_resource(session=session, dashboard=dashboard, current_user=current_user)


@router.post("/load_resource", summary=f"{PLACEHOLDER_PREFIX}load_resource_api")
async def load_resource_api(session: SessionDep, current_user: CurrentUser, dashboard: QueryDashboard):
    return load_resource(session=session, dashboard=dashboard, current_user=current_user)


@router.get("/default/list", summary=f"{PLACEHOLDER_PREFIX}dashboard_default_list")
async def list_default_resource_api(session: SessionDep, current_user: CurrentUser):
    return list_default_resources(session=session, current_user=current_user)


@router.post("/default/load", summary=f"{PLACEHOLDER_PREFIX}dashboard_default")
async def load_default_resource_api(session: SessionDep, current_user: CurrentUser, dashboard: QueryDashboard):
    return load_default_resource(session=session, dashboard=dashboard, current_user=current_user)


@router.post("/default/copy", response_model=BaseDashboard, summary=f"{PLACEHOLDER_PREFIX}dashboard_default_copy")
@system_log(LogConfig(
    operation_type=OperationType.CREATE,
    module=OperationModules.DASHBOARD,
    result_id_expr="id"
))
async def copy_default_resource_api(session: SessionDep, user: CurrentUser, request: DashboardDefaultCopyRequest):
    return copy_default_resource(session=session, user=user, request=request)


@router.post("/default/set", summary=f"{PLACEHOLDER_PREFIX}dashboard_default_set")
@system_log(LogConfig(
    operation_type=OperationType.UPDATE,
    module=OperationModules.DASHBOARD,
    resource_id_expr="request.dashboard_id"
))
async def set_default_resource_api(session: SessionDep, user: CurrentUser, request: DashboardDefaultRequest):
    return set_default_resource(session=session, user=user, request=request)


@router.post("/default/sort", summary=f"{PLACEHOLDER_PREFIX}dashboard_default_sort")
@system_log(LogConfig(
    operation_type=OperationType.UPDATE,
    module=OperationModules.DASHBOARD,
))
async def sort_default_resource_api(session: SessionDep, user: CurrentUser, request: DashboardDefaultSortRequest):
    return sort_default_resources(session=session, user=user, request=request)


@router.get("/platform-delegate/draft/list", summary=f"{PLACEHOLDER_PREFIX}platform_delegate_draft_list")
async def list_platform_delegate_draft_api(session: SessionDep, current_user: CurrentUser):
    return list_platform_delegate_drafts(session=session, current_user=current_user)


@router.post("/platform-delegate/draft/load", summary=f"{PLACEHOLDER_PREFIX}platform_delegate_draft_load")
async def load_platform_delegate_draft_api(session: SessionDep, current_user: CurrentUser, dashboard: QueryDashboard):
    return load_platform_delegate_draft(session=session, dashboard=dashboard, current_user=current_user)


@router.post("/platform-delegate/draft/update", response_model=BaseDashboard, summary=f"{PLACEHOLDER_PREFIX}platform_delegate_draft_update")
@system_log(LogConfig(
    operation_type=OperationType.UPDATE,
    module=OperationModules.DASHBOARD,
    resource_id_expr="dashboard.id"
))
async def update_platform_delegate_draft_api(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    return update_platform_delegate_draft(session=session, user=user, dashboard=dashboard)


@router.post("/platform-delegate/draft/maintain", summary=f"{PLACEHOLDER_PREFIX}platform_delegate_draft_maintain")
@system_log(LogConfig(
    operation_type=OperationType.CREATE,
    module=OperationModules.DASHBOARD,
    result_id_expr="id"
))
async def create_platform_delegate_maintenance_draft_api(
        session: SessionDep,
        user: CurrentUser,
        request: DashboardPlatformDelegateDraftRequest,
):
    return create_platform_delegate_maintenance_draft(
        session=session,
        user=user,
        dashboard_id=request.dashboard_id,
    )


@router.post("/platform-delegate/draft/publish", summary=f"{PLACEHOLDER_PREFIX}platform_delegate_draft_publish")
@system_log(LogConfig(
    operation_type=OperationType.UPDATE,
    module=OperationModules.DASHBOARD,
    resource_id_expr="request.draft_dashboard_id"
))
async def publish_platform_delegate_draft_api(
        session: SessionDep,
        user: CurrentUser,
        request: DashboardPlatformDelegatePublishRequest,
):
    return publish_platform_delegate_draft(
        session=session,
        user=user,
        draft_dashboard_id=request.draft_dashboard_id,
        publish_as_default=request.publish_as_default,
    )


@router.post("/platform-delegate/draft/delete", summary=f"{PLACEHOLDER_PREFIX}platform_delegate_draft_delete")
@system_log(LogConfig(
    operation_type=OperationType.DELETE,
    module=OperationModules.DASHBOARD,
    resource_id_expr="request.dashboard_id"
))
async def delete_platform_delegate_draft_api(
        session: SessionDep,
        user: CurrentUser,
        request: DashboardPlatformDelegateDraftRequest,
):
    return delete_platform_delegate_draft(
        session=session,
        user=user,
        draft_dashboard_id=request.dashboard_id,
    )


@router.get("/platform-delegate/template/list", summary=f"{PLACEHOLDER_PREFIX}platform_dashboard_template_list")
async def list_platform_dashboard_template_api(session: SessionDep, user: CurrentUser):
    return list_platform_dashboard_templates(session=session, user=user)


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
    return copy_dashboard_to_platform_template(
        session=session,
        user=user,
        dashboard_id=request.dashboard_id,
        name=request.name,
    )


@router.post("/platform-delegate/template/copy-to-draft", summary=f"{PLACEHOLDER_PREFIX}platform_dashboard_template_use")
@system_log(LogConfig(
    operation_type=OperationType.CREATE,
    module=OperationModules.DASHBOARD,
    result_id_expr="id"
))
async def copy_platform_template_to_delegate_draft_api(
        session: SessionDep,
        user: CurrentUser,
        request: DashboardPlatformTemplateUseRequest,
):
    return copy_platform_template_to_delegate_draft(
        session=session,
        user=user,
        template_id=request.template_id,
        name=request.name,
    )


@router.post("/create_resource", response_model=BaseDashboard, summary=f"{PLACEHOLDER_PREFIX}create_resource_api")
async def create_resource_api(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    return create_resource(session, user, dashboard)


@router.post("/update_resource", response_model=BaseDashboard, summary=f"{PLACEHOLDER_PREFIX}update_resource")
@system_log(LogConfig(
    operation_type=OperationType.UPDATE,
    module=OperationModules.DASHBOARD,
    resource_id_expr="dashboard.id"
))
async def update_resource_api(session: SessionDep, user: CurrentUser, dashboard: QueryDashboard):
    return update_resource(session=session, user=user, dashboard=dashboard)


@router.delete("/move_resource/{resource_id}", response_model=BaseDashboard, summary=f"{PLACEHOLDER_PREFIX}move_resource")
@system_log(LogConfig(
    operation_type=OperationType.UPDATE,
    module=OperationModules.DASHBOARD,
    resource_id_expr="resource_id"
))
async def move_resource_api(session: SessionDep, user: CurrentUser, resource_id: str, dashboard: QueryDashboard):
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
    return delete_resource(session, current_user, resource_id)


@router.post("/create_canvas", response_model=BaseDashboard, summary=f"{PLACEHOLDER_PREFIX}create_canvas_api")
@system_log(LogConfig(
    operation_type=OperationType.CREATE,
    module=OperationModules.DASHBOARD,
    result_id_expr="id"
))
async def create_canvas_api(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    return create_canvas(session, user, dashboard)


@router.post("/update_canvas", response_model=BaseDashboard, summary=f"{PLACEHOLDER_PREFIX}update_canvas_api")
@system_log(LogConfig(
    operation_type=OperationType.UPDATE,
    module=OperationModules.DASHBOARD,
    resource_id_expr="dashboard.id"
))
async def update_canvas_api(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    return update_canvas(session, user, dashboard)


@router.post("/check_name", summary=f"{PLACEHOLDER_PREFIX}check_name_api")
async def check_name_api(session: SessionDep, user: CurrentUser, dashboard: QueryDashboard):
    return validate_name(session, user, dashboard)


@router.post("/sql_preview", summary=f"{PLACEHOLDER_PREFIX}dashboard_sql_preview")
@require_permissions(permission=AppPermission(type='ds', keyExpression="request.datasource"))
async def sql_preview_api(session: SessionDep, current_user: CurrentUser, request: DashboardSqlPreview):
    return preview_sql(session=session, current_user=current_user, request=request)


@router.post("/share", summary=f"{PLACEHOLDER_PREFIX}dashboard_share")
@system_log(LogConfig(
    operation_type=OperationType.CREATE,
    module=OperationModules.DASHBOARD,
    result_id_expr="id"
))
async def share_resource_api(session: SessionDep, user: CurrentUser, request: DashboardShareRequest):
    return share_resource(session=session, user=user, request=request)


@router.post("/share/list", summary=f"{PLACEHOLDER_PREFIX}dashboard_share_list")
async def list_shared_resource_api(
        session: SessionDep,
        current_user: CurrentUser,
        query: DashboardShareListQuery,
):
    return list_shared_resources(session=session, current_user=current_user, query=query)


@router.post("/share/load", summary=f"{PLACEHOLDER_PREFIX}dashboard_share_load")
async def load_shared_resource_api(
        session: SessionDep,
        current_user: CurrentUser,
        query: SharedDashboardQuery,
):
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
    return use_shared_resource(session=session, user=user, request=request)
