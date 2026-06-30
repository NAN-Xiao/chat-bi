import asyncio
import io
import traceback
from typing import Any, Optional, List

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
from apps.chat.task_events import get_chat_task_events
from apps.datasource.crud.permission import has_datasource_access
from apps.system.crud.tenant import TENANT_ADMIN_ROLES, normalize_tenant_role
from apps.system.crud.tenant_usage import check_tenant_usage_quota
from apps.system.crud.user import is_platform_admin
from apps.system.schemas.business_access import require_chatbi_business_user
from apps.system.schemas.access_context import require_current_tenant_id
from apps.swagger.i18n import PLACEHOLDER_PREFIX
from apps.system.schemas.permission import AppPermission, require_permissions
from common.core.deps import CurrentAssistant, SessionDep, CurrentUser, Trans
from common.core.task_queue import enqueue_task, get_task
from common.core.task_registry import register_builtin_tasks
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
    是什么：_current_tenant_id 是 backend/apps/chat/api/chat.py 中的同步函数。
    谁调用：由 FastAPI 路由处理函数或同模块业务辅助流程调用。
    做了什么：围绕 _current_tenant_id 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
    """
    return require_current_tenant_id(current_user)


def _rate_limit_message(retry_after_seconds: int) -> str:
    """
    是什么：_rate_limit_message 是 backend/apps/chat/api/chat.py 中的同步函数。
    谁调用：由 FastAPI 路由处理函数或同模块业务辅助流程调用。
    做了什么：围绕 _rate_limit_message 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
    """
    return f"当前租户请求过于频繁，请稍后再试。约 {retry_after_seconds} 秒后可以重试。"


def _quota_message(state) -> str:
    """
    是什么：_quota_message 是 backend/apps/chat/api/chat.py 中的同步函数。
    谁调用：由 FastAPI 路由处理函数或同模块业务辅助流程调用。
    做了什么：围绕 _quota_message 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
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
    是什么：_parse_chat_finish_step 是 backend/apps/chat/api/chat.py 中的同步函数。
    谁调用：由 FastAPI 路由处理函数或同模块业务辅助流程调用。
    做了什么：解析、转换或格式化聊天和 Agent相关数据，生成后续流程可使用的结构。
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
    是什么：_tenant_rate_limit_response 是 backend/apps/chat/api/chat.py 中的异步函数。
    谁调用：由 FastAPI 路由处理函数或同模块业务辅助流程调用。
    做了什么：围绕 _tenant_rate_limit_response 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
    """
    try:
        limit = resolve_tenant_rate_limit(session, _current_tenant_id(current_user), action)
        state = await consume_tenant_rate_limit(_current_tenant_id(current_user), action, limit=limit)
    except RuntimeError as exc:
        message = str(exc)
        if stream:
            def _err():
                """
                是什么：_err 是 backend/apps/chat/api/chat.py 中的同步函数。
                谁调用：由外层函数 _tenant_rate_limit_response 在执行内部流程时调用。
                做了什么：围绕 _err 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
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
                    是什么：_quota_unavailable 是 backend/apps/chat/api/chat.py 中的同步函数。
                    谁调用：由外层函数 _tenant_rate_limit_response 在执行内部流程时调用。
                    做了什么：围绕 _quota_unavailable 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
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
                是什么：_quota_err 是 backend/apps/chat/api/chat.py 中的同步函数。
                谁调用：由外层函数 _tenant_rate_limit_response 在执行内部流程时调用。
                做了什么：围绕 _quota_err 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
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
            是什么：_err 是 backend/apps/chat/api/chat.py 中的同步函数。
            谁调用：由外层函数 _tenant_rate_limit_response 在执行内部流程时调用。
            做了什么：围绕 _err 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
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
    是什么：chats 是 backend/apps/chat/api/chat.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 chats 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
    """
    if datasource_id is not None and not has_datasource_access(session, current_user, datasource_id):
        raise HTTPException(status_code=403, detail="Datasource access is required")
    return list_chats(session, current_user, datasource_id)


@router.get("/{chart_id}", response_model=ChatInfo, summary=f"{PLACEHOLDER_PREFIX}get_chat")
async def get_chat(session: SessionDep, current_user: CurrentUser, chart_id: int, current_assistant: CurrentAssistant,
                   trans: Trans):
    """
    是什么：get_chat 是 backend/apps/chat/api/chat.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：读取或查询聊天和 Agent相关数据，整理后返回给调用方。
    """
    def inner():
        """
        是什么：inner 是 backend/apps/chat/api/chat.py 中的同步函数。
        谁调用：由外层函数 get_chat 在执行内部流程时调用。
        做了什么：围绕 inner 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
        """
        return get_chat_with_records(chart_id=chart_id, session=session, current_user=current_user,
                                     current_assistant=current_assistant, trans=trans)

    return await asyncio.to_thread(inner)


@router.get("/{chart_id}/with_data", response_model=ChatInfo, summary=f"{PLACEHOLDER_PREFIX}get_chat_with_data")
async def get_chat_with_data(session: SessionDep, current_user: CurrentUser, chart_id: int,
                             current_assistant: CurrentAssistant,
                             datasource_id: Optional[int] = Query(None, description=f"{PLACEHOLDER_PREFIX}ds_id")):
    """
    是什么：get_chat_with_data 是 backend/apps/chat/api/chat.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：读取或查询聊天和 Agent相关数据，整理后返回给调用方。
    """
    def inner():
        """
        是什么：inner 是 backend/apps/chat/api/chat.py 中的同步函数。
        谁调用：由外层函数 get_chat_with_data 在执行内部流程时调用。
        做了什么：围绕 inner 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
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
    是什么：chat_record_data 是 backend/apps/chat/api/chat.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 chat_record_data 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
    """
    def inner():
        """
        是什么：inner 是 backend/apps/chat/api/chat.py 中的同步函数。
        谁调用：由外层函数 chat_record_data 在执行内部流程时调用。
        做了什么：围绕 inner 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
        """
        data = get_chart_data_with_user(chat_record_id=chat_record_id, session=session, current_user=current_user)
        return format_json_data(data)

    return await asyncio.to_thread(inner)


@router.get("/record/{chat_record_id}/data_live", summary=f"{PLACEHOLDER_PREFIX}get_chart_data_live")
async def chat_record_data_live(session: SessionDep, current_user: CurrentUser, chat_record_id: int):
    """
    是什么：chat_record_data_live 是 backend/apps/chat/api/chat.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 chat_record_data_live 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
    """
    def inner():
        """
        是什么：inner 是 backend/apps/chat/api/chat.py 中的同步函数。
        谁调用：由外层函数 chat_record_data_live 在执行内部流程时调用。
        做了什么：围绕 inner 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
        """
        data = get_chart_data_with_user_live(chat_record_id=chat_record_id, session=session, current_user=current_user)
        return format_json_data(data)

    return await asyncio.to_thread(inner)


@router.get("/record/{chat_record_id}/predict_data", summary=f"{PLACEHOLDER_PREFIX}get_chart_predict_data")
async def chat_predict_data(session: SessionDep, current_user: CurrentUser, chat_record_id: int):
    """
    是什么：chat_predict_data 是 backend/apps/chat/api/chat.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 chat_predict_data 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
    """
    def inner():
        """
        是什么：inner 是 backend/apps/chat/api/chat.py 中的同步函数。
        谁调用：由外层函数 chat_predict_data 在执行内部流程时调用。
        做了什么：围绕 inner 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
        """
        data = get_chat_predict_data_with_user(chat_record_id=chat_record_id, session=session,
                                               current_user=current_user)
        return format_json_list_data(data)

    return await asyncio.to_thread(inner)


@router.get("/record/{chat_record_id}/log", summary=f"{PLACEHOLDER_PREFIX}get_record_log")
async def chat_record_log(session: SessionDep, current_user: CurrentUser, chat_record_id: int):
    """
    是什么：chat_record_log 是 backend/apps/chat/api/chat.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 chat_record_log 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
    """
    def inner():
        """
        是什么：inner 是 backend/apps/chat/api/chat.py 中的同步函数。
        谁调用：由外层函数 chat_record_log 在执行内部流程时调用。
        做了什么：围绕 inner 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
        """
        return get_chat_log_history(session, chat_record_id, current_user)

    return await asyncio.to_thread(inner)


@router.get("/record/{chat_record_id}/usage", summary=f"{PLACEHOLDER_PREFIX}get_record_usage")
async def chat_record_usage(session: SessionDep, current_user: CurrentUser, chat_record_id: int):
    """
    是什么：chat_record_usage 是 backend/apps/chat/api/chat.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 chat_record_usage 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
    """
    def inner():
        """
        是什么：inner 是 backend/apps/chat/api/chat.py 中的同步函数。
        谁调用：由外层函数 chat_record_usage 在执行内部流程时调用。
        做了什么：围绕 inner 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
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
    是什么：rename 是 backend/apps/chat/api/chat.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：更新聊天和 Agent相关状态、配置或持久化数据，并保持后续流程可继续使用。
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
    是什么：delete 是 backend/apps/chat/api/chat.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：删除或清理聊天和 Agent相关数据、缓存或临时状态。
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
    是什么：start_chat 是 backend/apps/chat/api/chat.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：执行聊天和 Agent主流程，协调下游服务并处理结果或异常。
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
    是什么：start_chat 是 backend/apps/chat/api/chat.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：执行聊天和 Agent主流程，协调下游服务并处理结果或异常。
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
    是什么：ask_recommend_questions 是 backend/apps/chat/api/chat.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 ask_recommend_questions 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
    """
    def _return_empty():
        """
        是什么：_return_empty 是 backend/apps/chat/api/chat.py 中的同步函数。
        谁调用：由外层函数 ask_recommend_questions 在执行内部流程时调用。
        做了什么：围绕 _return_empty 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
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
            是什么：_err 是 backend/apps/chat/api/chat.py 中的同步函数。
            谁调用：由外层函数 ask_recommend_questions 在执行内部流程时调用。
            做了什么：围绕 _err 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
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
    是什么：recommend_questions 是 backend/apps/chat/api/chat.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：基于输入上下文生成聊天和 Agent相关结果，并保存或返回给调用方。
    """
    return list_recent_questions(session=session, current_user=current_user, datasource_id=datasource_id)


def find_base_question(record_id: int, session: SessionDep, current_user: CurrentUser):
    """
    是什么：find_base_question 是 backend/apps/chat/api/chat.py 中的同步函数。
    谁调用：由 FastAPI 路由处理函数或同模块业务辅助流程调用。
    做了什么：读取或查询聊天和 Agent相关数据，整理后返回给调用方。
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


