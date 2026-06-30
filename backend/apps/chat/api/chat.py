"""
脚本说明：这个脚本放聊天问数据和 Agent的接口，把前端请求接进来并交给后面的业务逻辑处理。
"""
import asyncio
import io
import traceback
from typing import Optional, List

import orjson
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, select
from starlette.responses import JSONResponse

from apps.chat.curd.chat import delete_chat_with_user, get_chart_data_with_user, get_chat_predict_data_with_user, \
    list_chats, get_chat_with_records, create_chat, \
    get_chat_chart_data, get_chat_predict_data, get_chat_with_records_with_data, get_chat_record_by_id, \
    format_json_data, format_json_list_data, get_chart_config, list_recent_questions, \
    rename_chat_with_user, get_chat_log_history, get_chart_data_with_user_live
from apps.chat.models.chat_model import CreateChat, ChatRecord, RenameChat, ChatQuestion, AxisObj, QuickCommand, \
    ChatInfo, Chat, ChatFinishStep, ChatQuestionBase
from apps.chat.task.llm import LLMService
from apps.datasource.crud.permission import has_datasource_access
from apps.system.crud.tenant_usage import check_tenant_usage_quota
from apps.system.schemas.business_access import require_chatbi_business_user
from apps.system.schemas.access_context import require_current_tenant_id
from apps.swagger.i18n import PLACEHOLDER_PREFIX
from apps.system.schemas.permission import AppPermission, require_permissions
from common.core.deps import CurrentAssistant, SessionDep, CurrentUser, Trans
from common.core.tenant_rate_limiter import consume_tenant_rate_limit, resolve_tenant_rate_limit
from common.utils.command_utils import parse_quick_command
from common.utils.data_format import DataFormat
from common.audit.models.log_model import OperationType, OperationModules
from common.audit.schemas.logger_decorator import LogConfig, system_log

router = APIRouter(
    tags=["Data Q&A"],
    prefix="/chat",
    dependencies=[Depends(require_chatbi_business_user)],
)


def _current_tenant_id(current_user: CurrentUser) -> int:
    """
    是什么：_current_tenant_id 是从当前用户里取租户 ID 的小工具。
    谁调用：需要知道当前用户属于哪个租户的接口会调用它。
    做了什么：把用户上下文里的租户 ID 取出来，方便后面做权限和数据隔离。
    """
    return require_current_tenant_id(current_user)


def _rate_limit_message(retry_after_seconds: int) -> str:
    """
    是什么：_rate_limit_message 是组装限流提示文案的小工具。
    谁调用：用户请求太频繁时，限流处理会调用它。
    做了什么：把还需要等多久这件事变成用户能看懂的话。
    """
    return f"当前租户请求过于频繁，请稍后再试。约 {retry_after_seconds} 秒后可以重试。"


def _quota_message(state) -> str:
    """
    是什么：_quota_message 是组装额度不足提示的小工具。
    谁调用：租户用量不够或额度服务异常时，接口会调用它。
    做了什么：把额度问题整理成一句清楚的返回信息。
    """
    if getattr(state, "reason", None) == "subscription_suspended":
        return (
            f"当前租户订阅状态为 {getattr(state, 'subscription_status', 'suspended')}，"
            "高消耗功能已由 SaaS 管理员暂停。请联系工作空间管理员或 SaaS 管理员处理。"
        )
    window_name = "每日" if state.window == "daily" else "每月"
    return (
        f"当前租户套餐的{window_name} {state.action} 用量已达上限"
        f"（{state.used}/{state.limit}），请联系工作空间管理员或 SaaS 管理员调整套餐。"
    )


