import datetime
from decimal import Decimal
from typing import List, Optional, Union, Dict, Any

import orjson
import sqlparse
from sqlalchemy import and_, select, update
from sqlalchemy import desc, func
from sqlalchemy.orm import aliased

from apps.chat.models.chat_model import Chat, ChatRecord, CreateChat, ChatInfo, RenameChat, ChatQuestion, ChatLog, \
    TypeEnum, OperationEnum, ChatRecordResult, ChatLogHistory, ChatLogHistoryItem
from apps.dashboard.crud.dashboard_service import _execute_dashboard_chart_sql
from apps.datasource.crud.datasource import get_ds
from apps.datasource.crud.permission_errors import PERMISSION_DENIED_ERROR_TYPE
from apps.datasource.crud.permission import get_accessible_datasource_ids, has_datasource_access, is_normal_user
from apps.datasource.crud.sql_permission import validate_sql_scope
from apps.datasource.crud.recommended_problem import get_datasource_recommended_chart
from apps.datasource.models.datasource import CoreDatasource
from apps.db.constant import DB
from apps.system.crud.tenant_usage import record_tenant_usage_detached, token_total
from apps.system.crud.assistant import AssistantOutDs, AssistantOutDsFactory
from apps.system.schemas.system_schema import AssistantOutDsSchema
from common.core.deps import CurrentAssistant, SessionDep, CurrentUser, Trans
from common.utils.data_format import DataFormat
from common.utils.utils import extract_nested_json, AppLogUtil

_USER_PERMISSION_DENIED_MESSAGE = "SQL 超出当前数据权限范围"
DEFAULT_TENANT_ID = 1

CHAT_USAGE_METRICS = {
    OperationEnum.GENERATE_SQL: "chat.generate_sql",
    OperationEnum.GENERATE_CHART: "chat.generate_chart",
    OperationEnum.ANALYSIS: "chat.analysis",
    OperationEnum.PREDICT_DATA: "chat.predict",
    OperationEnum.GENERATE_RECOMMENDED_QUESTIONS: "chat.recommend",
    OperationEnum.CHOOSE_DATASOURCE: "chat.choose_datasource",
    OperationEnum.GENERATE_SQL_WITH_PERMISSIONS: "chat.generate_sql_with_permissions",
    OperationEnum.GENERATE_DYNAMIC_SQL: "chat.generate_dynamic_sql",
    OperationEnum.EXECUTE_SQL: "chat.execute_sql",
}


def _current_tenant_id(current_user: CurrentUser | None) -> int:
    tenant_id = getattr(current_user, "tenant_id", None)
    return int(tenant_id or DEFAULT_TENANT_ID)


def _same_tenant(row, current_user: CurrentUser | None) -> bool:
    return int(getattr(row, "tenant_id", DEFAULT_TENANT_ID) or DEFAULT_TENANT_ID) == _current_tenant_id(current_user)


def _record_tenant_id(session: SessionDep, record_id: int | None) -> int:
    if not record_id:
        return DEFAULT_TENANT_ID
    tenant_id = session.execute(select(ChatRecord.tenant_id).where(ChatRecord.id == record_id)).scalar()
    return int(tenant_id or DEFAULT_TENANT_ID)


def _chat_tenant_id(session: SessionDep, chat_id: int | None) -> int:
    if not chat_id:
        return DEFAULT_TENANT_ID
    tenant_id = session.execute(select(Chat.tenant_id).where(Chat.id == chat_id)).scalar()
    return int(tenant_id or DEFAULT_TENANT_ID)


def _record_chat_usage_from_log(log: ChatLog, *, success: bool) -> None:
    metric = CHAT_USAGE_METRICS.get(log.operate)
    if not metric:
        return
    total_tokens = token_total(log.token_usage)
    if log.local_operation and log.operate != OperationEnum.EXECUTE_SQL:
        return
    record_tenant_usage_detached(
        tenant_id=int(log.tenant_id or DEFAULT_TENANT_ID),
        metric=metric,
        request_count=1,
        success_count=1 if success else 0,
        failure_count=0 if success else 1,
        total_tokens=total_tokens,
    )


def _failed_permission_data(message: str = _USER_PERMISSION_DENIED_MESSAGE) -> dict[str, Any]:
    return {
        "status": "failed",
        "error_type": PERMISSION_DENIED_ERROR_TYPE,
        "fields": [],
        "data": [],
        "message": message,
        "reason": message,
    }


def _row_value(row, key: str):
    try:
        return getattr(row, key)
    except AttributeError:
        return None


def _record_has_sensitive_artifacts(row) -> bool:
    return any(
        _row_value(row, key)
        for key in (
            "sql_answer",
            "sql",
            "chart_answer",
            "chart",
            "analysis",
            "predict",
            "data",
            "predict_data",
            "datasource_select_answer",
        )
    )


def _record_allowed_by_current_permissions(session: SessionDep, current_user: CurrentUser, row) -> bool:
    if not is_normal_user(current_user):
        return True

    datasource_id = _row_value(row, "datasource")
    sql = _row_value(row, "sql")
    if not datasource_id:
        return True

    if not sql:
        source_record_id = _row_value(row, "analysis_record_id") or _row_value(row, "predict_record_id")
        if source_record_id:
            source_record = session.get(ChatRecord, source_record_id)
            if source_record is None or source_record.create_by != current_user.id or not _same_tenant(source_record, current_user):
                return False
            datasource_id = source_record.datasource
            sql = source_record.sql

    if not sql:
        return not _record_has_sensitive_artifacts(row)

    try:
        datasource = session.get(CoreDatasource, datasource_id)
        if datasource is None or not has_datasource_access(session, current_user, datasource_id):
            return False
        validate_sql_scope(session, current_user, datasource, sql)
        return True
    except Exception as exc:
        AppLogUtil.error(f"Chat record permission validation failed: {exc}")
        return False


def _scrub_record_for_current_permissions(record: ChatRecordResult) -> ChatRecordResult:
    record.sql_answer = None
    record.sql = None
    record.chart_answer = None
    record.chart = None
    record.analysis = None
    record.predict = None
    record.predict_data = None
    record.recommended_question = None
    record.datasource_select_answer = None
    record.sql_reasoning_content = None
    record.chart_reasoning_content = None
    record.analysis_reasoning_content = None
    record.predict_reasoning_content = None
    record.error = _USER_PERMISSION_DENIED_MESSAGE
    record.data = orjson.dumps(_failed_permission_data()).decode()
    return record


