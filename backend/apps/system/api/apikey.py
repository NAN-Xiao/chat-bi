"""
脚本说明：这个脚本放系统管理的接口，把前端请求接进来并交给后面的业务逻辑处理。
"""

from fastapi import APIRouter
from sqlmodel import func, select
from apps.system.crud.apikey_manage import clear_api_key_cache
from apps.system.models.system_model import ApiKeyModel
from apps.system.schemas.business_access import ensure_chatbi_business_user
from apps.system.schemas.system_schema import ApikeyGridItem, ApikeyStatus
from common.core.deps import CurrentUser, SessionDep
from common.utils.time import get_timestamp
import secrets

router = APIRouter(tags=["system_apikey"], prefix="/system/apikey", include_in_schema=False)
from common.audit.models.log_model import OperationType, OperationModules
from common.audit.schemas.logger_decorator import LogConfig, system_log


def _current_tenant_id(current_user: CurrentUser) -> int:
    """
    是什么：_current_tenant_id 是从当前用户里取租户 ID 的小工具。
    谁调用：需要知道当前用户属于哪个租户的接口会调用它。
    做了什么：把用户上下文里的租户 ID 取出来，方便后面做权限和数据隔离。
    """
    ensure_chatbi_business_user(current_user)
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise PermissionError("Current tenant is required")
    return int(tenant_id)


@router.get("")
async def grid(session: SessionDep, current_user: CurrentUser) -> list[ApikeyGridItem]:
    """
    是什么：grid 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    query = (
        select(ApiKeyModel)
        .where(
            ApiKeyModel.uid == current_user.id,
            ApiKeyModel.tenant_id == _current_tenant_id(current_user),
        )
        .order_by(ApiKeyModel.create_time.desc())
    )
    return session.exec(query).all()

@router.post("")
@system_log(LogConfig(operation_type=OperationType.CREATE, module=OperationModules.API_KEY,result_id_expr='result.self'))
async def create(session: SessionDep, current_user: CurrentUser):
    """
    是什么：create 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：创建或保存系统管理需要的东西，让后续流程能继续往下走。
    """
    tenant_id = _current_tenant_id(current_user)
    count = session.exec(
        select(func.count())
        .select_from(ApiKeyModel)
        .where(ApiKeyModel.uid == current_user.id, ApiKeyModel.tenant_id == tenant_id)
    ).one()
    if count >= 5:
        raise ValueError("Maximum of 5 API keys allowed")
    access_key = secrets.token_urlsafe(16)
    secret_key = secrets.token_urlsafe(32)
    api_key = ApiKeyModel(
        access_key=access_key,
        secret_key=secret_key,
        create_time=get_timestamp(),
        uid=current_user.id,
        tenant_id=tenant_id,
        status=True
    )
    session.add(api_key)
    session.commit()
    return api_key.id

@router.put("/status")
@system_log(LogConfig(operation_type=OperationType.UPDATE, module=OperationModules.API_KEY,resource_id_expr='id'))
async def status(session: SessionDep, current_user: CurrentUser, dto: ApikeyStatus):
    """
    是什么：status 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    api_key = session.get(ApiKeyModel, dto.id)
    if not api_key:
        raise ValueError("API Key not found")
    if api_key.uid != current_user.id or api_key.tenant_id != _current_tenant_id(current_user):
        raise PermissionError("No permission to modify this API Key")
    if dto.status == api_key.status:
        return
    api_key.status = dto.status
    await clear_api_key_cache(api_key.access_key)
    session.add(api_key)
    session.commit()

@router.delete("/{id}")
@system_log(LogConfig(operation_type=OperationType.DELETE, module=OperationModules.API_KEY,resource_id_expr='id'))
async def delete(session: SessionDep, current_user: CurrentUser, id: int):
    """
    是什么：delete 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理不再需要的数据、缓存或临时内容清理掉。
    """
    api_key = session.get(ApiKeyModel, id)
    if not api_key:
        raise ValueError("API Key not found")
    if api_key.uid != current_user.id or api_key.tenant_id != _current_tenant_id(current_user):
        raise PermissionError("No permission to delete this API Key")
    await clear_api_key_cache(api_key.access_key)
    session.delete(api_key)
    session.commit()
