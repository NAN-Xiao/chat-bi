"""
脚本说明：这个脚本放后端基础能力相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
import base64
from typing import Annotated
from urllib.parse import unquote

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from apps.system.crud.tenant import TenantContext
from apps.system.schemas.system_schema import AssistantHeader, UserInfoDTO
from common.core.db import get_session
from common.utils.locale import I18n

SessionDep = Annotated[Session, Depends(get_session)]
i18n = I18n()
async def get_i18n(request: Request):
    """
    是什么：get_i18n 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力需要的数据找出来，整理成后面好用的样子。
    """
    return i18n(request)

Trans = Annotated[I18n, Depends(get_i18n)]
async def get_current_user(request: Request) -> UserInfoDTO:
    """
    是什么：get_current_user 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力需要的数据找出来，整理成后面好用的样子。
    """
    return request.state.current_user

CurrentUser = Annotated[UserInfoDTO, Depends(get_current_user)]

async def get_current_tenant(request: Request) -> TenantContext:
    """
    是什么：get_current_tenant 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力需要的数据找出来，整理成后面好用的样子。
    """
    current_tenant = getattr(request.state, "current_tenant", None)
    if current_tenant is None:
        raise HTTPException(
            status_code=403,
            detail="当前账号尚未加入工作空间，请先创建或加入工作空间后再访问工作空间侧业务功能。",
        )
    return current_tenant

CurrentTenant = Annotated[TenantContext, Depends(get_current_tenant)]

async def get_current_assistant(request: Request) -> AssistantHeader | None:
    """
    是什么：get_current_assistant 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力需要的数据找出来，整理成后面好用的样子。
    """
    base_assistant = request.state.assistant if hasattr(request.state, "assistant") else None
    if base_assistant is None:
        return None
    if request.headers.get("X-SHUZHI-ASSISTANT-CERTIFICATE"):
        entry_certificate = request.headers['X-SHUZHI-ASSISTANT-CERTIFICATE']
        base_assistant.certificate = unquote(base64.b64decode(entry_certificate).decode('utf-8'))
    return base_assistant

CurrentAssistant = Annotated[AssistantHeader, Depends(get_current_assistant)]



