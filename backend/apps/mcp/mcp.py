# Author: Junjun
# Date: 2025/7/1

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from apps.chat.api.chat import create_chat
from apps.chat.models.chat_model import ChatMcp, CreateChat
from apps.chat.task.llm import LLMService, run_task
from apps.datasource.crud.datasource import get_datasource_list
from apps.system.crud.user import authenticate
from apps.system.models.system_model import AiModelDetail
from common.core.config import settings
from common.core.deps import SessionDep, get_current_user
from common.core.schemas import Token
from common.core.security import create_access_token

router = APIRouter(tags=["mcp"], prefix="/mcp")


@router.post("/access_token", operation_id="access_token")
def local_login(
        session: SessionDep,
        form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> Token:
    user = authenticate(session=session, account=form_data.username, password=form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect account or password")
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    user_dict = user.to_dict()
    return Token(access_token=create_access_token(
        user_dict, expires_delta=access_token_expires
    ))


@router.get("/ds_list", operation_id="get_datasource_list")
async def datasource_list(session: SessionDep):
    return get_datasource_list(session=session)


@router.get("/model_list", operation_id="get_model_list")
async def get_model_list(session: SessionDep):
    return session.query(AiModelDetail).all()


@router.post("/mcp_start", operation_id="mcp_start")
async def mcp_start(session: SessionDep, chat: ChatMcp):
    user = await get_current_user(session, chat.token)
    return create_chat(session, user, CreateChat(), False)


@router.post("/mcp_question", operation_id="mcp_question")
async def mcp_question(session: SessionDep, chat: ChatMcp):
    user = await get_current_user(session, chat.token)

    llm_service = LLMService(session, user, chat)
    llm_service.init_record()

    run_task(llm_service, session)

    # return await stream_sql(session, user, chat)
    return {"content": """这是一段写死的测试内容：

    步骤1: 确定需要查询的字段。
    我们需要统计上海的订单总数，因此需要从"城市"字段中筛选出值为"上海"的记录，并使用COUNT函数计算这些记录的数量。

    步骤2: 确定筛选条件。
    问题要求统计上海的订单总数，所以我们需要在SQL语句中添加WHERE "城市" = '上海'来筛选出符合条件的记录。

    步骤3: 避免关键字冲突。
    因为这个Excel/CSV数据库是 PostgreSQL 类型，所以在schema、表名、字段名和别名外层加双引号。

    最终答案:
    ```json
    {"success":true,"sql":"SELECT COUNT(*) AS \"TotalOrders\" FROM \"public\".\"Sheet1_c27345b66e\" WHERE \"城市\" = '上海';"}
    ```
    <img src="https://sqlbot.fit2cloud.cn/images/111.png">"""}