def _public_log_message(current_user: CurrentUser, log: ChatLog, message):
    if not is_normal_user(current_user):
        return message
    raw_message = message
    if log.operate == OperationEnum.EXECUTE_SQL:
        if isinstance(raw_message, str):
            try:
                raw_message = orjson.loads(raw_message)
            except Exception:
                raw_message = None
        if isinstance(raw_message, dict):
            return {"count": raw_message.get("count")}
    return None


def get_chat_record_by_id(session: SessionDep, record_id: int, tenant_id: int | None = None):
    record: ChatRecord | None = None

    stmt = select(ChatRecord.id, ChatRecord.question, ChatRecord.chat_id, ChatRecord.datasource, ChatRecord.engine_type,
                  ChatRecord.ai_modal_id, ChatRecord.create_by, ChatRecord.custom_prompt_id,
                  ChatRecord.tenant_id).where(
        and_(ChatRecord.id == record_id))
    if tenant_id is not None:
        stmt = stmt.where(ChatRecord.tenant_id == int(tenant_id))
    result = session.execute(stmt)
    for r in result:
        record = ChatRecord(id=r.id, question=r.question, chat_id=r.chat_id, datasource=r.datasource,
                            engine_type=r.engine_type, ai_modal_id=r.ai_modal_id, create_by=r.create_by,
                            custom_prompt_id=r.custom_prompt_id, tenant_id=r.tenant_id)
    return record


def get_chat(session: SessionDep, chat_id: int) -> Chat:
    statement = select(Chat).where(Chat.id == chat_id)
    chat = session.exec(statement).scalars().first()
    return chat


def list_chats(session: SessionDep, current_user: CurrentUser, datasource_id: Optional[int] = None) -> List[Chat]:
    filters = [Chat.create_by == current_user.id, Chat.tenant_id == _current_tenant_id(current_user)]
    if datasource_id:
        filters.append(Chat.datasource == datasource_id)
    else:
        accessible_ids = get_accessible_datasource_ids(session, current_user)
        if accessible_ids is not None:
            if not accessible_ids:
                return []
            filters.append(Chat.datasource.in_(accessible_ids))
    chart_list = session.query(Chat).filter(and_(*filters)).order_by(Chat.create_time.desc()).all()
    return chart_list


def list_recent_questions(session: SessionDep, current_user: CurrentUser, datasource_id: int) -> List[str]:
    chat_records = (
        session.query(
            ChatRecord.question
        )
        .join(Chat, ChatRecord.chat_id == Chat.id)  # 关联Chat表
        .filter(
            Chat.datasource == datasource_id,  # 使用Chat表的datasource字段
            Chat.tenant_id == _current_tenant_id(current_user),
            ChatRecord.tenant_id == _current_tenant_id(current_user),
            ChatRecord.question.isnot(None),
            ChatRecord.create_by == current_user.id
        )
        .group_by(ChatRecord.question)
        .order_by(desc(func.max(ChatRecord.create_time)))
        .limit(10)
        .all()
    )
    return [record[0] for record in chat_records] if chat_records else []


def rename_chat_with_user(session: SessionDep, current_user: CurrentUser, rename_object: RenameChat) -> str:
    chat = session.get(Chat, rename_object.id)
    if not chat:
        raise Exception(f"Chat with id {rename_object.id} not found")
    if chat.create_by != current_user.id or not _same_tenant(chat, current_user):
        raise Exception(f"Chat with id {rename_object.id} not Owned by the current user")
    chat.brief = rename_object.brief.strip()[:20]
    chat.brief_generate = rename_object.brief_generate
    session.add(chat)
    session.flush()
    session.refresh(chat)

    brief = chat.brief
    session.commit()
    return brief


def rename_chat(session: SessionDep, rename_object: RenameChat) -> str:
    chat = session.get(Chat, rename_object.id)
    if not chat:
        raise Exception(f"Chat with id {rename_object.id} not found")

    chat.brief = rename_object.brief.strip()[:20]
    chat.brief_generate = rename_object.brief_generate
    session.add(chat)
    session.flush()
    session.refresh(chat)

    brief = chat.brief
    session.commit()
    return brief


def delete_chat(session, chart_id) -> str:
    chat = session.query(Chat).filter(Chat.id == chart_id).first()
    if not chat:
        return f'Chat with id {chart_id} has been deleted'

    session.delete(chat)
    session.commit()

    return f'Chat with id {chart_id} has been deleted'


def delete_chat_with_user(session, current_user: CurrentUser, chart_id) -> str:
    chat = session.query(Chat).filter(Chat.id == chart_id).first()
    if not chat:
        return f'Chat with id {chart_id} has been deleted'
    if chat.create_by != current_user.id or not _same_tenant(chat, current_user):
        raise Exception(f"Chat with id {chart_id} not Owned by the current user")
    session.delete(chat)
    session.commit()

    return f'Chat with id {chart_id} has been deleted'


def get_chart_config(session: SessionDep, chart_record_id: int):
    stmt = select(ChatRecord.chart).where(and_(ChatRecord.id == chart_record_id))
    res = session.execute(stmt)
    for row in res:
        try:
            return orjson.loads(row.chart)
        except Exception:
            pass
    return {}


def _format_column(column: dict) -> str:
    """格式化单个column字段"""
    value = column.get('value', '')
    name = column.get('name', '')
    if value != name and name:
        return f"{value}({name})"
    return value


def format_chart_fields(chart_info: dict) -> list:
    fields = []

    # 处理 columns
    for column in chart_info.get('columns') or []:
        fields.append(_format_column(column))

    # 处理 axis
    if axis := chart_info.get('axis'):
        # 处理 x 轴
        if x_axis := axis.get('x'):
            fields.append(_format_column(x_axis))

        # 处理 y 轴
        if y_axis := axis.get('y'):
            if isinstance(y_axis, list):
                for column in y_axis:
                    fields.append(_format_column(column))
            else:
                fields.append(_format_column(y_axis))

        # 处理 series
        if series := axis.get('series'):
            fields.append(_format_column(series))

    return [field for field in fields if field]  # 过滤空字符串


def get_last_execute_sql_error(session: SessionDep, chart_id: int):
    stmt = select(ChatRecord.error).where(and_(ChatRecord.chat_id == chart_id)).order_by(
        ChatRecord.create_time.desc()).limit(1)
    res = session.execute(stmt).scalar()
    if res:
        try:
            obj = orjson.loads(res)
            if obj.get('type') and obj.get('type') == 'exec-sql-err':
                return obj.get('traceback')
        except Exception:
            pass

    return None


