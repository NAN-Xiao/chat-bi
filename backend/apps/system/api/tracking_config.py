"""
脚本说明：这个脚本放系统管理的接口，把前端请求接进来并交给后面的业务逻辑处理。
"""
from fastapi import APIRouter

from apps.system.crud.tenant import TENANT_ADMIN_ROLES, normalize_tenant_role
from apps.system.crud.tracking_config import get_tracking_config, save_tracking_config
from apps.system.schemas.tenant_schema import TenantTrackingConfigDTO, TenantTrackingConfigEditor
from common.audit.models.log_model import OperationModules, OperationType
from common.audit.schemas.logger_decorator import LogConfig, system_log
from common.core.deps import CurrentTenant, CurrentUser, SessionDep
from fastapi import HTTPException

router = APIRouter(tags=["TenantTrackingConfig"], prefix="/system/tracking-config")


def _require_workspace_admin(current_user: CurrentUser, current_tenant: CurrentTenant) -> None:
    """
    是什么：_require_workspace_admin 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    role = normalize_tenant_role(
        getattr(current_user, "workspace_role", None)
        or getattr(current_user, "tenant_role", None)
        or getattr(current_tenant, "role", None)
    )
    if role in TENANT_ADMIN_ROLES:
        return
    raise HTTPException(status_code=403, detail="Only workspace admin can maintain tracking config")


@router.get("", response_model=TenantTrackingConfigDTO, include_in_schema=False)
async def current_tracking_config(
    session: SessionDep,
    current_tenant: CurrentTenant,
):
    """
    是什么：current_tracking_config 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return get_tracking_config(session, int(current_tenant.id))


@router.put("", response_model=TenantTrackingConfigDTO, include_in_schema=False)
@system_log(
    LogConfig(
        operation_type=OperationType.CREATE_OR_UPDATE,
        module=OperationModules.SETTING,
        resource_id_expr="current_tenant.id",
    )
)
async def update_current_tracking_config(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    editor: TenantTrackingConfigEditor,
):
    """
    是什么：update_current_tracking_config 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理相关的信息改成最新状态，并保存这些变化。
    """
    _require_workspace_admin(current_user, current_tenant)
    return save_tracking_config(
        session,
        int(current_tenant.id),
        editor,
        current_user_id=int(current_user.id) if getattr(current_user, "id", None) is not None else None,
    )
