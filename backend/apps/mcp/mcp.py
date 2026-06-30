# 作者：Junjun
# 日期：2025/7/1
import json
from datetime import timedelta
from typing import Optional

import jwt
from fastapi import HTTPException, status, APIRouter
# from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from apps.chat.api.chat import create_chat, question_answer_inner
from apps.chat.models.chat_model import ChatMcp, CreateChat, ChatStart, McpQuestion, McpAssistant, ChatQuestion, \
    ChatFinishStep, McpDs
from apps.datasource.crud.datasource import get_datasource_list
from apps.system.crud.user import apply_user_role_flags, authenticate
from apps.system.crud.user import get_db_user
from apps.system.models.user import UserModel
from apps.system.schemas.system_schema import BaseUserDTO, AssistantHeader
from apps.system.schemas.system_schema import UserInfoDTO
from common.core import security
from common.core.config import settings
from common.core.deps import SessionDep, Trans
from common.core.schemas import TokenPayload, XOAuth2PasswordBearer, Token
from common.core.security import create_access_token

reusable_oauth2 = XOAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)

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


def get_user(session: SessionDep, token: str):
    """
    是什么：get_user 是 backend/apps/mcp/mcp.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询MCP 服务相关数据，整理后返回给调用方。
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    # session_user = await get_user_info(session=session, user_id=token_data.id)

    db_user: UserModel = get_db_user(session=session, user_id=token_data.id)
    session_user = UserInfoDTO.model_validate(db_user.model_dump())
    session_user = apply_user_role_flags(session_user)
    session_user.language = 'zh-CN'

    session_user = UserInfoDTO.model_validate(session_user)
    if not session_user:
        raise HTTPException(status_code=404, detail="User not found")

    if session_user.status != 1:
        raise HTTPException(status_code=400, detail="Inactive user")
    return session_user


@router.post("/mcp_start", operation_id="mcp_start")
async def mcp_start(session: SessionDep, chat: ChatStart):
    """
    是什么：mcp_start 是 backend/apps/mcp/mcp.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 mcp_start 的语义处理MCP 服务相关逻辑，并把结果返回或写入状态。
    """
    user: BaseUserDTO = authenticate(session=session, account=chat.username, password=chat.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect account or password")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    user_dict = user.to_dict()
    t = Token(access_token=create_access_token(
        user_dict, expires_delta=access_token_expires
    ))
    c = create_chat(session, user, CreateChat(origin=1), False)
    return {"access_token": t.access_token, "chat_id": c.id}


@router.post("/mcp_ds_list", operation_id="mcp_datasource_list")
async def datasource_list(session: SessionDep, trans: Trans, mcp_ds: McpDs):
    """
    是什么：datasource_list 是 backend/apps/mcp/mcp.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 datasource_list 的语义处理MCP 服务相关逻辑，并把结果返回或写入状态。
    """
    session_user = get_user(session, mcp_ds.token)
    ds_list = get_datasource_list(session=session, user=session_user)
    result = []
    for item in ds_list:
        dic = item.model_dump()
        dic.pop('embedding', None)
        dic.pop('table_relation', None)
        dic.pop('recommended_config', None)
        dic.pop('configuration', None)
        result.append(dic)
    return result


#
#
# @router.get("/model_list", operation_id="get_model_list")
# async def get_model_list(session: SessionDep):
#     return session.query(AiModelDetail).all()


@router.post("/mcp_question", operation_id="mcp_question")
async def mcp_question(session: SessionDep, trans: Trans, chat: McpQuestion):
    """
    是什么：mcp_question 是 backend/apps/mcp/mcp.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 mcp_question 的语义处理MCP 服务相关逻辑，并把结果返回或写入状态。
    """
    session_user = get_user(session, chat.token)
    lang = chat.lang
    if lang in ["zh-CN", "zh-TW", "en", "ko-KR"]:
        session_user.language = lang
    ds_id: Optional[int] = None
    if chat.datasource_id:
        if isinstance(chat.datasource_id, str):
            if chat.datasource_id.strip() == "":
                ds_id = None
            else:
                try:
                    ds_id = int(chat.datasource_id.strip())
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid datasource ID")
        elif isinstance(chat.datasource_id, int):
            ds_id = chat.datasource_id
        else:
            raise HTTPException(status_code=400, detail="Invalid datasource ID")

    mcp_chat = ChatMcp(token=chat.token, chat_id=chat.chat_id, question=chat.question, datasource_id=ds_id)

    return await question_answer_inner(session=session, current_user=session_user, request_question=mcp_chat,
                                       in_chat=False, stream=chat.stream, return_img=chat.return_img)


# 外部助手接口
@router.post("/mcp_assistant", operation_id="mcp_assistant")
async def mcp_assistant(session: SessionDep, chat: McpAssistant):
    """
    是什么：mcp_assistant 是 backend/apps/mcp/mcp.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 mcp_assistant 的语义处理MCP 服务相关逻辑，并把结果返回或写入状态。
    """
    session_user = BaseUserDTO(**{
        "id": -1, "account": 'shuzhi-mcp-assistant', "assistant_id": -1, "password": '', "language": "zh-CN",
        "name": "shuzhi-mcp-assistant", "email": "shuzhi-mcp-assistant@shuzhi.com"
    })
    # session_user: UserModel = get_db_user(session=session, user_id=1)
    c = create_chat(session, session_user, CreateChat(origin=1), False)

    # 构建助手参数
    configuration = {"endpoint": chat.url}
    # authorization = [{"key": "x-de-token",
    #                 "value": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1aWQiOjEsIm9pZCI6MSwiZXhwIjoxNzU4NTEyMDA2fQ.3NR-pgnADLdXZtI3dXX5-LuxfGYRvYD9kkr2de7KRP0",
    #                 "target": "header"}]
    mcp_assistant_header = AssistantHeader(id=1, name='mcp_assist', domain='', type=1,
                                           configuration=json.dumps(configuration),
                                           certificate=chat.authorization)

    # 助手问题
    mcp_chat = ChatQuestion(chat_id=c.id, question=chat.question)
    # 提问
    return await question_answer_inner(session=session, current_user=session_user, request_question=mcp_chat,
                                       current_assistant=mcp_assistant_header,
                                       in_chat=False, stream=chat.stream, finish_step=ChatFinishStep.QUERY_DATA)