def format_json_data(origin_data: dict):
    result = {'fields': origin_data.get('fields') if origin_data.get('fields') else []}
    _list = origin_data.get('data') if origin_data.get('data') else []
    data = format_json_list_data(_list)
    result['data'] = data
    for key in ("status", "error_type", "message", "reason", "warning", "agent_guidance", "datasource", "limit"):
        if key in origin_data:
            result[key] = origin_data.get(key)

    return result


def format_json_list_data(origin_data: list[dict]):
    data = []
    for _data in origin_data if origin_data else []:
        _row = {}
        for key, value in _data.items():
            if value is not None:
                # 检查是否为数字且需要特殊处理
                if isinstance(value, (int, float)):
                    # 整数且超过15位 → 转字符串并标记为文本列
                    if isinstance(value, int) and len(str(abs(value))) > 15:
                        value = str(value)
                    # 小数且超过15位有效数字 → 转字符串并标记为文本列
                    elif isinstance(value, float):
                        decimal_str = str(Decimal(str(value))).rstrip('0').rstrip('.')
                        if len(decimal_str) > 15:
                            value = str(value)
            _row[key] = value
        data.append(DataFormat.normalize_qualified_sql_column_keys(_row))

    return data


def get_chat_chart_config(session: SessionDep, chat_record_id: int):
    stmt = select(ChatRecord.chart).where(and_(ChatRecord.id == chat_record_id))
    res = session.execute(stmt)
    for row in res:
        try:
            return orjson.loads(row.chart)
        except Exception:
            pass
    return {}


def _loads_record_data(data: str | None):
    if not data:
        return None
    try:
        return orjson.loads(data)
    except Exception:
        return None


def get_chart_data_with_user(session: SessionDep, current_user: CurrentUser, chat_record_id: int):
    stmt = select(
        ChatRecord.datasource,
        ChatRecord.sql,
        ChatRecord.data,
        ChatRecord.analysis_record_id,
        ChatRecord.predict_record_id,
    ).where(
        and_(
            ChatRecord.id == chat_record_id,
            ChatRecord.create_by == current_user.id,
            ChatRecord.tenant_id == _current_tenant_id(current_user),
        )
    )
    res = session.execute(stmt)
    for row in res:
        source_record_id = row.analysis_record_id or row.predict_record_id
        if row.datasource and source_record_id:
            result = get_chart_data_with_user(
                session=session,
                current_user=current_user,
                chat_record_id=source_record_id,
            )
            if result.get("status") == "failed":
                return _failed_permission_data()
            return result

        if row.datasource and row.sql:
            if not _record_allowed_by_current_permissions(session, current_user, row):
                return _failed_permission_data()
            data = _loads_record_data(row.data)
            if data is not None:
                return data
            return get_chart_data_with_user_live(
                session=session,
                current_user=current_user,
                chat_record_id=chat_record_id,
            )

        if row.datasource and row.data and is_normal_user(current_user):
            return _failed_permission_data()

        data = _loads_record_data(row.data)
        if data is not None:
            return data
    return {}

def get_chart_data_with_user_live(session: SessionDep, current_user: CurrentUser, chat_record_id: int):
    stmt = select(ChatRecord.datasource,ChatRecord.sql).where(and_(
        ChatRecord.id == chat_record_id,
        ChatRecord.create_by == current_user.id,
        ChatRecord.tenant_id == _current_tenant_id(current_user),
    ))
    row = session.execute(stmt).first()
    if row is None or row.datasource is None or not row.sql:
        return {'status': 'failed', 'fields': [], 'data': [], 'message': '记录不存在或没有可执行 SQL'}
    return _execute_dashboard_chart_sql(session, current_user, row.datasource, row.sql)

def get_chat_chart_data(session: SessionDep, chat_record_id: int):
    stmt = select(ChatRecord.data).where(and_(ChatRecord.id == chat_record_id))
    res = session.execute(stmt)
    for row in res:
        try:
            return orjson.loads(row.data)
        except Exception:
            pass
    return {}


def get_chat_predict_data_with_user(session: SessionDep, current_user: CurrentUser, chat_record_id: int):
    stmt = select(ChatRecord.predict_data, ChatRecord.predict_record_id).where(
        and_(
            ChatRecord.id == chat_record_id,
            ChatRecord.create_by == current_user.id,
            ChatRecord.tenant_id == _current_tenant_id(current_user),
        ))
    res = session.execute(stmt)
    for row in res:
        if row.predict_record_id:
            base_result = get_chart_data_with_user_live(
                session=session,
                current_user=current_user,
                chat_record_id=row.predict_record_id,
            )
            if base_result.get("status") == "failed":
                return []
        try:
            return orjson.loads(row.predict_data)
        except Exception:
            pass
    return {}


def get_chat_predict_data(session: SessionDep, chat_record_id: int):
    stmt = select(ChatRecord.predict_data).where(and_(ChatRecord.id == chat_record_id))
    res = session.execute(stmt)
    for row in res:
        try:
            return orjson.loads(row.predict_data)
        except Exception:
            pass
    return {}


def get_chat_with_records_with_data(session: SessionDep, chart_id: int, current_user: CurrentUser,
                                    current_assistant: CurrentAssistant) -> ChatInfo:
    return get_chat_with_records(session, chart_id, current_user, current_assistant, True)


dynamic_ds_types = [1, 3]


