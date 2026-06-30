from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm

from apps.system.crud.tenant import (
    auto_assign_tenants_by_email_domain,
    attach_tenant_context,
    ensure_user_sample_workspace_membership,
    resolve_current_tenant,
)
from apps.system.schemas.logout_schema import LogoutSchema
from apps.system.schemas.system_schema import BaseUserDTO
from common.audit.models.log_model import OperationModules, OperationType
from common.audit.schemas.logger_decorator import LogConfig, system_log
from common.core.config import settings
from common.core.deps import SessionDep, Trans
from common.core.schemas import Token
from common.core.security import create_access_token
from common.utils.crypto import shuzhi_decrypt

from ..crud.user import authenticate

router = APIRouter(tags=["login"], prefix="/login")


def _requested_tenant_id(request: Request) -> int | None:
    """
    是什么：_requested_tenant_id 是 backend/apps/system/api/login.py 中的同步函数。
    谁调用：由 FastAPI 路由处理函数或同模块业务辅助流程调用。
    做了什么：围绕 _requested_tenant_id 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    raw = request.headers.get("X-SHUZHI-TENANT-ID")
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid tenant id") from exc

@router.post("/access-token")
@system_log(LogConfig(
    operation_type=OperationType.LOGIN,
    module=OperationModules.USER,
    result_id_expr="id"
))
async def local_login(
    session: SessionDep,
    trans: Trans,
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> Token:
    """
    是什么：local_login 是 backend/apps/system/api/login.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 local_login 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    origin_account = await shuzhi_decrypt(form_data.username)
    origin_pwd = await shuzhi_decrypt(form_data.password)
    user: BaseUserDTO = authenticate(session=session, account=origin_account, password=origin_pwd)
    if not user:
        raise HTTPException(status_code=400, detail=trans('i18n_login.account_pwd_error'))
    if user.status != 1:
        raise HTTPException(status_code=400, detail=trans('i18n_login.user_disable', msg = trans('i18n_concat_admin')))
    if user.origin is not None and user.origin != 0:
        raise HTTPException(status_code=400, detail=trans('i18n_login.origin_error'))
    try:
        auto_assign_tenants_by_email_domain(session, user)
        ensure_user_sample_workspace_membership(session, user)
        tenant = resolve_current_tenant(session, user, requested_tenant_id=_requested_tenant_id(request))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    user = attach_tenant_context(user, tenant)
    request.state.current_user = user
    request.state.current_tenant = tenant
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    user_dict = user.to_dict()
    return Token(access_token=create_access_token(
        user_dict, expires_delta=access_token_expires
    ))

@router.post("/logout")
async def logout(_session: SessionDep, _request: Request, _dto: LogoutSchema):
    """
    是什么：logout 是 backend/apps/system/api/login.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 logout 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    return None