def _parse_chat_finish_step(value: int) -> ChatFinishStep:
    """
    是什么：_parse_chat_finish_step 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把聊天问数据和 Agent的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    try:
        return ChatFinishStep(value)
    except ValueError:
        allowed = ", ".join(str(step.value) for step in ChatFinishStep)
        raise HTTPException(status_code=400, detail=f"finish_step must be one of: {allowed}")


async def _tenant_rate_limit_response(
        session: SessionDep,
        current_user: CurrentUser,
        action: str,
        *,
        in_chat: bool = True,
        stream: bool = True,
):
    """
    是什么：_tenant_rate_limit_response 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    try:
        limit = resolve_tenant_rate_limit(session, _current_tenant_id(current_user), action)
        state = await consume_tenant_rate_limit(_current_tenant_id(current_user), action, limit=limit)
    except RuntimeError as exc:
        message = str(exc)
        if stream:
            def _err():
                """
                是什么：_err 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
                谁调用：外层函数 _tenant_rate_limit_response 跑到对应步骤时会调用它。
                做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
                """
                if in_chat:
                    yield 'data:' + orjson.dumps({
                        'content': message,
                        'type': 'error',
                        'error_type': 'rate_limit_unavailable',
                    }).decode() + '\n\n'
                else:
                    yield f'&#x274c; **ERROR:**\n> {message}\n'

            return StreamingResponse(_err(), media_type="text/event-stream", status_code=503)
        return JSONResponse(content={'message': message, 'error_type': 'rate_limit_unavailable'}, status_code=503)

    if state.allowed:
        try:
            quota_state = check_tenant_usage_quota(session, tenant_id=_current_tenant_id(current_user), action=action)
        except RuntimeError as exc:
            message = str(exc)
            if stream:
                def _quota_unavailable():
                    """
                    是什么：_quota_unavailable 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
                    谁调用：外层函数 _tenant_rate_limit_response 跑到对应步骤时会调用它。
                    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
                    """
                    if in_chat:
                        yield 'data:' + orjson.dumps({
                            'content': message,
                            'type': 'error',
                            'error_type': 'quota_unavailable',
                        }).decode() + '\n\n'
                    else:
                        yield f'&#x274c; **ERROR:**\n> {message}\n'

                return StreamingResponse(_quota_unavailable(), media_type="text/event-stream", status_code=503)
            return JSONResponse(content={'message': message, 'error_type': 'quota_unavailable'}, status_code=503)
        if quota_state.allowed:
            return None
        message = _quota_message(quota_state)
        if stream:
            def _quota_err():
                """
                是什么：_quota_err 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
                谁调用：外层函数 _tenant_rate_limit_response 跑到对应步骤时会调用它。
                做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
                """
                if in_chat:
                    yield 'data:' + orjson.dumps({
                        'content': message,
                        'type': 'error',
                        'error_type': 'quota_exceeded',
                        'quota': {
                            'action': quota_state.action,
                            'window': quota_state.window,
                            'limit': quota_state.limit,
                            'used': quota_state.used,
                            'remaining': quota_state.remaining,
                            'reset_at': quota_state.reset_at,
                        },
                    }).decode() + '\n\n'
                else:
                    yield f'&#x274c; **ERROR:**\n> {message}\n'

            return StreamingResponse(_quota_err(), media_type="text/event-stream", status_code=429)
        return JSONResponse(
            content={
                'message': message,
                'error_type': 'quota_exceeded',
                'quota': {
                    'action': quota_state.action,
                    'window': quota_state.window,
                    'limit': quota_state.limit,
                    'used': quota_state.used,
                    'remaining': quota_state.remaining,
                    'reset_at': quota_state.reset_at,
                },
            },
            status_code=429,
        )

    message = _rate_limit_message(state.retry_after_seconds)
    headers = {"Retry-After": str(state.retry_after_seconds)}
    if stream:
        def _err():
            """
            是什么：_err 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
            谁调用：外层函数 _tenant_rate_limit_response 跑到对应步骤时会调用它。
            做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
            """
            if in_chat:
                yield 'data:' + orjson.dumps({
                    'content': message,
                    'type': 'error',
                    'error_type': 'rate_limited',
                    'retry_after_seconds': state.retry_after_seconds,
                }).decode() + '\n\n'
            else:
                yield f'&#x274c; **ERROR:**\n> {message}\n'

        return StreamingResponse(
            _err(),
            media_type="text/event-stream",
            status_code=429,
            headers=headers,
        )
    return JSONResponse(
        content={
            'message': message,
            'error_type': 'rate_limited',
            'retry_after_seconds': state.retry_after_seconds,
        },
        status_code=429,
        headers=headers,
    )


@router.get("/list", response_model=List[Chat], summary=f"{PLACEHOLDER_PREFIX}get_chat_list")
async def chats(session: SessionDep, current_user: CurrentUser,
                datasource_id: Optional[int] = Query(None, description=f"{PLACEHOLDER_PREFIX}ds_id")):
    """
    是什么：chats 是一个接口入口，负责接住聊天问数据和 Agent相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if datasource_id is not None and not has_datasource_access(session, current_user, datasource_id):
        raise HTTPException(status_code=403, detail="Datasource access is required")
    return list_chats(session, current_user, datasource_id)


@router.get("/{chart_id}", response_model=ChatInfo, summary=f"{PLACEHOLDER_PREFIX}get_chat")
async def get_chat(session: SessionDep, current_user: CurrentUser, chart_id: int, current_assistant: CurrentAssistant,
                   trans: Trans):
    """
    是什么：get_chat 是一个接口入口，负责接住聊天问数据和 Agent相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把聊天问数据和 Agent需要的数据找出来，整理成后面好用的样子。
    """
    def inner():
        """
        是什么：inner 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
        谁调用：外层函数 get_chat 跑到对应步骤时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return get_chat_with_records(chart_id=chart_id, session=session, current_user=current_user,
                                     current_assistant=current_assistant, trans=trans)

    return await asyncio.to_thread(inner)