def get_chat_with_records(session: SessionDep, chart_id: int, current_user: CurrentUser,
                          current_assistant: CurrentAssistant, with_data: bool = False,
                          trans: Trans = None) -> ChatInfo:
    chat = session.get(Chat, chart_id)
    if not chat:
        raise Exception(f"Chat with id {chart_id} not found")
    if chat.create_by != current_user.id or not _same_tenant(chat, current_user):
        raise Exception(f"Chat with id {chart_id} not Owned by the current user")
    if chat.datasource and not has_datasource_access(session, current_user, chat.datasource):
        raise Exception(f"当前用户无权访问项目 {chat.datasource}")
    chat_info = ChatInfo(**chat.model_dump())

    if current_assistant and current_assistant.type in dynamic_ds_types:
        out_ds_instance = AssistantOutDsFactory.get_instance(current_assistant)
        ds = out_ds_instance.get_ds(chat.datasource, trans)
    else:
        ds = session.get(CoreDatasource, chat.datasource) if chat.datasource else None

    if not ds:
        chat_info.datasource_exists = False
        chat_info.datasource_name = '项目不存在'
    else:
        chat_info.datasource_exists = True
        chat_info.datasource_name = ds.name
        chat_info.ds_type = ds.type

    sql_alias_log = aliased(ChatLog)
    chart_alias_log = aliased(ChatLog)
    analysis_alias_log = aliased(ChatLog)
    predict_alias_log = aliased(ChatLog)

    tenant_id = _current_tenant_id(current_user)
    stmt = (select(ChatRecord.id, ChatRecord.tenant_id, ChatRecord.chat_id, ChatRecord.create_time, ChatRecord.finish_time,
                   ChatRecord.question, ChatRecord.sql_answer, ChatRecord.sql,ChatRecord.datasource,
                   ChatRecord.chart_answer, ChatRecord.chart, ChatRecord.analysis, ChatRecord.predict,
                   ChatRecord.datasource_select_answer, ChatRecord.analysis_record_id, ChatRecord.predict_record_id,
                   ChatRecord.regenerate_record_id,
                   ChatRecord.custom_prompt_id,
                   ChatRecord.recommended_question, ChatRecord.first_chat,
                   ChatRecord.finish, ChatRecord.error,
                   sql_alias_log.reasoning_content.label('sql_reasoning_content'),
                   chart_alias_log.reasoning_content.label('chart_reasoning_content'),
                   analysis_alias_log.reasoning_content.label('analysis_reasoning_content'),
                   predict_alias_log.reasoning_content.label('predict_reasoning_content')
                   )
    .outerjoin(sql_alias_log, and_(sql_alias_log.pid == ChatRecord.id,
                                   sql_alias_log.type == TypeEnum.CHAT,
                                   sql_alias_log.operate == OperationEnum.GENERATE_SQL))
    .outerjoin(chart_alias_log, and_(chart_alias_log.pid == ChatRecord.id,
                                     chart_alias_log.type == TypeEnum.CHAT,
                                     chart_alias_log.operate == OperationEnum.GENERATE_CHART))
    .outerjoin(analysis_alias_log, and_(analysis_alias_log.pid == ChatRecord.id,
                                        analysis_alias_log.type == TypeEnum.CHAT,
                                        analysis_alias_log.operate == OperationEnum.ANALYSIS))
    .outerjoin(predict_alias_log, and_(predict_alias_log.pid == ChatRecord.id,
                                       predict_alias_log.type == TypeEnum.CHAT,
                                       predict_alias_log.operate == OperationEnum.PREDICT_DATA))
    .where(and_(
        ChatRecord.create_by == current_user.id,
        ChatRecord.chat_id == chart_id,
        ChatRecord.tenant_id == tenant_id,
    )).order_by(
        ChatRecord.create_time))
    if with_data:
        stmt = select(ChatRecord.id, ChatRecord.tenant_id, ChatRecord.chat_id, ChatRecord.create_time, ChatRecord.finish_time,
                      ChatRecord.question, ChatRecord.sql_answer, ChatRecord.sql,ChatRecord.datasource,
                      ChatRecord.chart_answer, ChatRecord.chart, ChatRecord.analysis, ChatRecord.predict,
                      ChatRecord.datasource_select_answer, ChatRecord.analysis_record_id, ChatRecord.predict_record_id,
                      ChatRecord.regenerate_record_id,
                      ChatRecord.custom_prompt_id,
                      ChatRecord.recommended_question, ChatRecord.first_chat,
                      ChatRecord.finish, ChatRecord.error, ChatRecord.data, ChatRecord.predict_data).where(
            and_(
                ChatRecord.create_by == current_user.id,
                ChatRecord.chat_id == chart_id,
                ChatRecord.tenant_id == tenant_id,
            )).order_by(
            ChatRecord.create_time)

    result = session.execute(stmt).all()
    record_list: list[ChatRecordResult] = []

    # 批量获取所有ChatRecord的token消耗
    record_ids = [row.id for row in result]
    token_usage_map = {}

    if record_ids:
        # 查询所有相关ChatLog的token_usage
        log_stmt = select(ChatLog.pid, ChatLog.token_usage).where(
            and_(
                ChatLog.pid.in_(record_ids),
                ChatLog.tenant_id == tenant_id,
                ChatLog.local_operation == False,
                ChatLog.operate != OperationEnum.GENERATE_RECOMMENDED_QUESTIONS,
                ChatLog.token_usage.is_not(None)  # 排除token_usage为空的记录
            )
        )
        log_results = session.execute(log_stmt).all()

        # 按pid分组计算total_tokens总和
        for pid, token_usage in log_results:
            if pid and token_usage is not None:
                tokens_to_add = 0

                if isinstance(token_usage, dict):
                    # 处理字典类型: {"input_tokens": 961, "total_tokens": 1006, "output_tokens": 45}
                    if token_usage:  # 非空字典
                        if "total_tokens" in token_usage:
                            token_value = token_usage["total_tokens"]
                            if isinstance(token_value, (int, float)):
                                tokens_to_add = int(token_value)
                elif isinstance(token_usage, (int, float)):
                    tokens_to_add = int(token_usage)
                if tokens_to_add > 0:
                    if pid not in token_usage_map:
                        token_usage_map[pid] = 0
                    token_usage_map[pid] += tokens_to_add

    for row in result:
        # 计算耗时
        duration = None
        if row.create_time and row.finish_time:
            try:
                time_diff = row.finish_time - row.create_time
                duration = time_diff.total_seconds()  # 转换为秒
            except Exception:
                duration = None

        # 获取token总消耗
        total_tokens = token_usage_map.get(row.id, 0)
        current_permission_allowed = _record_allowed_by_current_permissions(session, current_user, row)

        data_value = _row_value(row, "data")
        if row.datasource and (row.sql or row.analysis_record_id or row.predict_record_id):
            data_value = orjson.dumps(get_chart_data_with_user(
                session=session,
                current_user=current_user,
                chat_record_id=row.id,
            )).decode()

        record_result: ChatRecordResult
        if not with_data:
            record_result = ChatRecordResult(id=row.id, tenant_id=row.tenant_id, chat_id=row.chat_id, create_time=row.create_time,
                                             finish_time=row.finish_time,
                                             duration=duration,
                                             total_tokens=total_tokens,
                                             question=row.question, sql_answer=row.sql_answer, sql=row.sql,
                                             datasource=row.datasource,
                                             chart_answer=row.chart_answer, chart=row.chart,
                                             analysis=row.analysis, predict=row.predict,
                                             datasource_select_answer=row.datasource_select_answer,
                                             analysis_record_id=row.analysis_record_id,
                                             predict_record_id=row.predict_record_id,
                                             regenerate_record_id=row.regenerate_record_id,
                                             custom_prompt_id=row.custom_prompt_id,
                                             recommended_question=row.recommended_question, first_chat=row.first_chat,
                                             finish=row.finish, error=row.error, data=data_value,
                                             sql_reasoning_content=row.sql_reasoning_content,
                                             chart_reasoning_content=row.chart_reasoning_content,
                                             analysis_reasoning_content=row.analysis_reasoning_content,
                                             predict_reasoning_content=row.predict_reasoning_content,
                                             )
        else:
            predict_data_value = row.predict_data
            if row.predict_record_id and not current_permission_allowed:
                predict_data_value = None
            record_result = ChatRecordResult(id=row.id, tenant_id=row.tenant_id, chat_id=row.chat_id, create_time=row.create_time,
                                             finish_time=row.finish_time,
                                             duration=duration,
                                             total_tokens=total_tokens,
                                             question=row.question, sql_answer=row.sql_answer, sql=row.sql,
                                             datasource=row.datasource,
                                             chart_answer=row.chart_answer, chart=row.chart,
                                             analysis=row.analysis, predict=row.predict,
                                             datasource_select_answer=row.datasource_select_answer,
                                             analysis_record_id=row.analysis_record_id,
                                             predict_record_id=row.predict_record_id,
                                             regenerate_record_id=row.regenerate_record_id,
                                             custom_prompt_id=row.custom_prompt_id,
                                             recommended_question=row.recommended_question, first_chat=row.first_chat,
                                             finish=row.finish, error=row.error, data=data_value,
                                             predict_data=predict_data_value)

        if not current_permission_allowed:
            record_result = _scrub_record_for_current_permissions(record_result)
        record_list.append(record_result)

    result = list(map(format_record, record_list))

    for row in result:
        try:
            data_value = row.get('data')
            if data_value is not None:
                row['data'] = format_json_data(data_value)
        except Exception:
            pass

    chat_info.records = result

    return chat_info


