from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from apps.system.schemas.logout_schema import LogoutSchema
from apps.system.schemas.system_schema import BaseUserDTO
from common.core.deps import SessionDep, Trans
from common.core.login_rate_limiter import (
    clear_login_failures,
    get_login_limit_state,
    login_limit_identity,
    record_login_failure,
)
from common.utils.crypto import zhishu_decrypt
from ..crud.user import authenticate
from common.core.security import create_access_token
from datetime import timedelta
from common.core.config import settings
from common.core.schemas import Token

from common.audit.models.log_model import OperationType, OperationModules
from common.audit.schemas.logger_decorator import system_log, LogConfig

router = APIRouter(tags=["login"], prefix="/login")

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
    origin_account = await zhishu_decrypt(form_data.username)
    limit_identity = login_limit_identity(origin_account, request)
    limit_state = await get_login_limit_state(limit_identity)
    if limit_state.locked:
        raise HTTPException(
            status_code=429,
            detail="登录失败次数过多，请稍后再试",
            headers={"Retry-After": str(limit_state.retry_after_seconds)},
        )

    origin_pwd = await zhishu_decrypt(form_data.password)
    user: BaseUserDTO = authenticate(session=session, account=origin_account, password=origin_pwd)
    if not user:
        limit_state = await record_login_failure(limit_identity)
        if limit_state.locked:
            raise HTTPException(
                status_code=429,
                detail="登录失败次数过多，请稍后再试",
                headers={"Retry-After": str(limit_state.retry_after_seconds)},
            )
        raise HTTPException(status_code=400, detail=trans('i18n_login.account_pwd_error'))
    await clear_login_failures(limit_identity)
    if user.status != 1:
        raise HTTPException(status_code=400, detail=trans('i18n_login.user_disable', msg = trans('i18n_concat_admin')))
    if user.origin is not None and user.origin != 0:
        raise HTTPException(status_code=400, detail=trans('i18n_login.origin_error'))
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    user_dict = user.to_dict()
    return Token(access_token=create_access_token(
        user_dict, expires_delta=access_token_expires
    ))

@router.post("/logout")    
async def logout(session: SessionDep, request: Request, dto: LogoutSchema):
    return None
