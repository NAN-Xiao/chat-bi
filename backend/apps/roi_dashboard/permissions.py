"""ROI 专用看板的工作空间角色与数据源授权规则。"""

from fastapi import HTTPException
from sqlmodel import select

from apps.datasource.crud.binding import list_bound_datasource_ids_for_tenant
from apps.datasource.models.datasource import CoreDatasource, CoreDatasourceUser
from apps.system.crud.tenant import TENANT_ADMIN_ROLES
from apps.system.schemas.access_context import AccessContext, resolve_access_context
from common.core.deps import CurrentUser, SessionDep


def require_roi_workspace_admin(current_user: CurrentUser) -> AccessContext:
    """要求当前账号以拥有者或管理员角色进入真实工作空间。"""
    context = resolve_access_context(current_user)
    if (
        not context.has_workspace_context
        or context.is_platform_admin
        or context.tenant_role not in TENANT_ADMIN_ROLES
    ):
        raise HTTPException(status_code=403, detail="仅空间拥有者和管理员可访问 ROI 看板")
    return context


def list_account_datasource_ids_without_tenant_filter(
    session: SessionDep,
    user_id: int,
) -> set[int]:
    """读取账号的直接数据源授权，不附加当前工作空间过滤。"""
    rows = session.exec(
        select(CoreDatasourceUser.ds_id).where(CoreDatasourceUser.user_id == int(user_id))
    ).all()
    return {int(value) for value in rows if value is not None}


def list_roi_accessible_datasource_ids(
    session: SessionDep,
    current_user: CurrentUser,
) -> set[int]:
    """列出当前 ROI 管理员可配置的真实数据源。"""
    context = require_roi_workspace_admin(current_user)
    workspace_ids = set(
        list_bound_datasource_ids_for_tenant(session, context.management_tenant_id)
    )
    direct_ids = list_account_datasource_ids_without_tenant_filter(
        session,
        int(current_user.id),
    )
    candidate_ids = workspace_ids | direct_ids
    if not candidate_ids:
        return set()

    active_ids = session.exec(
        select(CoreDatasource.id).where(CoreDatasource.id.in_(candidate_ids))
    ).all()
    return {int(value) for value in active_ids if value is not None}


def has_roi_datasource_access(
    session: SessionDep,
    current_user: CurrentUser,
    datasource_id: int,
) -> bool:
    """使用 ROI 候选数据源集合判断指定数据源是否可访问。"""
    return int(datasource_id) in list_roi_accessible_datasource_ids(session, current_user)
