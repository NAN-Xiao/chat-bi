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
    _require_workspace_admin(current_user, current_tenant)
    return save_tracking_config(
        session,
        int(current_tenant.id),
        editor,
        current_user_id=int(current_user.id) if getattr(current_user, "id", None) is not None else None,
    )