def format_record(record: ChatRecordResult):
    _dict = record.model_dump()

    if record.sql_answer and record.sql_answer.strip() != '' and record.sql_answer.strip()[0] == '{' and \
            record.sql_answer.strip()[-1] == '}':
        _obj = orjson.loads(record.sql_answer)
        _dict['sql_answer'] = _obj.get('reasoning_content')
    if record.sql_reasoning_content and record.sql_reasoning_content.strip() != '':
        _dict['sql_answer'] = record.sql_reasoning_content
    if record.chart_answer and record.chart_answer.strip() != '' and record.chart_answer.strip()[0] == '{' and \
            record.chart_answer.strip()[-1] == '}':
        _obj = orjson.loads(record.chart_answer)
        _dict['chart_answer'] = _obj.get('reasoning_content')
    if record.chart_reasoning_content and record.chart_reasoning_content.strip() != '':
        _dict['chart_answer'] = record.chart_reasoning_content
    if record.analysis and record.analysis.strip() != '' and record.analysis.strip()[0] == '{' and \
            record.analysis.strip()[-1] == '}':
        _obj = orjson.loads(record.analysis)
        _dict['analysis_thinking'] = _obj.get('reasoning_content')
        _dict['analysis'] = _obj.get('content')
    if record.analysis_reasoning_content and record.analysis_reasoning_content.strip() != '':
        _dict['analysis_thinking'] = record.analysis_reasoning_content
    if record.predict and record.predict.strip() != '' and record.predict.strip()[0] == '{' and record.predict.strip()[
        -1] == '}':
        _obj = orjson.loads(record.predict)
        _dict['predict'] = _obj.get('reasoning_content')
        _dict['predict_content'] = _obj.get('content')
    if record.predict_reasoning_content and record.predict_reasoning_content.strip() != '':
        _dict['predict'] = record.predict_reasoning_content
    if record.data and record.data.strip() != '':
        try:
            _obj = orjson.loads(record.data)
            _dict['data'] = _obj
        except Exception:
            pass
    if record.predict_data and record.predict_data.strip() != '':
        try:
            _obj = orjson.loads(record.predict_data)
            _dict['predict_data'] = _obj
        except Exception:
            pass
    if record.sql and record.sql.strip() != '':
        try:
            _dict['sql'] = sqlparse.format(record.sql, reindent=True)
        except Exception:
            pass

    # 格式化duration字段，保留2位小数
    if 'duration' in _dict and _dict['duration'] is not None:
        try:
            # 可以格式化为更易读的形式
            _dict['duration'] = round(_dict['duration'], 2)  # 保留2位小数
        except Exception:
            pass

    # 格式化total_tokens字段
    if 'total_tokens' in _dict and _dict['total_tokens'] is not None:
        try:
            # 确保是整数类型
            _dict['total_tokens'] = int(_dict['total_tokens']) if _dict['total_tokens'] else 0
        except Exception:
            _dict['total_tokens'] = 0

    # 去除返回前端多余的字段
    _dict.pop('sql_reasoning_content', None)
    _dict.pop('chart_reasoning_content', None)
    _dict.pop('analysis_reasoning_content', None)
    _dict.pop('predict_reasoning_content', None)

    return _dict