@router.get("/{chart_id}/with_data", response_model=ChatInfo, summary=f"{PLACEHOLDER_PREFIX}get_chat_with_data")
async def get_chat_with_data(session: SessionDep, current_user: CurrentUser, chart_id: int,
                             current_assistant: CurrentAssistant,
                             datasource_id: Optional[int] = Query(None, description=f"{PLACEHOLDER_PREFIX}ds_id")):
    """
    是什么：get_chat_with_data 是一个接口入口，负责接住聊天问数据和 Agent相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把聊天问数据和 Agent需要的数据找出来，整理成后面好用的样子。
    """
    def inner():
        """
        是什么：inner 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
        谁调用：外层函数 get_chat_with_data 跑到对应步骤时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        chat_info = get_chat_with_records_with_data(chart_id=chart_id, session=session, current_user=current_user,
                                                    current_assistant=current_assistant)
        if datasource_id and int(chat_info.datasource or 0) != int(datasource_id):
            raise HTTPException(
                status_code=403,
                detail="Chat does not belong to current project"
            )
        return chat_info

    return await asyncio.to_thread(inner)


""" @router.get("/record/{chat_record_id}/data", summary=f"{PLACEHOLDER_PREFIX}get_chart_data")
async def chat_record_data(session: SessionDep, chat_record_id: int):
    def inner():
        data = get_chat_chart_data(chat_record_id=chat_record_id, session=session)
        return format_json_data(data)

    return await asyncio.to_thread(inner)