def _serialize_current_assistant(current_assistant: CurrentAssistant) -> dict[str, Any] | None:
    if current_assistant is None:
        return None
    if hasattr(current_assistant, "model_dump"):
        return current_assistant.model_dump()
    if hasattr(current_assistant, "dict"):
        return current_assistant.dict()
    return None


def _can_read_chat_task(task: dict[str, Any], current_user: CurrentUser) -> bool:
    if int(task.get("tenant_id")) != _current_tenant_id(current_user):
        return False
    created_by = task.get("created_by")
    if created_by is not None and int(created_by) == int(current_user.id):
        return True
    tenant_role = normalize_tenant_role(
        getattr(current_user, "workspace_role", None)
        or getattr(current_user, "tenant_role", None)
    )
    return is_platform_admin(current_user) or tenant_role in TENANT_ADMIN_ROLES


@router.post("/question/task", summary=f"{PLACEHOLDER_PREFIX}ask_question")
@require_permissions(permission=AppPermission(type='chat', keyExpression="request_question.chat_id"))
async def start_question_task(session: SessionDep, current_user: CurrentUser, request_question: ChatQuestionBase,
                              current_assistant: CurrentAssistant,
                              finish_step: int = Query(
                                  ChatFinishStep.GENERATE_CHART.value,
                                  description="Smart Q&A execution stop step. Defaults to full chart generation.",
                              )):
    limited_response = await _tenant_rate_limit_response(session, current_user, "chat", stream=False)
    if limited_response is not None:
        return limited_response

    register_builtin_tasks()
    tenant_id = _current_tenant_id(current_user)
    task = await enqueue_task(
        "chat.smart_qa",
        {
            "question": request_question.question,
            "chat_id": request_question.chat_id,
            "custom_prompt_id": request_question.custom_prompt_id,
            "data_skill_id": request_question.data_skill_id,
            "finish_step": _parse_chat_finish_step(finish_step).value,
            "embedding": True,
            "return_img": True,
            "tenant_id": tenant_id,
            "user_id": current_user.id,
            "language": getattr(current_user, "language", "zh-CN"),
            "tenant_role": (
                getattr(current_user, "workspace_role", None)
                or getattr(current_user, "tenant_role", None)
                or "member"
            ),
            "assistant": _serialize_current_assistant(current_assistant),
        },
        created_by=current_user.id,
        tenant_id=tenant_id,
    )
    return {
        "task_id": task["id"],
        "status": task["status"],
    }