def get_chat_log_history(session: SessionDep, chat_record_id: int, current_user: CurrentUser,
                         without_steps: bool = False) -> ChatLogHistory:
    """
    获取ChatRecord的详细历史记录

    Args:
        session: 数据库会话
        chat_record_id: ChatRecord的ID
        current_user: 当前用户
        without_steps

    Returns:
        ChatLogHistory: 包含历史步骤和时间信息的对象
    """
    # 1. 首先验证ChatRecord存在且属于当前用户
    chat_record = session.get(ChatRecord, chat_record_id)
    if not chat_record:
        raise Exception(f"ChatRecord with id {chat_record_id} not found")

    tenant_id = _current_tenant_id(current_user)
    if chat_record.create_by != current_user.id or int(chat_record.tenant_id or DEFAULT_TENANT_ID) != tenant_id:
        raise Exception(f"ChatRecord with id {chat_record_id} not owned by the current user")

    # 2. 查询与该ChatRecord相关的所有ChatLog记录
    chat_logs = session.query(ChatLog).filter(
        ChatLog.pid == chat_record_id,
        ChatLog.tenant_id == tenant_id,
        ChatLog.operate != OperationEnum.GENERATE_RECOMMENDED_QUESTIONS
    ).order_by(ChatLog.start_time).all()

    # 3. 计算总的时间和token信息
    total_tokens = 0
    steps = []

    for log in chat_logs:
        # 计算单条记录的token消耗
        log_tokens = 0
        if log.token_usage is not None:
            if isinstance(log.token_usage, dict):
                if log.token_usage and "total_tokens" in log.token_usage:
                    token_value = log.token_usage["total_tokens"]
                    if isinstance(token_value, (int, float)):
                        log_tokens = int(token_value)
            elif isinstance(log.token_usage, (int, float)):
                log_tokens = log.token_usage

        # 累加到总token消耗
        total_tokens += log_tokens

        if not without_steps:
            # 计算单条记录的耗时
            duration = None
            if log.start_time and log.finish_time:
                try:
                    time_diff = log.finish_time - log.start_time
                    duration = round(time_diff.total_seconds(), 2)
                except Exception:
                    duration = None

            # 获取操作类型的枚举名称
            operate_name = None
            message = None
            if log.operate:
                # 如果是OperationEnum枚举实例
                if isinstance(log.operate, OperationEnum):
                    operate_name = log.operate.name
                # 如果是字符串，尝试从枚举值获取名称
                elif isinstance(log.operate, str):
                    try:
                        # 通过枚举值找到对应的枚举实例
                        for enum_item in OperationEnum:
                            if enum_item.value == log.operate:
                                operate_name = enum_item.name
                                break
                    except Exception:
                        operate_name = log.operate
                else:
                    operate_name = str(log.operate)

                if log.messages is not None:
                    message = log.messages
                    if not log.operate == OperationEnum.CHOOSE_TABLE:
                        try:
                            message = orjson.loads(log.messages)
                        except Exception:
                            pass
                    message = _public_log_message(current_user, log, message)

            # 创建ChatLogHistoryItem
            history_item = ChatLogHistoryItem(
                start_time=log.start_time,
                finish_time=log.finish_time,
                duration=duration,
                total_tokens=log_tokens,
                operate=operate_name,
                local_operation=log.local_operation,
                error=log.error,
                message=message,
            )

            steps.append(history_item)

    # 4. 计算总耗时（使用ChatRecord的时间）
    total_duration = None
    if chat_record.create_time and chat_record.finish_time:
        try:
            time_diff = chat_record.finish_time - chat_record.create_time
            total_duration = round(time_diff.total_seconds(), 2)
        except Exception:
            total_duration = None

    # 5. 创建并返回ChatLogHistory对象
    chat_log_history = ChatLogHistory(
        start_time=chat_record.create_time,  # 使用ChatRecord的create_time
        finish_time=chat_record.finish_time,  # 使用ChatRecord的finish_time
        duration=total_duration,
        total_tokens=total_tokens,
        steps=steps
    )

    return chat_log_history


def get_chat_brief_generate(session: SessionDep, chat_id: int):
    chat = get_chat(session=session, chat_id=chat_id)
    if chat is not None and chat.brief_generate is not None:
        return chat.brief_generate
    else:
        return False


def list_generate_sql_logs(session: SessionDep, chart_id: int) -> List[ChatLog]:
    tenant_id = _chat_tenant_id(session, chart_id)
    stmt = select(ChatLog).where(
        and_(
            ChatLog.pid.in_(select(ChatRecord.id).where(and_(
                ChatRecord.chat_id == chart_id,
                ChatRecord.tenant_id == tenant_id,
            ))),
            ChatLog.tenant_id == tenant_id,
            ChatLog.type == TypeEnum.CHAT,
            ChatLog.operate == OperationEnum.GENERATE_SQL,
        )).order_by(
        ChatLog.start_time)
    result = session.execute(stmt).all()
    _list = []
    for row in result:
        for r in row:
            _list.append(ChatLog(**r.model_dump()))
    return _list


def list_generate_chart_logs(session: SessionDep, chart_id: int) -> List[ChatLog]:
    tenant_id = _chat_tenant_id(session, chart_id)
    stmt = select(ChatLog).where(
        and_(
            ChatLog.pid.in_(select(ChatRecord.id).where(and_(
                ChatRecord.chat_id == chart_id,
                ChatRecord.tenant_id == tenant_id,
            ))),
            ChatLog.tenant_id == tenant_id,
            ChatLog.type == TypeEnum.CHAT,
            ChatLog.operate == OperationEnum.GENERATE_CHART,
        )).order_by(
        ChatLog.start_time)
    result = session.execute(stmt).all()
    _list = []
    for row in result:
        for r in row:
            _list.append(ChatLog(**r.model_dump()))
    return _list


def create_chat(session: SessionDep, current_user: CurrentUser, create_chat_obj: CreateChat,
                require_datasource: bool = True, current_assistant: CurrentAssistant = None) -> ChatInfo:
    if not create_chat_obj.datasource and require_datasource:
        raise Exception("项目不能为空")

    if not create_chat_obj.question or create_chat_obj.question.strip() == '':
        create_chat_obj.question = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    chat = Chat(create_time=datetime.datetime.now(),
                tenant_id=_current_tenant_id(current_user),
                create_by=current_user.id,
                brief=create_chat_obj.question.strip()[:20],
                origin=create_chat_obj.origin if create_chat_obj.origin is not None else 0)
    ds: CoreDatasource | AssistantOutDsSchema | None = None
    if create_chat_obj.datasource:
        chat.datasource = create_chat_obj.datasource
        if current_assistant and current_assistant.type == 1:
            out_ds_instance: AssistantOutDs = AssistantOutDsFactory.get_instance(current_assistant)
            ds = out_ds_instance.get_ds(chat.datasource)
            ds.type_name = DB.get_db(ds.type)
        else:
            ds = session.get(CoreDatasource, create_chat_obj.datasource)
            if not ds:
                raise Exception(f"项目 {create_chat_obj.datasource} 不存在")
            if not has_datasource_access(session, current_user, ds.id):
                raise Exception(f"当前用户无权访问项目 {create_chat_obj.datasource}")

        if not ds:
            raise Exception(f"项目 {create_chat_obj.datasource} 不存在")

        chat.engine_type = ds.type_name
    else:
        chat.engine_type = ''

    chat_info = ChatInfo(**chat.model_dump())

    session.add(chat)
    session.flush()
    session.refresh(chat)
    chat_info.id = chat.id
    session.commit()

    if ds:
        chat_info.datasource_exists = True
        chat_info.datasource_name = ds.name
        chat_info.ds_type = ds.type

    if require_datasource and ds:
        # generate first empty record
        record = ChatRecord()
        record.tenant_id = chat.tenant_id
        record.chat_id = chat.id
        record.datasource = ds.id
        record.engine_type = ds.type_name
        record.first_chat = True
        record.finish = True
        record.create_time = datetime.datetime.now()
        record.create_by = current_user.id
        if isinstance(ds, CoreDatasource) and ds.recommended_config == 2:
            questions = get_datasource_recommended_chart(session, ds.id)
            record.recommended_question = orjson.dumps(questions).decode()
            record.recommended_question_answer = orjson.dumps({
                "content": questions
            }).decode()

        _record = ChatRecord(**record.model_dump())

        session.add(record)
        session.flush()
        session.refresh(record)
        _record.id = record.id
        session.commit()

        chat_info.records.append(_record)

    return chat_info


