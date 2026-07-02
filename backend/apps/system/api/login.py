"""
脚本说明：这个脚本放系统管理的接口，把前端请求接进来并交给后面的业务逻辑处理。
"""
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import select

from apps.system.crud.tenant import (
    auto_assign_tenants_by_email_domain,
    attach_tenant_context,
    ensure_user_sample_workspace_membership,
    resolve_current_tenant,
)
from apps.system.schemas.logout_schema import LogoutSchema
from apps.system.schemas.auth import TrialApplicationCreate, TrialApplicationDTO
from apps.system.schemas.system_schema import BaseUserDTO
from common.audit.models.log_model import OperationModules, OperationType
from common.audit.schemas.logger_decorator import LogConfig, system_log
from common.core.config import settings
from common.core.deps import SessionDep, Trans
from common.core.schemas import Token
from common.core.security import create_access_token, hash_password
from common.utils.crypto import shuzhi_decrypt
from common.utils.time import get_timestamp

from ..crud.user import authenticate, check_email_format, check_pwd_format
from ..models.user import TrialApplicationModel, UserModel

router = APIRouter(tags=["login"], prefix="/login")


def _clean_trial_value(value: str | None) -> str:
    """
    是什么：_clean_trial_value 清理试用申请中的文本字段。
    """
    return (value or "").strip()


def _trial_application_dto(application: TrialApplicationModel) -> TrialApplicationDTO:
    """
    是什么：_trial_application_dto 把试用申请数据库对象转成接口返回结构。
    """
    return TrialApplicationDTO.model_validate(application.model_dump(exclude={"password_hash"}))


def _pending_trial_application_exists(session: SessionDep, account: str, email: str) -> bool:
    """
    是什么：_pending_trial_application_exists 检查账号或邮箱是否已有待审核申请。
    """
    statement = select(TrialApplicationModel.id).where(
        TrialApplicationModel.status == "pending",
        (TrialApplicationModel.account == account) | (TrialApplicationModel.email == email),
    )
    return session.exec(statement).first() is not None


@router.post("/trial-application", response_model=TrialApplicationDTO)
async def submit_trial_application(
    session: SessionDep,
    application: TrialApplicationCreate,
) -> TrialApplicationDTO:
    """
    是什么：submit_trial_application 接收未登录访客提交的试用账号申请。
    """
    account = _clean_trial_value(application.account)
    name = _clean_trial_value(application.name)
    email = _clean_trial_value(application.email)
    company = _clean_trial_value(application.company) or None
    reason = _clean_trial_value(application.reason) or None
    password = application.password or ""
    if not account or not name:
        raise HTTPException(status_code=400, detail="账号和姓名不能为空")
    if not check_email_format(email):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    if not check_pwd_format(password):
        raise HTTPException(status_code=400, detail="密码需为 8-20 位，包含大小写字母、数字和特殊字符")
    if session.exec(select(UserModel.id).where(UserModel.account == account)).first():
        raise HTTPException(status_code=400, detail="账号已存在，请直接登录或更换账号")
    if session.exec(select(UserModel.id).where(UserModel.name == name)).first():
        raise HTTPException(status_code=400, detail="姓名已存在，请更换姓名或联系管理员")
    if session.exec(select(UserModel.id).where(UserModel.email == email)).first():
        raise HTTPException(status_code=400, detail="邮箱已存在，请直接登录或更换邮箱")
    if _pending_trial_application_exists(session, account, email):
        raise HTTPException(status_code=400, detail="该账号或邮箱已有待审核申请，请等待管理员审核")
    now = get_timestamp()
    trial_application = TrialApplicationModel(
        account=account,
        name=name,
        email=email,
        password_hash=hash_password(password),
        company=company,
        reason=reason,
        status="pending",
        create_time=now,
        update_time=now,
    )
    session.add(trial_application)
    session.flush()
    return _trial_application_dto(trial_application)


def _requested_tenant_id(request: Request) -> int | None:
    """
    是什么：_requested_tenant_id 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
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
    是什么：local_login 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
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
    是什么：logout 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return None