@router.get("/record/{chat_record_id}/predict_data", summary=f"{PLACEHOLDER_PREFIX}get_chart_predict_data")
async def chat_predict_data(session: SessionDep, chat_record_id: int):
    def inner():
        data = get_chat_predict_data(chat_record_id=chat_record_id, session=session)
        return format_json_list_data(data)

    return await asyncio.to_thread(inner) """


@router.get("/record/{chat_record_id}/data", summary=f"{PLACEHOLDER_PREFIX}get_chart_data")
async def chat_record_data(session: SessionDep, current_user: CurrentUser, chat_record_id: int):
    """
    是什么：chat_record_data 是一个接口入口，负责接住聊天问数据和 Agent相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    def inner():
        """
        是什么：inner 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
        谁调用：外层函数 chat_record_data 跑到对应步骤时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        data = get_chart_data_with_user(chat_record_id=chat_record_id, session=session, current_user=current_user)
        return format_json_data(data)

    return await asyncio.to_thread(inner)


@router.get("/record/{chat_record_id}/data_live", summary=f"{PLACEHOLDER_PREFIX}get_chart_data_live")
async def chat_record_data_live(session: SessionDep, current_user: CurrentUser, chat_record_id: int):
    """
    是什么：chat_record_data_live 是一个接口入口，负责接住聊天问数据和 Agent相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    def inner():
        """
        是什么：inner 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
        谁调用：外层函数 chat_record_data_live 跑到对应步骤时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        data = get_chart_data_with_user_live(chat_record_id=chat_record_id, session=session, current_user=current_user)
        return format_json_data(data)

    return await asyncio.to_thread(inner)


@router.get("/record/{chat_record_id}/predict_data", summary=f"{PLACEHOLDER_PREFIX}get_chart_predict_data")
async def chat_predict_data(session: SessionDep, current_user: CurrentUser, chat_record_id: int):
    """
    是什么：chat_predict_data 是一个接口入口，负责接住聊天问数据和 Agent相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    def inner():
        """
        是什么：inner 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
        谁调用：外层函数 chat_predict_data 跑到对应步骤时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        data = get_chat_predict_data_with_user(chat_record_id=chat_record_id, session=session,
                                               current_user=current_user)
        return format_json_list_data(data)

    return await asyncio.to_thread(inner)


@router.get("/record/{chat_record_id}/log", summary=f"{PLACEHOLDER_PREFIX}get_record_log")
async def chat_record_log(session: SessionDep, current_user: CurrentUser, chat_record_id: int):
    """
    是什么：chat_record_log 是一个接口入口，负责接住聊天问数据和 Agent相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    def inner():
        """
        是什么：inner 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
        谁调用：外层函数 chat_record_log 跑到对应步骤时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return get_chat_log_history(session, chat_record_id, current_user)

    return await asyncio.to_thread(inner)


@router.get("/record/{chat_record_id}/usage", summary=f"{PLACEHOLDER_PREFIX}get_record_usage")
async def chat_record_usage(session: SessionDep, current_user: CurrentUser, chat_record_id: int):
    """
    是什么：chat_record_usage 是一个接口入口，负责接住聊天问数据和 Agent相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    def inner():
        """
        是什么：inner 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
        谁调用：外层函数 chat_record_usage 跑到对应步骤时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return get_chat_log_history(session, chat_record_id, current_user, True)

    return await asyncio.to_thread(inner)


""" @router.post("/rename", response_model=str, summary=f"{PLACEHOLDER_PREFIX}rename_chat")
@system_log(LogConfig(
    operation_type=OperationType.UPDATE,
    module=OperationModules.CHAT,
    resource_id_expr="chat.id"
))
async def rename(session: SessionDep, chat: RenameChat):
    try:
        return rename_chat(session=session, rename_object=chat)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        ) """


@router.post("/rename", response_model=str, summary=f"{PLACEHOLDER_PREFIX}rename_chat")
@system_log(LogConfig(
    operation_type=OperationType.UPDATE,
    module=OperationModules.CHAT,
    resource_id_expr="chat.id"
))
async def rename(session: SessionDep, current_user: CurrentUser, chat: RenameChat):
    """
    是什么：rename 是一个接口入口，负责接住聊天问数据和 Agent相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把聊天问数据和 Agent相关的信息改成最新状态，并保存这些变化。
    """
    try:
        return rename_chat_with_user(session=session, current_user=current_user, rename_object=chat)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


""" @router.delete("/{chart_id}/{brief}", response_model=str, summary=f"{PLACEHOLDER_PREFIX}delete_chat")
@system_log(LogConfig(
    operation_type=OperationType.DELETE,
    module=OperationModules.CHAT,
    resource_id_expr="chart_id",
    remark_expr="brief"
))
async def delete(session: SessionDep, chart_id: int, brief: str):
    try:
        return delete_chat(session=session, chart_id=chart_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        ) """


@router.delete("/{chart_id}/{brief}", response_model=str, summary=f"{PLACEHOLDER_PREFIX}delete_chat")
@system_log(LogConfig(
    operation_type=OperationType.DELETE,
    module=OperationModules.CHAT,
    resource_id_expr="chart_id",
    remark_expr="brief"
))
async def delete(session: SessionDep, current_user: CurrentUser, chart_id: int, brief: str):
    """
    是什么：delete 是一个接口入口，负责接住聊天问数据和 Agent相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把聊天问数据和 Agent不再需要的数据、缓存或临时内容清理掉。
    """
    try:
        return delete_chat_with_user(session=session, current_user=current_user, chart_id=chart_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.post("/start", response_model=ChatInfo, summary=f"{PLACEHOLDER_PREFIX}start_chat")
@require_permissions(permission=AppPermission(type='ds', keyExpression="create_chat_obj.datasource"))
@system_log(LogConfig(
    operation_type=OperationType.CREATE,
    module=OperationModules.CHAT,
    result_id_expr="id"
))
async def start_chat(session: SessionDep, current_user: CurrentUser, create_chat_obj: CreateChat):
    """
    是什么：start_chat 是一个接口入口，负责接住聊天问数据和 Agent相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把聊天问数据和 Agent的主要流程跑起来，一步步调用需要的处理。
    """
    try:
        return create_chat(session, current_user, create_chat_obj)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.post("/assistant/start", response_model=ChatInfo, summary=f"{PLACEHOLDER_PREFIX}assistant_start_chat")
@system_log(LogConfig(
    operation_type=OperationType.CREATE,
    module=OperationModules.CHAT,
    result_id_expr="id"
))
async def start_chat(session: SessionDep, current_user: CurrentUser, current_assistant: CurrentAssistant,
                     create_chat_obj: CreateChat = CreateChat(origin=2)):
    """
    是什么：start_chat 是一个接口入口，负责接住聊天问数据和 Agent相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把聊天问数据和 Agent的主要流程跑起来，一步步调用需要的处理。
    """
    try:
        if (
            create_chat_obj
            and create_chat_obj.datasource is not None
            and not has_datasource_access(session, current_user, create_chat_obj.datasource)
        ):
            raise HTTPException(status_code=403, detail="Datasource access is required")
        return create_chat(session, current_user, create_chat_obj, create_chat_obj and create_chat_obj.datasource,
                           current_assistant)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.post("/recommend_questions/{chat_record_id}", summary=f"{PLACEHOLDER_PREFIX}ask_recommend_questions")
async def ask_recommend_questions(session: SessionDep, current_user: CurrentUser, chat_record_id: int,
                                  current_assistant: CurrentAssistant, articles_number: Optional[int] = 4):
    """
    是什么：ask_recommend_questions 是一个接口入口，负责接住聊天问数据和 Agent相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    def _return_empty():
        """
        是什么：_return_empty 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
        谁调用：外层函数 ask_recommend_questions 跑到对应步骤时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        yield 'data:' + orjson.dumps({'content': '[]', 'type': 'recommended_question'}).decode() + '\n\n'

    limited_response = await _tenant_rate_limit_response(session, current_user, "recommend")
    if limited_response is not None:
        return limited_response

    try:
        record = get_chat_record_by_id(session, chat_record_id, _current_tenant_id(current_user))

        if not record or record.create_by != current_user.id:
            return StreamingResponse(_return_empty(), media_type="text/event-stream")

        request_question = ChatQuestion(chat_id=record.chat_id, question=record.question if record.question else '')

        llm_service = await LLMService.create(session, current_user, request_question, current_assistant, True)
        llm_service.set_record(record)
        llm_service.set_articles_number(articles_number)
        llm_service.run_recommend_questions_task_async()
    except Exception as e:
        traceback.print_exc()

        def _err(_e: Exception):
            """
            是什么：_err 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
            谁调用：外层函数 ask_recommend_questions 跑到对应步骤时会调用它。
            做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
            """
            yield 'data:' + orjson.dumps({'content': str(_e), 'type': 'error'}).decode() + '\n\n'

        return StreamingResponse(_err(e), media_type="text/event-stream")

    return StreamingResponse(llm_service.await_result(), media_type="text/event-stream")


@router.get("/recent_questions/{datasource_id}", response_model=List[str],
            summary=f"{PLACEHOLDER_PREFIX}get_recommend_questions")
# @require_permissions(permission=AppPermission(type='ds', keyExpression="datasource_id"))
async def recommend_questions(session: SessionDep, current_user: CurrentUser,
                              datasource_id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_id")):
    """
    是什么：recommend_questions 是一个接口入口，负责接住聊天问数据和 Agent相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：根据已有信息生成聊天问数据和 Agent的结果，比如答案、SQL、图表或建议。
    """
    return list_recent_questions(session=session, current_user=current_user, datasource_id=datasource_id)


def find_base_question(record_id: int, session: SessionDep, current_user: CurrentUser):
    """
    是什么：find_base_question 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把聊天问数据和 Agent需要的数据找出来，整理成后面好用的样子。
    """
    stmt = select(ChatRecord.question, ChatRecord.regenerate_record_id).where(
        and_(
            ChatRecord.id == record_id,
            ChatRecord.create_by == current_user.id,
            ChatRecord.tenant_id == _current_tenant_id(current_user),
        ))
    _record = session.execute(stmt).fetchone()
    if not _record:
        raise Exception(f'Cannot find base chat record')
    rec_question, rec_regenerate_record_id = _record
    if rec_regenerate_record_id:
        return find_base_question(rec_regenerate_record_id, session, current_user)
    else:
        return rec_question


@router.post("/question", summary=f"{PLACEHOLDER_PREFIX}ask_question")
@require_permissions(permission=AppPermission(type='chat', keyExpression="request_question.chat_id"))
async def question_answer(session: SessionDep, current_user: CurrentUser, request_question: ChatQuestionBase,
                          current_assistant: CurrentAssistant,
                          finish_step: int = Query(
                              ChatFinishStep.GENERATE_CHART.value,
                              description="Smart Q&A execution stop step. Defaults to full chart generation.",
                          )):
    """
    是什么：question_answer 是用户发起智能问数时进来的接口。
    谁调用：前端提交问题时，FastAPI 会把请求交给它。
    做了什么：先整理用户问题和权限信息，再把它交给真正的问数流程。
    """
    question = ChatQuestion(
        chat_id=request_question.chat_id,
        question=request_question.question,
        custom_prompt_id=request_question.custom_prompt_id,
        data_skill_id=request_question.data_skill_id,
    )
    return await question_answer_inner(
        session,
        current_user,
        question,
        current_assistant,
        finish_step=_parse_chat_finish_step(finish_step),
        embedding=True,
    )


async def question_answer_inner(session: SessionDep, current_user: CurrentUser, request_question: ChatQuestion,
                                current_assistant: Optional[CurrentAssistant] = None, in_chat: bool = True,
                                stream: bool = True,
                                finish_step: ChatFinishStep = ChatFinishStep.GENERATE_CHART, embedding: bool = False,
                                return_img: bool = True):
    """
    是什么：question_answer_inner 是智能问数的分流步骤。
    谁调用：question_answer 接到问题后会调用它。
    做了什么：判断这次是快捷命令、重新生成、分析预测，还是正常问数，然后分别交给对应流程。
    """
    try:
        command, text_before_command, record_id, warning_info = parse_quick_command(request_question.question)
        if command:
            # 待办：对话界面暂不支持分析和预测，需要改造前端
            if in_chat and (command == QuickCommand.ANALYSIS or command == QuickCommand.PREDICT_DATA):
                raise Exception(f'Command: {command.value} temporary not supported')

            if record_id is not None:
                # 排除分析和预测记录
                stmt = select(ChatRecord.id, ChatRecord.chat_id, ChatRecord.analysis_record_id,
                              ChatRecord.predict_record_id, ChatRecord.regenerate_record_id,
                              ChatRecord.first_chat).where(
                    and_(
                        ChatRecord.id == record_id,
                        ChatRecord.create_by == current_user.id,
                        ChatRecord.tenant_id == _current_tenant_id(current_user),
                    )).order_by(ChatRecord.create_time.desc())
                _record = session.execute(stmt).fetchone()
                if not _record:
                    raise Exception(f'Record id: {record_id} does not exist')

                rec_id, rec_chat_id, rec_analysis_record_id, rec_predict_record_id, rec_regenerate_record_id, rec_first_chat = _record

                if rec_chat_id != request_question.chat_id:
                    raise Exception(f'Record id: {record_id} does not belong to this chat')
                if rec_first_chat:
                    raise Exception(f'Record id: {record_id} does not support this operation')

                if rec_analysis_record_id:
                    raise Exception('Analysis record does not support this operation')
                if rec_predict_record_id:
                    raise Exception('Predict data record does not support this operation')

            else:  # 获取上一条记录 ID
                stmt = select(ChatRecord.id, ChatRecord.chat_id, ChatRecord.regenerate_record_id).where(
                    and_(ChatRecord.chat_id == request_question.chat_id,
                         ChatRecord.create_by == current_user.id,
                         ChatRecord.tenant_id == _current_tenant_id(current_user),
                         ChatRecord.first_chat == False,
                         ChatRecord.analysis_record_id.is_(None),
                         ChatRecord.predict_record_id.is_(None))).order_by(
                    ChatRecord.create_time.desc()).limit(1)
                _record = session.execute(stmt).fetchone()

                if not _record:
                    raise Exception(f'You have not ask any question')

                rec_id, rec_chat_id, rec_regenerate_record_id = _record

            # 没有指定的，就查询上一个
            if not rec_regenerate_record_id:
                rec_regenerate_record_id = rec_id

            # 针对已经是重新生成的提问，需要找到原来的提问是什么
            base_question_text = find_base_question(rec_regenerate_record_id, session, current_user)
            text_before_command = text_before_command + ("\n" if text_before_command else "") + base_question_text

            if command == QuickCommand.REGENERATE:
                request_question.question = text_before_command
                request_question.regenerate_record_id = rec_id
                return await stream_sql(session, current_user, request_question, current_assistant, in_chat, stream,
                                        finish_step, embedding, return_img)

            elif command == QuickCommand.ANALYSIS:
                return await analysis_or_predict(session, current_user, rec_id, 'analysis', current_assistant, in_chat,
                                                 stream)

            elif command == QuickCommand.PREDICT_DATA:
                return await analysis_or_predict(session, current_user, rec_id, 'predict', current_assistant, in_chat,
                                                 stream)
            else:
                raise Exception(f'Unknown command: {command.value}')
        else:
            return await stream_sql(session, current_user, request_question, current_assistant, in_chat, stream,
                                    finish_step, embedding, return_img)
    except Exception as e:
        traceback.print_exc()

        if stream:
            def _err(_e: Exception):
                """
                是什么：_err 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
                谁调用：外层函数 question_answer_inner 跑到对应步骤时会调用它。
                做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
                """
                if in_chat:
                    yield 'data:' + orjson.dumps({'content': str(_e), 'type': 'error'}).decode() + '\n\n'
                else:
                    yield f'&#x274c; **ERROR:**\n'
                    yield f'> {str(_e)}\n'

            return StreamingResponse(_err(e), media_type="text/event-stream")
        else:
            return JSONResponse(
                content={'message': str(e)},
                status_code=500,
            )


async def stream_sql(session: SessionDep, current_user: CurrentUser, request_question: ChatQuestion,
                     current_assistant: Optional[CurrentAssistant] = None, in_chat: bool = True, stream: bool = True,
                     finish_step: ChatFinishStep = ChatFinishStep.GENERATE_CHART, embedding: bool = False,
                     return_img: bool = True):
    """
    是什么：stream_sql 是启动智能问数任务并返回流式结果的步骤。
    谁调用：智能问数需要生成 SQL 和图表时会调用它。
    做了什么：检查频控和额度，创建 LLMService，启动后台任务，再把过程中的消息一段段推给前端。
    """
    limited_response = await _tenant_rate_limit_response(session, current_user, "chat", in_chat=in_chat, stream=stream)
    if limited_response is not None:
        return limited_response

    try:
        llm_service = await LLMService.create(session, current_user, request_question, current_assistant,
                                              embedding=embedding)
        llm_service.init_record(session=session)
        llm_service.run_task_async(in_chat=in_chat, stream=stream, finish_step=finish_step, return_img=return_img)
    except Exception as e:
        traceback.print_exc()

        if stream:
            def _err(_e: Exception):
                """
                是什么：_err 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
                谁调用：外层函数 stream_sql 跑到对应步骤时会调用它。
                做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
                """
                yield 'data:' + orjson.dumps({'content': str(_e), 'type': 'error'}).decode() + '\n\n'

            return StreamingResponse(_err(e), media_type="text/event-stream")
        else:
            return JSONResponse(
                content={'message': str(e)},
                status_code=500,
            )
    if stream:
        return StreamingResponse(llm_service.await_result(), media_type="text/event-stream")
    else:
        res = llm_service.await_result()
        raw_data = {}
        for chunk in res:
            if chunk:
                raw_data = chunk
        status_code = 200
        if not raw_data.get('success'):
            status_code = 500

        return JSONResponse(
            content=raw_data,
            status_code=status_code,
        )


@router.post("/record/{chat_record_id}/{action_type}", summary=f"{PLACEHOLDER_PREFIX}analysis_or_predict")
async def analysis_or_predict_question(session: SessionDep, current_user: CurrentUser,
                                       current_assistant: CurrentAssistant, chat_record_id: int,
                                       action_type: str = Path(...,
                                                               description=f"{PLACEHOLDER_PREFIX}analysis_or_predict_action_type")):
    """
    是什么：analysis_or_predict_question 是一个接口入口，负责接住聊天问数据和 Agent相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return await analysis_or_predict(session, current_user, chat_record_id, action_type, current_assistant)


