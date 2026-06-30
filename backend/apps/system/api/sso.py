"""
脚本说明：这个脚本放系统管理的接口，把前端请求接进来并交给后面的业务逻辑处理。
"""
from fastapi import APIRouter, HTTPException, Query, Request

from apps.system.crud.feishu_sso import (
    FEISHU_ORIGIN,
    bind_or_create_feishu_user,
    build_feishu_authorize_url,
    fetch_feishu_identity,
    get_enabled_feishu_config,
    get_feishu_sso_config,
    parse_feishu_state,
    token_expires_delta,
    upsert_feishu_sso_config,
)
from apps.system.crud.tenant import attach_tenant_context, resolve_current_tenant
from apps.system.schemas.permission import AppPermission, require_permissions
from apps.system.schemas.sso import (
    FeishuCallbackRequest,
    FeishuLoginStatusDTO,
    FeishuSsoConfigDTO,
    FeishuSsoConfigEditor,
)
from common.core.deps import SessionDep
from common.core.schemas import Token
from common.core.security import create_access_token

login_router = APIRouter(tags=["login"], prefix="/login/feishu")
admin_router = APIRouter(tags=["system_authentication"], prefix="/system/auth/feishu", include_in_schema=False)


def _requested_tenant_id(request: Request, state_payload: dict | None = None) -> int | None:
    """
    是什么：_requested_tenant_id 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    state_tenant_id = (state_payload or {}).get("tenant_id")
    if state_tenant_id:
        return int(state_tenant_id)
    raw = request.headers.get("X-SHUZHI-TENANT-ID")
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid tenant id") from exc


@login_router.get("/status", response_model=FeishuLoginStatusDTO)
async def feishu_login_status(
    session: SessionDep,
    redirect: str | None = Query(default=None, max_length=1000),
    tenant_id: int | None = Query(default=None),
) -> FeishuLoginStatusDTO:
    """
    是什么：feishu_login_status 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    authorize_url = build_feishu_authorize_url(session, redirect=redirect, tenant_id=tenant_id)
    return FeishuLoginStatusDTO(enabled=bool(authorize_url), authorize_url=authorize_url)


@login_router.post("/callback", response_model=Token)
async def feishu_login_callback(
    session: SessionDep,
    request: Request,
    callback: FeishuCallbackRequest,
) -> Token:
    """
    是什么：feishu_login_callback 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    try:
        state_payload = parse_feishu_state(callback.state)
        config = get_enabled_feishu_config(session)
        identity = await fetch_feishu_identity(config, callback.code)
        user = bind_or_create_feishu_user(session, identity)
        if user.status != 1:
            raise PermissionError("User is disabled")
        tenant = resolve_current_tenant(
            session,
            user,
            requested_tenant_id=_requested_tenant_id(request, state_payload),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user = attach_tenant_context(user, tenant)
    request_state = getattr(request, "state", None)
    if request_state is not None:
        request_state.current_user = user
        request_state.current_tenant = tenant
    user_dict = user.to_dict()
    user_dict["auth_origin"] = FEISHU_ORIGIN
    return Token(
        access_token=create_access_token(user_dict, expires_delta=token_expires_delta()),
        platform_info={
            "provider": "feishu",
            "origin": FEISHU_ORIGIN,
            "redirect": state_payload.get("redirect"),
        },
    )


@admin_router.get("", response_model=FeishuSsoConfigDTO)
@require_permissions(permission=AppPermission(role=["platform_admin"]))
async def get_feishu_config(session: SessionDep) -> FeishuSsoConfigDTO:
    """
    是什么：get_feishu_config 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    return get_feishu_sso_config(session)


@admin_router.put("", response_model=FeishuSsoConfigDTO)
@require_permissions(permission=AppPermission(role=["platform_admin"]))
async def save_feishu_config(session: SessionDep, editor: FeishuSsoConfigEditor) -> FeishuSsoConfigDTO:
    """
    是什么：save_feishu_config 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：创建或保存系统管理需要的东西，让后续流程能继续往下走。
    """
    return upsert_feishu_sso_config(session, editor)