def save_question(session: SessionDep, current_user: CurrentUser, question: ChatQuestion) -> ChatRecord:
    if not question.chat_id:
        raise Exception("ChatId cannot be None")
    if not question.question or question.question.strip() == '':
        raise Exception("Question cannot be Empty")

    # chat = session.query(Chat).filter(Chat.id == question.chat_id).first()
    chat: Chat = session.get(Chat, question.chat_id)
    if not chat:
        raise Exception(f"Chat with id {question.chat_id} not found")
    if chat.create_by != current_user.id or not _same_tenant(chat, current_user):
        raise Exception(f"Chat with id {question.chat_id} not Owned by the current user")

    record = ChatRecord()
    record.tenant_id = _current_tenant_id(current_user)
    record.question = question.question
    record.chat_id = chat.id
    record.create_time = datetime.datetime.now()
    record.create_by = current_user.id
    record.datasource = chat.datasource
    record.engine_type = chat.engine_type
    record.ai_modal_id = question.ai_modal_id
    record.regenerate_record_id = question.regenerate_record_id
    record.custom_prompt_id = question.custom_prompt_id

    result = ChatRecord(**record.model_dump())

    session.add(record)
    session.flush()
    session.refresh(record)
    result.id = record.id
    session.commit()

    return result


def save_analysis_predict_record(session: SessionDep, base_record: ChatRecord, action_type: str) -> ChatRecord:
    record = ChatRecord()
    record.tenant_id = int(base_record.tenant_id or DEFAULT_TENANT_ID)
    record.question = base_record.question
    record.chat_id = base_record.chat_id
    record.datasource = base_record.datasource
    record.engine_type = base_record.engine_type
    record.ai_modal_id = base_record.ai_modal_id
    record.custom_prompt_id = base_record.custom_prompt_id
    record.create_time = datetime.datetime.now()
    record.create_by = base_record.create_by
    record.chart = base_record.chart
    record.data = base_record.data

    if action_type == 'analysis':
        record.analysis_record_id = base_record.id
    elif action_type == 'predict':
        record.predict_record_id = base_record.id

    result = ChatRecord(**record.model_dump())

    session.add(record)
    session.flush()
    session.refresh(record)
    result.id = record.id
    session.commit()

    return result


def start_log(session: SessionDep, ai_modal_id: int = None, ai_modal_name: str = None, operate: OperationEnum = None,
              record_id: int = None, full_message: Union[list[dict], dict] = None,
              local_operation: bool = False) -> ChatLog:
    log = ChatLog(tenant_id=_record_tenant_id(session, record_id),
                  type=TypeEnum.CHAT, operate=operate, pid=record_id, ai_modal_id=ai_modal_id, base_modal=ai_modal_name,
                  messages=full_message, start_time=datetime.datetime.now(), local_operation=local_operation)

    result = ChatLog(**log.model_dump())

    session.add(log)
    session.flush()
    session.refresh(log)
    result.id = log.id
    session.commit()

    return result


def end_log(session: SessionDep, log: ChatLog, full_message: Union[list[dict], dict, str],
            reasoning_content: str = None,
            token_usage=None) -> ChatLog:
    if token_usage is None:
        token_usage = {}
    log.messages = full_message
    log.token_usage = token_usage
    log.finish_time = datetime.datetime.now()
    log.reasoning_content = reasoning_content if reasoning_content and len(reasoning_content.strip()) > 0 else None

    stmt = update(ChatLog).where(and_(ChatLog.id == log.id)).values(
        messages=log.messages,
        token_usage=log.token_usage,
        finish_time=log.finish_time,
        reasoning_content=log.reasoning_content
    )
    session.execute(stmt)
    session.commit()
    _record_chat_usage_from_log(log, success=True)

    return log


def trigger_log_error(session: SessionDep, log: ChatLog) -> ChatLog:
    log.error = True
    stmt = update(ChatLog).where(and_(ChatLog.id == log.id)).values(
        error=True
    )
    session.execute(stmt)
    session.commit()
    _record_chat_usage_from_log(log, success=False)

    return log


def save_sql_answer(session: SessionDep, record_id: int, answer: str) -> ChatRecord:
    if not record_id:
        raise Exception("Record id cannot be None")

    stmt = update(ChatRecord).where(and_(ChatRecord.id == record_id)).values(
        sql_answer=answer,
    )

    session.execute(stmt)

    session.commit()

    record = get_chat_record_by_id(session, record_id)

    return record


def save_analysis_answer(session: SessionDep, record_id: int, answer: str = '') -> ChatRecord:
    if not record_id:
        raise Exception("Record id cannot be None")

    stmt = update(ChatRecord).where(and_(ChatRecord.id == record_id)).values(
        analysis=answer,
    )

    session.execute(stmt)

    session.commit()

    record = get_chat_record_by_id(session, record_id)

    return record


def save_predict_answer(session: SessionDep, record_id: int, answer: str) -> ChatRecord:
    if not record_id:
        raise Exception("Record id cannot be None")

    stmt = update(ChatRecord).where(and_(ChatRecord.id == record_id)).values(
        predict=answer,
    )

    session.execute(stmt)

    session.commit()

    record = get_chat_record_by_id(session, record_id)

    return record