async def analysis_or_predict(session: SessionDep, current_user: CurrentUser, chat_record_id: int, action_type: str,
                              current_assistant: CurrentAssistant, in_chat: bool = True, stream: bool = True):
    """
    是什么：analysis_or_predict 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    limited_response = await _tenant_rate_limit_response(session, current_user, "analysis", in_chat=in_chat, stream=stream)
    if limited_response is not None:
        return limited_response

    try:
        if action_type != 'analysis' and action_type != 'predict':
            raise Exception(f"Type {action_type} Not Found")
        record: ChatRecord | None = None

        stmt = select(ChatRecord.id, ChatRecord.tenant_id, ChatRecord.question, ChatRecord.chat_id, ChatRecord.datasource,
                      ChatRecord.engine_type,
                      ChatRecord.ai_modal_id, ChatRecord.create_by, ChatRecord.chart, ChatRecord.data,
                      ChatRecord.custom_prompt_id, ChatRecord.data_skill_id,
                      ChatRecord.agent_context_snapshot).where(
            and_(
                ChatRecord.id == chat_record_id,
                ChatRecord.create_by == current_user.id,
                ChatRecord.tenant_id == _current_tenant_id(current_user),
            ))
        result = session.execute(stmt)
        for r in result:
            record = ChatRecord(id=r.id, tenant_id=r.tenant_id, question=r.question, chat_id=r.chat_id, datasource=r.datasource,
                                engine_type=r.engine_type, ai_modal_id=r.ai_modal_id, create_by=r.create_by,
                                chart=r.chart,
                                data=r.data, custom_prompt_id=r.custom_prompt_id,
                                data_skill_id=r.data_skill_id,
                                agent_context_snapshot=r.agent_context_snapshot)

        if not record:
            raise Exception(f"Chat record with id {chat_record_id} not found")

        if not record.chart:
            raise Exception(
                f"Chat record with id {chat_record_id} has not generated chart, do not support to analyze it")

        current_data = get_chart_data_with_user(session, current_user, record.id)
        record.data = orjson.dumps(current_data).decode()

        request_question = ChatQuestion(
            chat_id=record.chat_id,
            question=record.question,
            custom_prompt_id=record.custom_prompt_id,
            data_skill_id=record.data_skill_id,
        )

        llm_service = await LLMService.create(session, current_user, request_question, current_assistant)
        llm_service.run_analysis_or_predict_task_async(session, action_type, record, in_chat, stream)
    except Exception as e:
        traceback.print_exc()
        if stream:
            def _err(_e: Exception):
                """
                是什么：_err 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
                谁调用：外层函数 analysis_or_predict 跑到对应步骤时会调用它。
                做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
                """
                if in_chat:
                    yield 'data:' + orjson.dumps({'content': str(_e), 'type': 'error'}).decode() + '\n\n'
                else:
                    yield f'&#x274c; **ERROR:**\n'
                    yield f'> {str(_e)}\n'

            return StreamingResponse(_err(e), media_type="text/event-stream")
        else:
            return JSONResponse(
                content={'message': str(e)},
                status_code=500,
            )
    if stream:
        return StreamingResponse(llm_service.await_result(), media_type="text/event-stream")
    else:
        res = llm_service.await_result()
        raw_data = {}
        for chunk in res:
            if chunk:
                raw_data = chunk
        status_code = 200
        if not raw_data.get('success'):
            status_code = 500

        return JSONResponse(
            content=raw_data,
            status_code=status_code,
        )


@router.get("/record/{chat_record_id}/excel/export/{chat_id}", summary=f"{PLACEHOLDER_PREFIX}export_chart_data")
@system_log(LogConfig(operation_type=OperationType.EXPORT, module=OperationModules.CHAT, resource_id_expr="chat_id", ))
async def export_excel(session: SessionDep, current_user: CurrentUser, chat_record_id: int, chat_id: int, trans: Trans):
    """
    是什么：export_excel 是一个接口入口，负责接住聊天问数据和 Agent相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    chat_record = session.get(ChatRecord, chat_record_id)
    if not chat_record:
        raise HTTPException(
            status_code=500,
            detail=f"ChatRecord with id {chat_record_id} not found"
        )
    if chat_record.create_by != current_user.id:
        raise HTTPException(
            status_code=500,
            detail=f"ChatRecord with id {chat_record_id} not Owned by the current user"
        )
    if int(chat_record.tenant_id) != _current_tenant_id(current_user):
        raise HTTPException(
            status_code=500,
            detail=f"ChatRecord with id {chat_record_id} not Owned by the current user"
        )
    is_predict_data = chat_record.predict_record_id is not None

    _origin_data = format_json_data(
        get_chart_data_with_user(chat_record_id=chat_record_id, session=session, current_user=current_user)
    )

    _base_field = _origin_data.get('fields')
    _data = _origin_data.get('data')

    if _origin_data.get("status") == "failed" or not _data:
        raise HTTPException(
            status_code=500,
            detail=_origin_data.get("message") or trans("i18n_excel_export.data_is_empty")
        )

    chart_info = get_chart_config(session, chat_record_id)

    _title = chart_info.get('title') if chart_info.get('title') else 'Excel'

    fields = []
    if chart_info.get('columns') and len(chart_info.get('columns')) > 0:
        for column in chart_info.get('columns'):
            fields.append(AxisObj(name=column.get('name') or column.get('value'), value=column.get('value') or column.get('name')))
    # 处理 axis
    if axis := chart_info.get('axis'):
        # 处理 x 轴
        if x_axis := axis.get('x'):
            if 'name' in x_axis or 'value' in x_axis:
                fields.append(AxisObj(name=x_axis.get('name') or x_axis.get('value'), value=x_axis.get('value') or x_axis.get('name')))

        # 处理 y 轴 - 兼容数组和对象格式
        if y_axis := axis.get('y'):
            if isinstance(y_axis, list):
                for column in y_axis:
                    if 'name' in column or 'value' in column:
                        fields.append(AxisObj(name=column.get('name') or column.get('value'), value=column.get('value') or column.get('name')))
            elif isinstance(y_axis, dict) and ('name' in y_axis or 'value' in y_axis):
                fields.append(AxisObj(name=y_axis.get('name') or y_axis.get('value'), value=y_axis.get('value') or y_axis.get('name')))

        # 处理 series
        if series := axis.get('series'):
            if 'name' in series or 'value' in series:
                fields.append(AxisObj(name=series.get('name') or series.get('value'), value=series.get('value') or series.get('name')))

    _predict_data = []
    if is_predict_data:
        _predict_data = format_json_list_data(
            get_chat_predict_data_with_user(
                chat_record_id=chat_record_id,
                session=session,
                current_user=current_user,
            )
        )

    def inner():

        """
        是什么：inner 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
        谁调用：外层函数 export_excel 跑到对应步骤时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        data_list = DataFormat.convert_large_numbers_in_object_array(obj_array=_data + _predict_data,
                                                                     int_threshold=1e11)

        md_data, _fields_list = DataFormat.convert_object_array_for_pandas(fields, data_list)

        # data, _fields_list, col_formats = LLMService.format_pd_data(fields, _data + _predict_data)

        df = pd.DataFrame(md_data, columns=_fields_list)

        buffer = io.BytesIO()

        with pd.ExcelWriter(buffer, engine='xlsxwriter',
                            engine_kwargs={'options': {'strings_to_numbers': False}}) as writer:
            df.to_excel(writer, sheet_name='Sheet1', index=False)

            # 获取 xlsxwriter 的工作簿和工作表对象
            # workbook = writer.book
            # worksheet = writer.sheets['Sheet1']
            #
            # for col_idx, fmt_type in col_formats.items():
            #     if fmt_type == 'text':
            #         worksheet.set_column(col_idx, col_idx, None, workbook.add_format({'num_format': '@'}))
            #     elif fmt_type == 'number':
            #         worksheet.set_column(col_idx, col_idx, None, workbook.add_format({'num_format': '0'}))

        buffer.seek(0)
        return io.BytesIO(buffer.getvalue())

    result = await asyncio.to_thread(inner)
    return StreamingResponse(result, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
