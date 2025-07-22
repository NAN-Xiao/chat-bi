from typing import Annotated

from fastapi import Depends, Request
from sqlmodel import Session
from apps.system.models.system_model import AssistantModel
from apps.system.schemas.system_schema import UserInfoDTO
from common.core.db import get_session
from common.utils.locale import I18n


SessionDep = Annotated[Session, Depends(get_session)]
i18n = I18n()
async def get_i18n(request: Request):
    return i18n(request)

Trans = Annotated[I18n, Depends(get_i18n)]
async def get_current_user(request: Request) -> UserInfoDTO:
    return request.state.current_user

CurrentUser = Annotated[UserInfoDTO, Depends(get_current_user)]

async def get_current_assistant(request: Request) -> AssistantModel | None:
    return request.state.assistant if hasattr(request.state, "assistant") else None

CurrentAssistant = Annotated[AssistantModel, Depends(get_current_assistant)]