@router.get("/question/task/{task_id}/events", summary=f"{PLACEHOLDER_PREFIX}ask_question")
async def get_question_task_events(current_user: CurrentUser,
                                   task_id: str = Path(..., description="Smart Q&A task id"),
                                   offset: int = Query(0, ge=0),
                                   limit: int = Query(100, ge=1, le=500)):
    task = await get_task(task_id, tenant_id=_current_tenant_id(current_user))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if not _can_read_chat_task(task, current_user):
        raise HTTPException(status_code=403, detail="Permission denied")

    event_page = await get_chat_task_events(
        _current_tenant_id(current_user),
        task_id,
        offset=offset,
        limit=limit,
    )
    return {
        "task_id": task_id,
        "status": task.get("status"),
        "error": task.get("error"),
        "result": task.get("result"),
        **event_page,
    }


@router.post("/question", summary=f"{PLACEHOLDER_PREFIX}ask_question")
@require_permissions(permission=AppPermission(type='chat', keyExpression="request_question.chat_id"))
async def question_answer(session: SessionDep, current_user: CurrentUser, request_question: ChatQuestionBase,
                          current_assistant: CurrentAssistant,
                          finish_step: int = Query(
                              ChatFinishStep.GENERATE_CHART.value,
                              description="Smart Q&A execution stop step. Defaults to full chart generation.",
                          )):
    """
    是什么：question_answer 是 backend/apps/chat/api/chat.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 question_answer 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
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
    是什么：question_answer_inner 是 backend/apps/chat/api/chat.py 中的异步函数。
    谁调用：由 FastAPI 路由处理函数或同模块业务辅助流程调用。
    做了什么：围绕 question_answer_inner 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
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
                是什么：_err 是 backend/apps/chat/api/chat.py 中的同步函数。
                谁调用：由外层函数 question_answer_inner 在执行内部流程时调用。
                做了什么：围绕 _err 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
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
    是什么：stream_sql 是 backend/apps/chat/api/chat.py 中的异步函数。
    谁调用：由 FastAPI 路由处理函数或同模块业务辅助流程调用。
    做了什么：组织聊天和 Agent的流式输出或异步等待，把事件和结果传递给调用方。
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
                是什么：_err 是 backend/apps/chat/api/chat.py 中的同步函数。
                谁调用：由外层函数 stream_sql 在执行内部流程时调用。
                做了什么：围绕 _err 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
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
    是什么：analysis_or_predict_question 是 backend/apps/chat/api/chat.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 analysis_or_predict_question 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
    """
    return await analysis_or_predict(session, current_user, chat_record_id, action_type, current_assistant)


async def analysis_or_predict(session: SessionDep, current_user: CurrentUser, chat_record_id: int, action_type: str,
                              current_assistant: CurrentAssistant, in_chat: bool = True, stream: bool = True):
    """
    是什么：analysis_or_predict 是 backend/apps/chat/api/chat.py 中的异步函数。
    谁调用：由 FastAPI 路由处理函数或同模块业务辅助流程调用。
    做了什么：围绕 analysis_or_predict 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
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
                是什么：_err 是 backend/apps/chat/api/chat.py 中的同步函数。
                谁调用：由外层函数 analysis_or_predict 在执行内部流程时调用。
                做了什么：围绕 _err 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
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
    是什么：export_excel 是 backend/apps/chat/api/chat.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 export_excel 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
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
        是什么：inner 是 backend/apps/chat/api/chat.py 中的同步函数。
        谁调用：由外层函数 export_excel 在执行内部流程时调用。
        做了什么：围绕 inner 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
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