def save_select_datasource_answer(session: SessionDep, record_id: int, answer: str,
                                  datasource: int = None, engine_type: str = None) -> ChatRecord:
    if not record_id:
        raise Exception("Record id cannot be None")
    record = get_chat_record_by_id(session, record_id)

    record.datasource_select_answer = answer

    if datasource:
        record.datasource = datasource
        record.engine_type = engine_type

    result = ChatRecord(**record.model_dump())

    if datasource:
        stmt = update(ChatRecord).where(and_(ChatRecord.id == record.id)).values(
            datasource_select_answer=record.datasource_select_answer,
            datasource=record.datasource,
            engine_type=record.engine_type,
        )
    else:
        stmt = update(ChatRecord).where(and_(ChatRecord.id == record.id)).values(
            datasource_select_answer=record.datasource_select_answer,
        )

    session.execute(stmt)

    session.commit()

    return result


def save_recommend_question_answer(session: SessionDep, record_id: int,
                                   answer: dict = None, articles_number: Optional[int] = 4) -> ChatRecord:
    if not record_id:
        raise Exception("Record id cannot be None")

    recommended_question_answer = orjson.dumps(answer).decode()

    json_str = '[]'
    if answer and answer.get('content') and answer.get('content') != '':
        try:
            json_str = extract_nested_json(answer.get('content'))

            if not json_str:
                json_str = '[]'
        except Exception:
            pass
    recommended_question = json_str

    stmt = update(ChatRecord).where(and_(ChatRecord.id == record_id)).values(
        recommended_question_answer=recommended_question_answer,
        recommended_question=recommended_question,
    )

    session.execute(stmt)
    session.commit()

    record = get_chat_record_by_id(session, record_id)
    record.recommended_question_answer = recommended_question_answer
    record.recommended_question = recommended_question
    if articles_number > 4:
        stmt_chat = update(Chat).where(and_(Chat.id == record.chat_id)).values(
            recommended_question_answer=recommended_question_answer,
            recommended_question=recommended_question,
            recommended_generate=True
        )
        session.execute(stmt_chat)
        session.commit()

    return record


def save_sql(session: SessionDep, record_id: int, sql: str) -> ChatRecord:
    if not record_id:
        raise Exception("Record id cannot be None")

    record = get_chat_record_by_id(session, record_id)

    record.sql = sql

    result = ChatRecord(**record.model_dump())

    stmt = update(ChatRecord).where(and_(ChatRecord.id == record.id)).values(
        sql=record.sql
    )

    session.execute(stmt)

    session.commit()

    return result


def save_chart_answer(session: SessionDep, record_id: int, answer: str) -> ChatRecord:
    if not record_id:
        raise Exception("Record id cannot be None")

    stmt = update(ChatRecord).where(and_(ChatRecord.id == record_id)).values(
        chart_answer=answer,
    )

    session.execute(stmt)

    session.commit()

    record = get_chat_record_by_id(session, record_id)

    return record


def save_chart(session: SessionDep, record_id: int, chart: str) -> ChatRecord:
    if not record_id:
        raise Exception("Record id cannot be None")
    record = get_chat_record_by_id(session, record_id)

    record.chart = chart

    result = ChatRecord(**record.model_dump())

    stmt = update(ChatRecord).where(and_(ChatRecord.id == record.id)).values(
        chart=record.chart
    )

    session.execute(stmt)

    session.commit()

    return result


def save_predict_data(session: SessionDep, record_id: int, data: str = '') -> ChatRecord:
    if not record_id:
        raise Exception("Record id cannot be None")
    record = get_chat_record_by_id(session, record_id)

    record.predict_data = data

    result = ChatRecord(**record.model_dump())

    stmt = update(ChatRecord).where(and_(ChatRecord.id == record.id)).values(
        predict_data=record.predict_data
    )

    session.execute(stmt)

    session.commit()

    return result


def save_error_message(session: SessionDep, record_id: int, message: str) -> ChatRecord:
    if not record_id:
        raise Exception("Record id cannot be None")
    record = get_chat_record_by_id(session, record_id)

    record.error = message
    record.finish = True
    record.finish_time = datetime.datetime.now()

    result = ChatRecord(**record.model_dump())

    stmt = update(ChatRecord).where(and_(ChatRecord.id == record.id)).values(
        error=record.error,
        finish=record.finish,
        finish_time=record.finish_time
    )

    session.execute(stmt)

    session.commit()

    # log error finish
    stmt = update(ChatLog).where(and_(ChatLog.pid == record.id, ChatLog.finish_time.is_(None))).values(
        finish_time=record.finish_time,
        error=True
    )
    session.execute(stmt)
    session.commit()

    return result


def save_sql_exec_data(session: SessionDep, record_id: int, data: str) -> ChatRecord:
    if not record_id:
        raise Exception("Record id cannot be None")
    record = get_chat_record_by_id(session, record_id)

    record.data = data

    result = ChatRecord(**record.model_dump())

    stmt = update(ChatRecord).where(and_(ChatRecord.id == record.id)).values(
        data=record.data,
    )

    session.execute(stmt)

    session.commit()

    return result


def finish_record(session: SessionDep, record_id: int) -> ChatRecord:
    if not record_id:
        raise Exception("Record id cannot be None")
    record = get_chat_record_by_id(session, record_id)

    record.finish = True
    record.finish_time = datetime.datetime.now()

    result = ChatRecord(**record.model_dump())

    stmt = update(ChatRecord).where(and_(ChatRecord.id == record.id)).values(
        finish=record.finish,
        finish_time=record.finish_time
    )

    session.execute(stmt)

    session.commit()

    return result


def get_old_questions(session: SessionDep, datasource: int, current_user: CurrentUser = None):
    records = []
    if not datasource:
        return records
    conditions = [
        ChatRecord.datasource == datasource,
        ChatRecord.question.isnot(None),
        ChatRecord.error.is_(None),
    ]
    if current_user is not None:
        conditions.append(ChatRecord.create_by == current_user.id)
        conditions.append(ChatRecord.tenant_id == _current_tenant_id(current_user))
    stmt = select(ChatRecord.question).where(and_(*conditions)).order_by(
        ChatRecord.create_time.desc()).limit(20)
    result = session.execute(stmt)
    for r in result:
        records.append(r.question)
    return records
