# Author: Junjun
# Date: 2025/7/1

from datetime import timedelta

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from apps.chat.api.chat import create_chat
from apps.chat.models.chat_model import ChatMcp, CreateChat, ChatStart
from apps.chat.task.llm import LLMService, run_task
from apps.datasource.crud.datasource import get_datasource_list
from apps.system.crud.user import authenticate
from apps.system.models.system_model import AiModelDetail
from common.core.config import settings
from common.core.deps import SessionDep, get_current_user
from common.core.schemas import Token
from common.core.security import create_access_token

router = APIRouter(tags=["mcp"], prefix="/mcp")


# @router.post("/access_token", operation_id="access_token")
# def local_login(
#         session: SessionDep,
#         form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
# ) -> Token:
#     user = authenticate(session=session, account=form_data.username, password=form_data.password)
#     if not user:
#         raise HTTPException(status_code=400, detail="Incorrect account or password")
#     access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
#     user_dict = user.to_dict()
#     return Token(access_token=create_access_token(
#         user_dict, expires_delta=access_token_expires
#     ))


@router.get("/ds_list", operation_id="get_datasource_list")
async def datasource_list(session: SessionDep):
    return get_datasource_list(session=session)


@router.get("/model_list", operation_id="get_model_list")
async def get_model_list(session: SessionDep):
    return session.query(AiModelDetail).all()


@router.post("/mcp_start", operation_id="mcp_start")
async def mcp_start(session: SessionDep, chat: ChatStart):
    user = authenticate(session=session, account=chat.username, password=chat.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect account or password")
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    user_dict = user.to_dict()
    t = Token(access_token=create_access_token(
        user_dict, expires_delta=access_token_expires
    ))
    c = create_chat(session, user, CreateChat(), False)
    return {"access_token": t.access_token, "chat_id": c.id}


@router.post("/mcp_question", operation_id="mcp_question")
async def mcp_question(session: SessionDep, chat: ChatMcp):
    user = await get_current_user(session, chat.token)

    llm_service = LLMService(session, user, chat)
    llm_service.init_record()

    return StreamingResponse(run_task(llm_service, False), media_type="text/event-stream")
