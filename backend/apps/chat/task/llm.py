import concurrent
import json
import os
import traceback
import urllib.parse
import warnings
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional, Union, Dict, Iterator

import orjson
import pandas as pd
import requests
import sqlparse
from langchain.chat_models.base import BaseChatModel
from langchain_community.utilities import SQLDatabase
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, BaseMessageChunk
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlmodel import Session

from apps.ai_model.model_factory import LLMConfig, LLMFactory, get_default_config
from apps.chat.curd.chat import save_question, save_sql_answer, save_sql, \
    save_error_message, save_sql_exec_data, save_chart_answer, save_chart, \
    finish_record, save_analysis_answer, save_predict_answer, save_predict_data, \
    save_select_datasource_answer, save_recommend_question_answer, \
    get_old_questions, save_analysis_predict_record, rename_chat, get_chart_config, \
    get_chat_chart_data, list_generate_sql_logs, list_generate_chart_logs, start_log, end_log, \
    get_last_execute_sql_error, format_json_data, format_chart_fields, get_chat_brief_generate, get_chat_predict_data, \
    get_chat_chart_config, trigger_log_error
from apps.chat.curd.custom_prompt import (
    CustomPromptTargetScopeEnum,
    CustomPromptTypeEnum,
    find_custom_prompts,
    find_data_skills,
)
from apps.chat.models.chat_model import ChatQuestion, ChatRecord, Chat, RenameChat, ChatLog, OperationEnum, \
    ChatFinishStep, AxisObj, SystemPromptMessage, HumanPromptMessage, AIPromptMessage
from apps.datasource.crud.datasource import get_datasource_list, get_table_schema, get_tables_sample_data
from apps.datasource.crud.permission_errors import (
    PERMISSION_DENIED_AGENT_GUIDANCE,
    PERMISSION_DENIED_ERROR_TYPE,
    PERMISSION_DENIED_RESULT_MESSAGE,
    looks_like_permission_scope_error,
    permission_denied_result,
)
from apps.datasource.crud.permission import get_row_permission_filters, has_datasource_access, is_normal_user
from apps.datasource.crud.query_executor import (
    execute_external_user_query_or_raise,
    execute_user_analysis_query_or_raise,
    validate_user_query_sql_or_raise,
)
from apps.datasource.embedding.ds_embedding import get_ds_embedding
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import get_version, check_connection
from apps.system.crud.aimodel_manage import get_ai_model_list
from apps.system.crud.assistant import AssistantOutDs, AssistantOutDsFactory, get_assistant_ds
from apps.system.crud.parameter_manage import get_groups
from apps.system.crud.tenant import TENANT_ADMIN_ROLES, normalize_tenant_role
from apps.system.crud.tracking_config import find_tracking_prompt_context
from apps.system.crud.user import is_platform_admin, is_platform_workspace_delegate, is_system_admin
from apps.system.schemas.access_context import require_current_tenant_id
from apps.system.models.system_model import SysArgModel


def _can_manage_platform_prompt_runtime(user) -> bool:
    return bool(user is not None and is_platform_admin(user) and not is_platform_workspace_delegate(user))


def _can_manage_tenant_prompt_runtime(user) -> bool:
    if user is None or _can_manage_platform_prompt_runtime(user):
        return False
    if is_system_admin(user):
        return True
    return normalize_tenant_role(getattr(user, "tenant_role", None)) in TENANT_ADMIN_ROLES
from apps.system.schemas.system_schema import AssistantOutDsSchema
from common.core.config import settings
from common.core.db import engine
from common.core.deps import CurrentAssistant, CurrentUser
from common.error import SingleMessageError, AppDBError, ParseSQLResultError, AppDBConnectionError
from common.utils.data_format import DataFormat
from common.utils.locale import I18n, I18nHelper
from common.utils.utils import AppLogUtil, extract_nested_json, prepare_for_orjson

warnings.filterwarnings("ignore")

executor = ThreadPoolExecutor(max_workers=200)

dynamic_ds_types = [1, 3]
dynamic_subsql_prefix = 'select * from app_dynamic_temp_table_'

session_maker = scoped_session(sessionmaker(bind=engine, class_=Session))

i18n = I18n()

APP_SYSTEM_MESSAGE_KEY = "app_system"
APP_TEMP_SQL_TEXT_KEY = "app_temp_sql_text"


def _is_app_system_message(message: dict[str, Any]) -> bool:
    return message.get(APP_SYSTEM_MESSAGE_KEY) is True


def _message_has_app_system_flag(message: BaseMessage) -> bool:
    return getattr(message, APP_SYSTEM_MESSAGE_KEY, False) is True


def _serialize_prompt_messages(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    return [
        {
            "type": msg.type,
            APP_SYSTEM_MESSAGE_KEY: _message_has_app_system_flag(msg),
            "content": msg.content,
        }
        for msg in messages
    ]


def _get_temp_sql_text(dynamic_sql_result: Optional[dict[str, Any]]) -> Optional[str]:
    if not dynamic_sql_result:
        return None
    return dynamic_sql_result.get(APP_TEMP_SQL_TEXT_KEY)


def _remove_temp_sql_text(dynamic_sql_result: dict[str, Any]) -> None:
    dynamic_sql_result.pop(APP_TEMP_SQL_TEXT_KEY, None)


def _normalize_chart_field_name(value: Any) -> str:
    return str(value or "").strip().strip('`"[]').lower()


def _clean_chart_value(value: Any) -> str:
    return str(value or "").strip().strip('`"[]')


def _sanitize_chart_axis_binding(axis_item: Any) -> None:
    if not isinstance(axis_item, dict):
        return
    value = _clean_chart_value(axis_item.get("value") or axis_item.get("name"))
    if value:
        axis_item["value"] = value
    axis_item.pop("name", None)


def _sanitize_chart_bindings(chart: dict[str, Any]) -> dict[str, Any]:
    for column in chart.get("columns") or []:
        _sanitize_chart_axis_binding(column)

    axis = chart.get("axis")
    if isinstance(axis, dict):
        for key in ("x", "series"):
            _sanitize_chart_axis_binding(axis.get(key))

        y_axis = axis.get("y")
        if isinstance(y_axis, list):
            for item in y_axis:
                _sanitize_chart_axis_binding(item)
        else:
            _sanitize_chart_axis_binding(y_axis)

        multi_quota = axis.get("multi-quota")
        if isinstance(multi_quota, dict):
            values = multi_quota.get("value")
            if isinstance(values, list):
                multi_quota["value"] = [_clean_chart_value(value) for value in values if _clean_chart_value(value)]
            elif values:
                multi_quota["value"] = _clean_chart_value(values)
            multi_quota.pop("name", None)

    return chart


def _is_chart_numeric_value(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float, Decimal)):
        return True
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        if text.endswith("%"):
            text = text[:-1].strip()
        text = text.replace(",", "")
        try:
            float(text)
            return True
        except ValueError:
            return False
    return False


def _chart_axis_values(chart: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    chart_type = str(chart.get("type") or "").lower()
    for column in chart.get("columns") or []:
        if isinstance(column, dict) and column.get("value"):
            values.add(_normalize_chart_field_name(column.get("value")))

    axis = chart.get("axis") or {}
    for key in ("x", "series"):
        axis_item = axis.get(key)
        if isinstance(axis_item, dict) and axis_item.get("value"):
            values.add(_normalize_chart_field_name(axis_item.get("value")))

    y_axis = axis.get("y")
    if isinstance(y_axis, list):
        displayed_y_axis = y_axis[:1] if axis.get("series") and chart_type != "metric" else y_axis
        for y_item in displayed_y_axis:
            if isinstance(y_item, dict) and y_item.get("value"):
                values.add(_normalize_chart_field_name(y_item.get("value")))
    elif isinstance(y_axis, dict) and y_axis.get("value"):
        values.add(_normalize_chart_field_name(y_axis.get("value")))

    if not axis.get("series"):
        multi_quota = axis.get("multi-quota") or {}
        multi_values = multi_quota.get("value") if isinstance(multi_quota, dict) else None
        if isinstance(multi_values, list):
            values.update(_normalize_chart_field_name(value) for value in multi_values if value)
        elif multi_values:
            values.add(_normalize_chart_field_name(multi_values))
    return values


def _build_complete_table_chart(fields: list[Any], title: str | None = None) -> dict[str, Any]:
    columns = []
    for field in fields or []:
        field_name = str(field)
        columns.append({"value": field_name})
    return {
        "type": "table",
        "title": title or "数据明细",
        "columns": columns,
    }


def _is_rate_metric_field(field: str) -> bool:
    normalized = _normalize_chart_field_name(field)
    return any(
        token in normalized
        for token in (
            "rate",
            "ratio",
            "pct",
            "percent",
            "percentage",
            "conversion",
            "率",
            "占比",
            "比例",
            "转化",
        )
    )


def _is_average_metric_field(field: str) -> bool:
    normalized = _normalize_chart_field_name(field)
    return any(
        token in normalized
        for token in (
            "avg",
            "average",
            "mean",
            "per_",
            "per-",
            "per ",
            "平均",
            "人均",
            "每",
        )
    )


def _is_supporting_metric_field(field: str) -> bool:
    normalized = _normalize_chart_field_name(field)
    return any(
        token in normalized
        for token in (
            "base",
            "total",
            "size",
            "count",
            "num",
            "number",
            "人数",
            "次数",
            "数量",
            "分母",
            "分子",
        )
    )


def _is_numeric_dimension_field(field: str) -> bool:
    normalized = _normalize_chart_field_name(field)
    return any(
        token in normalized
        for token in (
            "id",
            "index",
            "rank",
            "order",
            "sort",
            "seq",
            "sequence",
            "week",
            "month",
            "year",
            "日期",
            "序号",
            "排序",
            "排名",
        )
    )


def _is_supporting_only_gap(covered_metrics: list[str], missing_metrics: list[str]) -> bool:
    if not covered_metrics or not missing_metrics:
        return False
    return any(_is_rate_metric_field(field) or _is_average_metric_field(field) for field in covered_metrics) and all(
        _is_supporting_metric_field(field) for field in missing_metrics
    )


def _is_funnel_supporting_metric_gap(
    chart: dict[str, Any],
    covered_metrics: list[str],
    missing_metrics: list[str],
) -> bool:
    if str(chart.get("type") or "").lower() != "funnel" or not covered_metrics or not missing_metrics:
        return False

    axis = chart.get("axis") or {}
    x_axis = axis.get("x")
    x_field = _normalize_chart_field_name(x_axis.get("value")) if isinstance(x_axis, dict) else ""
    if not any(token in x_field for token in ("step", "stage", "funnel", "步骤", "阶段")):
        return False

    def is_funnel_primary(field: str) -> bool:
        normalized = _normalize_chart_field_name(field)
        return any(
            token in normalized
            for token in (
                "users",
                "user_count",
                "count",
                "num",
                "value",
                "人数",
                "用户数",
                "数量",
            )
        )

    def is_funnel_auxiliary(field: str) -> bool:
        normalized = _normalize_chart_field_name(field)
        return any(
            token in normalized
            for token in (
                "conversion",
                "rate",
                "ratio",
                "pct",
                "percent",
                "dropoff",
                "drop_off",
                "drop",
                "lost",
                "loss",
                "流失",
                "掉点",
                "转化",
                "通过率",
            )
        )

    return any(is_funnel_primary(field) for field in covered_metrics) and all(
        is_funnel_auxiliary(field) or _is_supporting_metric_field(field)
        for field in missing_metrics
    )


def _ensure_chart_covers_metric_fields(
    chart: dict[str, Any],
    fields: list[Any] | None,
    rows: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Avoid silently reducing a multi-metric answer to a single-metric chart."""
    if chart.get("type") == "table" or not fields or not rows:
        return chart

    sample_rows = [row for row in rows[:20] if isinstance(row, dict)]
    if not sample_rows:
        return chart

    metric_fields: list[str] = []
    for field in fields:
        field_key = str(field)
        if _is_numeric_dimension_field(field_key):
            continue
        values = [row.get(field_key) for row in sample_rows if field_key in row]
        non_empty_values = [
            value for value in values if value is not None and not (isinstance(value, str) and not value.strip())
        ]
        if non_empty_values and any(_is_chart_numeric_value(value) for value in non_empty_values):
            metric_fields.append(field_key)

    if len(metric_fields) <= 1:
        return chart

    used_values = _chart_axis_values(chart)
    covered_metrics = [
        field for field in metric_fields if _normalize_chart_field_name(field) in used_values
    ]
    missing_metrics = [
        field for field in metric_fields if _normalize_chart_field_name(field) not in used_values
    ]
    if len(covered_metrics) < len(metric_fields):
        if _is_funnel_supporting_metric_gap(chart, covered_metrics, missing_metrics):
            return chart
        if _is_supporting_only_gap(covered_metrics, missing_metrics):
            return chart
        title = chart.get("title") or "指标对比"
        return _build_complete_table_chart(fields, title=title)

    return chart



class LLMService:
    ds: CoreDatasource
    chat_question: ChatQuestion
    record: ChatRecord
    config: LLMConfig
    llm: BaseChatModel
    sql_message: List[Union[BaseMessage, dict[str, Any]]]
    chart_message: List[Union[BaseMessage, dict[str, Any]]]

    # session: Session = db_session
    current_user: CurrentUser
    current_assistant: Optional[CurrentAssistant] = None
    out_ds_instance: Optional[AssistantOutDs] = None
    change_title: bool = False

    generate_sql_logs: List[ChatLog]
    generate_chart_logs: List[ChatLog]
    current_logs: dict[OperationEnum, ChatLog]
    chunk_list: List[str]
    future: Future

    trans: I18nHelper = None

    last_execute_sql_error: str = None
    articles_number: int = 4

    enable_sql_row_limit: bool = settings.GENERATE_SQL_QUERY_LIMIT_ENABLED
    base_message_round_count_limit: int = settings.GENERATE_SQL_QUERY_HISTORY_ROUND_COUNT

    def __init__(self, session: Session, current_user: CurrentUser, chat_question: ChatQuestion,
                 current_assistant: Optional[CurrentAssistant] = None, no_reasoning: bool = False,
                 embedding: bool = False, config: LLMConfig = None):
        self.sql_message = []
        self.chart_message = []
        self.generate_sql_logs = []
        self.generate_chart_logs = []
        self.current_logs = {}
        self.chunk_list = []
        self.current_user = current_user
        self.current_assistant = current_assistant

        self.table_name_list = []

        chat_id = chat_question.chat_id
        chat: Chat | None = session.get(Chat, chat_id)
        if not chat:
            raise SingleMessageError(f"Chat with id {chat_id} not found")
        tenant_id = require_current_tenant_id(current_user)
        if chat.create_by != current_user.id or int(chat.tenant_id) != tenant_id:
            raise SingleMessageError(f"Chat with id {chat_id} not Owned by the current user")
        ds: CoreDatasource | AssistantOutDsSchema | None = None
        if not chat.datasource and chat_question.datasource_id:
            _ds = session.get(CoreDatasource, chat_question.datasource_id)
            if _ds:
                if not has_datasource_access(session, current_user, _ds.id):
                    raise SingleMessageError(
                        f"当前用户无权访问项目 {chat_question.datasource_id}")
                chat.datasource = _ds.id
                chat.engine_type = _ds.type_name
                # save chat
                session.add(chat)
                session.flush()
                session.refresh(chat)
                session.commit()

        if chat.datasource:
            use_dynamic_assistant_ds = current_assistant and current_assistant.type in dynamic_ds_types
            if not use_dynamic_assistant_ds and not has_datasource_access(session, current_user, chat.datasource):
                raise SingleMessageError(f"当前用户无权访问项目 {chat.datasource}")
            # Get available datasource
            if use_dynamic_assistant_ds:
                self.out_ds_instance = AssistantOutDsFactory.get_instance(current_assistant)
                ds = self.out_ds_instance.get_ds(chat.datasource)
                if not ds:
                    raise SingleMessageError("当前没有可用项目，请联系管理员创建或分配项目")
                chat_question.engine = ds.type + get_version(ds)
            else:
                ds = session.get(CoreDatasource, chat.datasource)
                if not ds:
                    raise SingleMessageError("当前没有可用项目，请联系管理员创建或分配项目")
                chat_question.engine = (ds.type_name if ds.type != 'excel' else 'PostgreSQL') + get_version(ds)

        self.generate_sql_logs = list_generate_sql_logs(session=session, chart_id=chat_id)
        self.generate_chart_logs = list_generate_chart_logs(session=session, chart_id=chat_id)

        self.change_title = not get_chat_brief_generate(session=session, chat_id=chat_id)

        chat_question.lang = get_lang_name(current_user.language)
        self.trans = i18n(lang=current_user.language)

        self.ds = (
            ds if isinstance(ds, AssistantOutDsSchema) else CoreDatasource(**ds.model_dump())) if ds else None
        self.chat_question = chat_question
        self.config = config
        if no_reasoning:
            # only work while using qwen
            if self.config.additional_params:
                if self.config.additional_params.get('extra_body'):
                    if self.config.additional_params.get('extra_body').get('enable_thinking'):
                        del self.config.additional_params['extra_body']['enable_thinking']

        self.chat_question.ai_modal_id = self.config.model_id
        self.chat_question.ai_modal_name = self.config.model_name

        # Create LLM instance through factory
        llm_instance = LLMFactory.create_llm(self.config)
        self.llm = llm_instance.llm

        # get last_execute_sql_error
        last_execute_sql_error = get_last_execute_sql_error(session, self.chat_question.chat_id)
        if last_execute_sql_error:
            self.chat_question.error_msg = f'''<error-msg>
{last_execute_sql_error}
</error-msg>'''
        else:
            self.chat_question.error_msg = ''

    @classmethod
    async def create(cls, *args, **kwargs):
        specialized_model_id = None
        _ai_model_list = []
        if args[3]:
            if args[1]:
                _ai_model_list = get_ai_model_list(args[0], False)
            if args[3].enable_custom_model:
                if args[3].custom_model:
                    if any(str(model.id) == str(args[3].custom_model) for model in _ai_model_list):
                        specialized_model_id = args[3].custom_model
                        print("use custom model: id[" + specialized_model_id + "]")
        chat_question = args[2] if len(args) > 2 else None
        selected_prompt_id = getattr(chat_question, "custom_prompt_id", None)
        if selected_prompt_id:
            if not _ai_model_list and args[1]:
                _ai_model_list = get_ai_model_list(args[0], False)
            chat = args[0].get(Chat, chat_question.chat_id) if chat_question and chat_question.chat_id else None
            datasource_id = getattr(chat, "datasource", None) or getattr(chat_question, "datasource_id", None)
            _prompt, _prompt_list, prompt_model_id = find_custom_prompts(
                args[0],
                CustomPromptTypeEnum.GENERATE_SQL,
                datasource_id,
                CustomPromptTargetScopeEnum.SMART_QA,
                selected_prompt_id,
                getattr(args[1], "id", None),
                is_system_admin(args[1]),
                require_current_tenant_id(args[1]),
                can_manage_public=_can_manage_tenant_prompt_runtime(args[1]),
                can_manage_platform_public=_can_manage_platform_prompt_runtime(args[1]),
            )
            if prompt_model_id and any(str(model.id) == str(prompt_model_id) for model in _ai_model_list):
                specialized_model_id = prompt_model_id
        config: LLMConfig = await get_default_config(specialized_model_id)
        instance = cls(*args, **kwargs, config=config)

        chat_params: list[SysArgModel] = await get_groups(args[0], "chat")
        for config in chat_params:
            if config.pkey == 'chat.zhishu_name':
                if config.pval.strip():
                    instance.chat_question.zhishu_name = config.pval
            if config.pkey == 'chat.limit_rows':
                if config.pval.lower().strip() == 'true':
                    instance.enable_sql_row_limit = True
                else:
                    instance.enable_sql_row_limit = False
            if config.pkey == 'chat.context_record_count':
                count_value = config.pval
                if count_value is None:
                    count_value = settings.GENERATE_SQL_QUERY_HISTORY_ROUND_COUNT
                count_value = int(count_value)
                if count_value < 0:
                    count_value = 0
                instance.base_message_round_count_limit = count_value
        return instance

    def is_running(self, timeout=0.5):
        try:
            r = concurrent.futures.wait([self.future], timeout)
            if len(r.not_done) > 0:
                return True
            else:
                return False
        except Exception:
            return True

    def init_messages(self, session: Session):

        self.table_name_list = self.choose_table_schema(session)

        last_sql_messages: List[dict[str, Any]] = self.generate_sql_logs[-1].messages if len(
            self.generate_sql_logs) > 0 else []
        if self.chat_question.regenerate_record_id:
            # filter record before regenerate_record_id
            _temp_log = next(
                filter(lambda obj: obj.pid == self.chat_question.regenerate_record_id, self.generate_sql_logs), None)
            last_sql_messages: List[dict[str, Any]] = _temp_log.messages if _temp_log else []

        # 排除所有的系统提示词
        last_sql_messages = [obj for obj in last_sql_messages if not _is_app_system_message(obj)]

        count_limit = self.base_message_round_count_limit

        self.sql_message = []
        # add sys prompt
        _system_templates = self.chat_question.sql_sys_question(self.ds.type, self.enable_sql_row_limit)
        self.sql_message.append(SystemPromptMessage(content=_system_templates['system']))
        self.sql_message.append(HumanPromptMessage(content=_system_templates['rules']))
        self.sql_message.append(
            AIPromptMessage(content='我已掌握所有规则，包括表结构、SQL规范、安全限制和输出格式，我会严格遵守这些规则。'))
        self.sql_message.append(HumanPromptMessage(content=_system_templates['schema']))
        self.sql_message.append(
            AIPromptMessage(content='我已确认您提供的数据库信息与表结构schema，我生成的SQL不会超出您提供的范围。'))
        if _system_templates.get('tracking_config'):
            self.sql_message.append(HumanPromptMessage(content=_system_templates['tracking_config']))
            self.sql_message.append(
                AIPromptMessage(content='我已确认当前工作空间的打点字段规范，我会结合数据库Schema使用，不会编造不存在的表或字段。'))
        if _system_templates.get('custom_prompt'):
            self.sql_message.append(HumanPromptMessage(content=_system_templates['custom_prompt']))
            self.sql_message.append(AIPromptMessage(content='我已确认您提供的额外信息，我会进行参考。'))
        if _system_templates.get('data_skill'):
            self.sql_message.append(HumanPromptMessage(content=_system_templates['data_skill']))
            self.sql_message.append(AIPromptMessage(content='我已确认您提供的数据 Skill，我会优先参考其中的业务口径与查询范式。'))
        if last_sql_messages is not None and len(last_sql_messages) > 0:
            last_rounds = get_last_conversation_rounds(last_sql_messages, rounds=count_limit)

            for _msg_dict in last_rounds:
                _msg: BaseMessage
                if _msg_dict.get('type') == 'human':
                    _msg = HumanMessage(content=_msg_dict.get('content'))
                    self.sql_message.append(_msg)
                elif _msg_dict.get('type') == 'ai':
                    _msg = AIMessage(content=_msg_dict.get('content'))
                    self.sql_message.append(_msg)

        last_chart_messages: List[dict[str, Any]] = self.generate_chart_logs[-1].messages if len(
            self.generate_chart_logs) > 0 else []
        if self.chat_question.regenerate_record_id:
            # filter record before regenerate_record_id
            _temp_log = next(
                filter(lambda obj: obj.pid == self.chat_question.regenerate_record_id, self.generate_chart_logs), None)
            last_chart_messages: List[dict[str, Any]] = _temp_log.messages if _temp_log else []

        # 排除所有的系统提示词
        last_chart_messages = [obj for obj in last_chart_messages if not _is_app_system_message(obj)]

        count_chart_limit = self.base_message_round_count_limit

        self.chart_message = []
        # add sys prompt
        _chart_system_templates = self.chat_question.chart_sys_question()
        self.chart_message.append(SystemPromptMessage(content=_chart_system_templates['system']))
        self.chart_message.append(HumanPromptMessage(content=_chart_system_templates['rules']))
        self.chart_message.append(AIPromptMessage(content='我已掌握所有规则，我会严格遵守这些规则来生成符合要求的JSON。'))
        if last_chart_messages is not None and len(last_chart_messages) > 0:
            last_rounds = get_last_conversation_rounds(last_chart_messages, rounds=count_chart_limit)

            for _msg_dict in last_rounds:
                _msg: BaseMessage
                if _msg_dict.get('type') == 'human':
                    _msg = HumanMessage(content=_msg_dict.get('content'))
                    self.chart_message.append(_msg)
                elif _msg_dict.get('type') == 'ai':
                    _msg = AIMessage(content=_msg_dict.get('content'))
                    self.chart_message.append(_msg)

    def init_record(self, session: Session) -> ChatRecord:
        self.record = save_question(session=session, current_user=self.current_user, question=self.chat_question)
        return self.record

    def get_record(self):
        return self.record

    def set_record(self, record: ChatRecord):
        self.record = record

    def set_articles_number(self, articles_number: int):
        self.articles_number = articles_number

    def get_fields_from_chart(self, _session: Session):
        chart_info = get_chart_config(_session, self.record.id)
        return format_chart_fields(chart_info)

    def filter_custom_prompts(self, _session: Session, custom_prompt_type: CustomPromptTypeEnum, ds_id: int = None):
        if not self.chat_question.custom_prompt_id:
            self.chat_question.custom_prompt = ""
            return

        calculate_ds_id = ds_id
        if self.current_assistant:
            if self.current_assistant.type == 1:
                calculate_ds_id = None
        self.current_logs[OperationEnum.FILTER_CUSTOM_PROMPT] = start_log(session=_session,
                                                                          operate=OperationEnum.FILTER_CUSTOM_PROMPT,
                                                                          record_id=self.record.id,
                                                                          local_operation=True)
        self.chat_question.custom_prompt, prompt_list, _prompt_model_id = find_custom_prompts(
            _session,
            custom_prompt_type,
            calculate_ds_id,
            CustomPromptTargetScopeEnum.SMART_QA,
            self.chat_question.custom_prompt_id,
            self.current_user.id,
            is_system_admin(self.current_user),
            require_current_tenant_id(self.current_user),
            can_manage_public=_can_manage_tenant_prompt_runtime(self.current_user),
            can_manage_platform_public=_can_manage_platform_prompt_runtime(self.current_user),
        )
        self.current_logs[OperationEnum.FILTER_CUSTOM_PROMPT] = end_log(session=_session,
                                                                        log=self.current_logs[
                                                                            OperationEnum.FILTER_CUSTOM_PROMPT],
                                                                        full_message=prompt_list)

    def filter_data_skills(
            self,
            _session: Session,
            ds_id: int = None,
            target_scope: CustomPromptTargetScopeEnum = CustomPromptTargetScopeEnum.SMART_QA,
    ):
        calculate_ds_id = ds_id
        if self.current_assistant:
            if self.current_assistant.type == 1:
                calculate_ds_id = None
        self.current_logs[OperationEnum.FILTER_DATA_SKILL] = start_log(session=_session,
                                                                       operate=OperationEnum.FILTER_DATA_SKILL,
                                                                       record_id=self.record.id,
                                                                       local_operation=True)
        self.chat_question.data_skill, skill_list, _skill_model_id = find_data_skills(
            _session,
            calculate_ds_id,
            target_scope,
            self.chat_question.data_skill_id,
            self.current_user.id,
            is_system_admin(self.current_user),
            require_current_tenant_id(self.current_user),
            question=self.chat_question.question,
            can_manage_public=_can_manage_tenant_prompt_runtime(self.current_user),
            can_manage_platform_public=_can_manage_platform_prompt_runtime(self.current_user),
        )
        self.current_logs[OperationEnum.FILTER_DATA_SKILL] = end_log(session=_session,
                                                                     log=self.current_logs[
                                                                         OperationEnum.FILTER_DATA_SKILL],
                                                                     full_message=skill_list)

    def load_data_skills(
            self,
            _session: Session,
            ds_id: int = None,
            target_scope: CustomPromptTargetScopeEnum = CustomPromptTargetScopeEnum.SMART_QA,
    ):
        self.filter_data_skills(_session, ds_id, target_scope)

    def load_tracking_config(self, _session: Session):
        tenant_id = require_current_tenant_id(self.current_user)
        self.chat_question.tracking_config, _ = find_tracking_prompt_context(_session, tenant_id)

    def choose_table_schema(self, _session: Session):
        self.current_logs[OperationEnum.CHOOSE_TABLE] = start_log(session=_session,
                                                                  operate=OperationEnum.CHOOSE_TABLE,
                                                                  record_id=self.record.id,
                                                                  local_operation=True)
        self.chat_question.db_schema, tables = self.out_ds_instance.get_db_schema(
            self.ds.id, self.chat_question.question) if self.out_ds_instance else get_table_schema(
            session=_session,
            current_user=self.current_user,
            ds=self.ds,
            question=self.chat_question.question)

        # Get sample data for all tables
        if not self.out_ds_instance:
            self.chat_question.sample_data = get_tables_sample_data(
                session=_session,
                current_user=self.current_user,
                ds=self.ds,
                table_list=tables)

        self.current_logs[OperationEnum.CHOOSE_TABLE] = end_log(session=_session,
                                                                log=self.current_logs[OperationEnum.CHOOSE_TABLE],
                                                                full_message=self.chat_question.db_schema)
        return tables

    def generate_analysis(self, _session: Session):
        fields = self.get_fields_from_chart(_session)
        self.chat_question.fields = orjson.dumps(fields).decode()
        data = get_chat_chart_data(_session, self.record.id)
        self.chat_question.data = format_chart_data_for_agent_prompt(data)
        analysis_msg: List[Union[BaseMessage, dict[str, Any]]] = []

        ds_id = self.ds.id if isinstance(self.ds, CoreDatasource) else None

        self.load_data_skills(_session, ds_id, CustomPromptTargetScopeEnum.ANALYSIS_ASSISTANT)

        self.filter_custom_prompts(_session, CustomPromptTypeEnum.ANALYSIS, ds_id)

        analysis_msg.append(SystemPromptMessage(content=self.chat_question.analysis_sys_question()))
        analysis_msg.append(HumanMessage(content=self.chat_question.analysis_user_question()))

        self.current_logs[OperationEnum.ANALYSIS] = start_log(session=_session,
                                                              ai_modal_id=self.chat_question.ai_modal_id,
                                                              ai_modal_name=self.chat_question.ai_modal_name,
                                                              operate=OperationEnum.ANALYSIS,
                                                              record_id=self.record.id,
                                                              full_message=_serialize_prompt_messages(analysis_msg))
        full_thinking_text = ''
        full_analysis_text = ''
        token_usage = {}
        res = process_stream(self.llm.stream(analysis_msg), token_usage)
        for chunk in res:
            if chunk.get('content'):
                full_analysis_text += chunk.get('content')
            if chunk.get('reasoning_content'):
                full_thinking_text += chunk.get('reasoning_content')
            yield chunk

        analysis_msg.append(AIMessage(full_analysis_text))

        self.current_logs[OperationEnum.ANALYSIS] = end_log(session=_session,
                                                            log=self.current_logs[
                                                                OperationEnum.ANALYSIS],
                                                            full_message=_serialize_prompt_messages(analysis_msg),
                                                            reasoning_content=full_thinking_text,
                                                            token_usage=token_usage)
        self.record = save_analysis_answer(session=_session, record_id=self.record.id,
                                           answer=orjson.dumps({'content': full_analysis_text}).decode())

    def generate_predict(self, _session: Session):
        fields = self.get_fields_from_chart(_session)
        self.chat_question.fields = orjson.dumps(fields).decode()
        data = get_chat_chart_data(_session, self.record.id)
        self.chat_question.data = format_chart_data_for_agent_prompt(data)

        ds_id = self.ds.id if isinstance(self.ds, CoreDatasource) else None
        self.filter_data_skills(_session, ds_id, CustomPromptTargetScopeEnum.ANALYSIS_ASSISTANT)
        self.filter_custom_prompts(_session, CustomPromptTypeEnum.PREDICT_DATA, ds_id)

        predict_msg: List[Union[BaseMessage, dict[str, Any]]] = []
        predict_msg.append(SystemPromptMessage(content=self.chat_question.predict_sys_question()))
        predict_msg.append(HumanMessage(content=self.chat_question.predict_user_question()))

        self.current_logs[OperationEnum.PREDICT_DATA] = start_log(session=_session,
                                                                  ai_modal_id=self.chat_question.ai_modal_id,
                                                                  ai_modal_name=self.chat_question.ai_modal_name,
                                                                  operate=OperationEnum.PREDICT_DATA,
                                                                  record_id=self.record.id,
                                                                  full_message=_serialize_prompt_messages(predict_msg))
        full_thinking_text = ''
        full_predict_text = ''
        token_usage = {}
        res = process_stream(self.llm.stream(predict_msg), token_usage)
        for chunk in res:
            if chunk.get('content'):
                full_predict_text += chunk.get('content')
            if chunk.get('reasoning_content'):
                full_thinking_text += chunk.get('reasoning_content')
            yield chunk

        predict_msg.append(AIMessage(full_predict_text))
        self.record = save_predict_answer(session=_session, record_id=self.record.id,
                                          answer=orjson.dumps({'content': full_predict_text}).decode())
        self.current_logs[OperationEnum.PREDICT_DATA] = end_log(session=_session,
                                                                log=self.current_logs[
                                                                    OperationEnum.PREDICT_DATA],
                                                                full_message=_serialize_prompt_messages(predict_msg),
                                                                reasoning_content=full_thinking_text,
                                                                token_usage=token_usage)

    def generate_recommend_questions_task(self, _session: Session):

        # get schema
        if self.ds and not self.chat_question.db_schema:
            self.chat_question.db_schema, tables = self.out_ds_instance.get_db_schema(
                self.ds.id, self.chat_question.question) if self.out_ds_instance else get_table_schema(
                session=_session,
                current_user=self.current_user, ds=self.ds,
                question=self.chat_question.question,
                embedding=False)

            # Get sample data for all tables
            # if not self.out_ds_instance:
            #     self.chat_question.sample_data = get_tables_sample_data(
            #         session=_session,
            #         current_user=self.current_user,
            #         ds=self.ds)

        guess_msg: List[Union[BaseMessage, dict[str, Any]]] = []
        guess_msg.append(SystemPromptMessage(content=self.chat_question.guess_sys_question(self.articles_number)))

        old_questions = list(map(lambda q: q.strip(), get_old_questions(
            _session,
            self.record.datasource,
            self.current_user,
        )))
        guess_msg.append(
            HumanMessage(content=self.chat_question.guess_user_question(orjson.dumps(old_questions).decode())))

        self.current_logs[OperationEnum.GENERATE_RECOMMENDED_QUESTIONS] = start_log(session=_session,
                                                                                    ai_modal_id=self.chat_question.ai_modal_id,
                                                                                    ai_modal_name=self.chat_question.ai_modal_name,
                                                                                    operate=OperationEnum.GENERATE_RECOMMENDED_QUESTIONS,
                                                                                    record_id=self.record.id,
                                                                                    full_message=_serialize_prompt_messages(guess_msg))
        full_thinking_text = ''
        full_guess_text = ''
        token_usage = {}
        res = process_stream(self.llm.stream(guess_msg), token_usage)
        for chunk in res:
            if chunk.get('content'):
                full_guess_text += chunk.get('content')
            if chunk.get('reasoning_content'):
                full_thinking_text += chunk.get('reasoning_content')
            yield chunk

        guess_msg.append(AIMessage(full_guess_text))

        self.current_logs[OperationEnum.GENERATE_RECOMMENDED_QUESTIONS] = end_log(session=_session,
                                                                                  log=self.current_logs[
                                                                                      OperationEnum.GENERATE_RECOMMENDED_QUESTIONS],
                                                                                  full_message=_serialize_prompt_messages(guess_msg),
                                                                                  reasoning_content=full_thinking_text,
                                                                                  token_usage=token_usage)
        self.record = save_recommend_question_answer(session=_session, record_id=self.record.id,
                                                     answer={'content': full_guess_text},
                                                     articles_number=self.articles_number)

        yield {'recommended_question': self.record.recommended_question}

    def select_datasource(self, _session: Session):
        datasource_msg: List[Union[BaseMessage, dict[str, Any]]] = []
        datasource_msg.append(SystemPromptMessage(self.chat_question.datasource_sys_question()))
        if self.current_assistant and self.current_assistant.type != 4:
            _ds_list = get_assistant_ds(session=_session, llm_service=self)
        else:
            datasource_list = get_datasource_list(session=_session, user=self.current_user)
            _ds_list = [
                {
                    "id": ds.id,
                    "name": ds.name,
                    "description": ds.description
                }
                for ds in datasource_list
            ]
        if not _ds_list:
            raise SingleMessageError('当前没有可用项目，请联系管理员创建或分配项目')
        ignore_auto_select = _ds_list and len(_ds_list) == 1
        # ignore auto select ds

        full_thinking_text = ''
        full_text = ''
        if not ignore_auto_select:
            if settings.TABLE_EMBEDDING_ENABLED and (
                    not self.current_assistant or (self.current_assistant and self.current_assistant.type != 1)):
                _ds_list = get_ds_embedding(_session, self.current_user, _ds_list, self.out_ds_instance,
                                            self.chat_question.question, self.current_assistant)
                # yield {'content': '{"id":' + str(ds.get('id')) + '}'}

            _ds_list_dict = []
            for _ds in _ds_list:
                _ds_list_dict.append(_ds)
            datasource_msg.append(
                HumanMessage(self.chat_question.datasource_user_question(orjson.dumps(_ds_list_dict).decode())))

            self.current_logs[OperationEnum.CHOOSE_DATASOURCE] = start_log(session=_session,
                                                                           ai_modal_id=self.chat_question.ai_modal_id,
                                                                           ai_modal_name=self.chat_question.ai_modal_name,
                                                                           operate=OperationEnum.CHOOSE_DATASOURCE,
                                                                           record_id=self.record.id,
                                                                           full_message=_serialize_prompt_messages(datasource_msg))

            token_usage = {}
            res = process_stream(self.llm.stream(datasource_msg), token_usage)
            for chunk in res:
                if chunk.get('content'):
                    full_text += chunk.get('content')
                if chunk.get('reasoning_content'):
                    full_thinking_text += chunk.get('reasoning_content')
                yield chunk
            datasource_msg.append(AIMessage(full_text))

            self.current_logs[OperationEnum.CHOOSE_DATASOURCE] = end_log(session=_session,
                                                                         log=self.current_logs[
                                                                             OperationEnum.CHOOSE_DATASOURCE],
                                                                         full_message=_serialize_prompt_messages(datasource_msg),
                                                                         reasoning_content=full_thinking_text,
                                                                         token_usage=token_usage)

            json_str = extract_nested_json(full_text)
            if json_str is None:
                raise SingleMessageError(f'无法从模型返回中识别项目：{full_text}')
            ds = orjson.loads(json_str)

        _error: Exception | None = None
        _datasource: int | None = None
        _engine_type: str | None = None
        try:
            data: dict = _ds_list[0] if ignore_auto_select else ds

            if data.get('id') and data.get('id') != 0:
                _datasource = data['id']
                _chat = _session.get(Chat, self.record.chat_id)
                _chat.datasource = _datasource
                if self.current_assistant and self.current_assistant.type in dynamic_ds_types:
                    _ds = self.out_ds_instance.get_ds(data['id'])
                    self.ds = _ds
                    self.chat_question.engine = _ds.type + get_version(self.ds)

                    _engine_type = self.chat_question.engine
                    _chat.engine_type = _ds.type
                else:
                    _ds = _session.get(CoreDatasource, _datasource)
                    if not _ds:
                        missing_datasource = _datasource
                        _datasource = None
                        raise SingleMessageError(f"项目 {missing_datasource} 不存在或连接配置不可用")
                    if not has_datasource_access(_session, self.current_user, _datasource):
                        forbidden_datasource = _datasource
                        _datasource = None
                        raise SingleMessageError(f"当前用户无权访问项目 {forbidden_datasource}")
                    self.ds = CoreDatasource(**_ds.model_dump())
                    self.chat_question.engine = (_ds.type_name if _ds.type != 'excel' else 'PostgreSQL') + get_version(
                        self.ds)

                    _engine_type = self.chat_question.engine
                    _chat.engine_type = _ds.type_name
                # save chat
                with _session.begin_nested():
                    # 为了能继续记日志，先单独处理下事务
                    try:
                        _session.add(_chat)
                        _session.flush()
                        _session.refresh(_chat)
                        _session.commit()
                    except Exception as e:
                        _session.rollback()
                        raise e

            elif data['fail']:
                raise SingleMessageError(data['fail'])
            else:
                raise SingleMessageError('当前没有可用项目，请联系管理员创建或分配项目')

        except Exception as e:
            _error = e

        if not ignore_auto_select and not settings.TABLE_EMBEDDING_ENABLED:
            self.record = save_select_datasource_answer(session=_session, record_id=self.record.id,
                                                        answer=orjson.dumps({'content': full_text}).decode(),
                                                        datasource=_datasource,
                                                        engine_type=_engine_type)
        if self.ds:
            ds_id = self.ds.id if isinstance(self.ds, CoreDatasource) else None

            self.load_data_skills(_session, ds_id, CustomPromptTargetScopeEnum.SMART_QA)

            self.filter_custom_prompts(_session, CustomPromptTypeEnum.GENERATE_SQL, ds_id)

            self.load_tracking_config(_session)

            self.init_messages(_session)

        if _error:
            raise _error

    def generate_sql(self, _session: Session):
        # append current question
        self.sql_message.append(HumanMessage(
            self.chat_question.sql_user_question(current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                                 change_title=self.change_title)))

        self.current_logs[OperationEnum.GENERATE_SQL] = start_log(session=_session,
                                                                  ai_modal_id=self.chat_question.ai_modal_id,
                                                                  ai_modal_name=self.chat_question.ai_modal_name,
                                                                  operate=OperationEnum.GENERATE_SQL,
                                                                  record_id=self.record.id,
                                                                  full_message=_serialize_prompt_messages(self.sql_message))
        full_thinking_text = ''
        full_sql_text = ''
        token_usage = {}
        res = process_stream(self.llm.stream(self.sql_message), token_usage)
        for chunk in res:
            if chunk.get('content'):
                full_sql_text += chunk.get('content')
            if chunk.get('reasoning_content'):
                full_thinking_text += chunk.get('reasoning_content')
            yield chunk

        self.sql_message.append(AIMessage(full_sql_text))

        self.current_logs[OperationEnum.GENERATE_SQL] = end_log(session=_session,
                                                                log=self.current_logs[OperationEnum.GENERATE_SQL],
                                                                full_message=_serialize_prompt_messages(self.sql_message),
                                                                reasoning_content=full_thinking_text,
                                                                token_usage=token_usage)
        self.record = save_sql_answer(session=_session, record_id=self.record.id,
                                      answer=orjson.dumps({'content': full_sql_text}).decode())

    def generate_with_sub_sql(self, session: Session, sql, sub_mappings: list):
        sub_query = json.dumps(sub_mappings, ensure_ascii=False)
        self.chat_question.sql = sql
        self.chat_question.sub_query = sub_query
        dynamic_sql_msg: List[Union[BaseMessage, dict[str, Any]]] = []
        dynamic_sql_msg.append(SystemPromptMessage(content=self.chat_question.dynamic_sys_question()))
        dynamic_sql_msg.append(HumanMessage(content=self.chat_question.dynamic_user_question()))

        self.current_logs[OperationEnum.GENERATE_DYNAMIC_SQL] = start_log(session=session,
                                                                          ai_modal_id=self.chat_question.ai_modal_id,
                                                                          ai_modal_name=self.chat_question.ai_modal_name,
                                                                          operate=OperationEnum.GENERATE_DYNAMIC_SQL,
                                                                          record_id=self.record.id,
                                                                          full_message=_serialize_prompt_messages(dynamic_sql_msg))

        full_thinking_text = ''
        full_dynamic_text = ''
        token_usage = {}
        res = process_stream(self.llm.stream(dynamic_sql_msg), token_usage)
        for chunk in res:
            if chunk.get('content'):
                full_dynamic_text += chunk.get('content')
            if chunk.get('reasoning_content'):
                full_thinking_text += chunk.get('reasoning_content')

        dynamic_sql_msg.append(AIMessage(full_dynamic_text))

        self.current_logs[OperationEnum.GENERATE_DYNAMIC_SQL] = end_log(session=session,
                                                                        log=self.current_logs[
                                                                            OperationEnum.GENERATE_DYNAMIC_SQL],
                                                                        full_message=_serialize_prompt_messages(dynamic_sql_msg),
                                                                        reasoning_content=full_thinking_text,
                                                                        token_usage=token_usage)

        AppLogUtil.info(full_dynamic_text)
        return full_dynamic_text

    def generate_assistant_dynamic_sql(self, _session: Session, sql, tables: List):
        ds: AssistantOutDsSchema = self.ds
        sub_query = []
        result_dict = {}
        for table in ds.tables:
            if table.name in tables and table.sql:
                # sub_query.append({"table": table.name, "query": table.sql})
                result_dict[table.name] = table.sql
                sub_query.append({"table": table.name, "query": f'{dynamic_subsql_prefix}{table.name}'})
        if not sub_query:
            return None
        temp_sql_text = self.generate_with_sub_sql(session=_session, sql=sql, sub_mappings=sub_query)
        result_dict[APP_TEMP_SQL_TEXT_KEY] = temp_sql_text
        return result_dict

    def build_table_filter(self, session: Session, sql: str, filters: list):
        filter = json.dumps(filters, ensure_ascii=False)
        self.chat_question.sql = sql
        self.chat_question.filter = filter
        permission_sql_msg: List[Union[BaseMessage, dict[str, Any]]] = []
        permission_sql_msg.append(SystemPromptMessage(content=self.chat_question.filter_sys_question()))
        permission_sql_msg.append(HumanMessage(content=self.chat_question.filter_user_question()))

        self.current_logs[OperationEnum.GENERATE_SQL_WITH_PERMISSIONS] = start_log(session=session,
                                                                                   ai_modal_id=self.chat_question.ai_modal_id,
                                                                                   ai_modal_name=self.chat_question.ai_modal_name,
                                                                                   operate=OperationEnum.GENERATE_SQL_WITH_PERMISSIONS,
                                                                                   record_id=self.record.id,
                                                                                   full_message=_serialize_prompt_messages(permission_sql_msg))
        full_thinking_text = ''
        full_filter_text = ''
        token_usage = {}
        res = process_stream(self.llm.stream(permission_sql_msg), token_usage)
        for chunk in res:
            if chunk.get('content'):
                full_filter_text += chunk.get('content')
            if chunk.get('reasoning_content'):
                full_thinking_text += chunk.get('reasoning_content')

        permission_sql_msg.append(AIMessage(full_filter_text))

        self.current_logs[OperationEnum.GENERATE_SQL_WITH_PERMISSIONS] = end_log(session=session,
                                                                                 log=self.current_logs[
                                                                                     OperationEnum.GENERATE_SQL_WITH_PERMISSIONS],
                                                                                 full_message=_serialize_prompt_messages(permission_sql_msg),
                                                                                 reasoning_content=full_thinking_text,
                                                                                 token_usage=token_usage)

        AppLogUtil.info(full_filter_text)
        return full_filter_text

    def generate_filter(self, _session: Session, sql: str, tables: List):
        filters = get_row_permission_filters(session=_session, current_user=self.current_user, ds=self.ds,
                                             tables=tables)
        if not filters:
            return None
        return self.build_table_filter(session=_session, sql=sql, filters=filters)

    def generate_assistant_filter(self, _session: Session, sql, tables: List):
        ds: AssistantOutDsSchema = self.ds
        filters = []
        for table in ds.tables:
            if table.name in tables and table.rule:
                filters.append({"table": table.name, "filter": table.rule})
        if not filters:
            return None
        return self.build_table_filter(session=_session, sql=sql, filters=filters)

    def generate_chart(self, _session: Session, chart_type: Optional[str] = '', schema: Optional[str] = ''):
        # append current question
        self.chart_message.append(HumanMessage(self.chat_question.chart_user_question(chart_type, schema)))

        self.current_logs[OperationEnum.GENERATE_CHART] = start_log(session=_session,
                                                                    ai_modal_id=self.chat_question.ai_modal_id,
                                                                    ai_modal_name=self.chat_question.ai_modal_name,
                                                                    operate=OperationEnum.GENERATE_CHART,
                                                                    record_id=self.record.id,
                                                                    full_message=_serialize_prompt_messages(self.chart_message))
        full_thinking_text = ''
        full_chart_text = ''
        token_usage = {}
        res = process_stream(self.llm.stream(self.chart_message), token_usage)
        for chunk in res:
            if chunk.get('content'):
                full_chart_text += chunk.get('content')
            if chunk.get('reasoning_content'):
                full_thinking_text += chunk.get('reasoning_content')
            yield chunk

        self.chart_message.append(AIMessage(full_chart_text))

        self.record = save_chart_answer(session=_session, record_id=self.record.id,
                                        answer=orjson.dumps({'content': full_chart_text}).decode())
        self.current_logs[OperationEnum.GENERATE_CHART] = end_log(session=_session,
                                                                  log=self.current_logs[OperationEnum.GENERATE_CHART],
                                                                  full_message=_serialize_prompt_messages(self.chart_message),
                                                                  reasoning_content=full_thinking_text,
                                                                  token_usage=token_usage)

    def check_sql(self, session: Session, res: str, operate: OperationEnum) -> tuple[str, Optional[list]]:
        json_str = extract_nested_json(res)

        log = self.current_logs[operate]

        if json_str is None:
            trigger_log_error(session, log)
            raise SingleMessageError(orjson.dumps({'message': 'SQL answer is not a valid json object',
                                                   'traceback': "SQL answer is not a valid json object:\n" + res}).decode())
        sql: str
        data: dict
        try:
            data = orjson.loads(json_str)

            if data['success']:
                sql = data['sql']
            else:
                message = data['message']
                raise SingleMessageError(message)
        except SingleMessageError as e:
            trigger_log_error(session, log)
            raise e
        except Exception:
            trigger_log_error(session, log)
            raise SingleMessageError(orjson.dumps({'message': 'Cannot parse sql from answer',
                                                   'traceback': "Cannot parse sql from answer:\n" + res}).decode())

        if sql.strip() == '':
            trigger_log_error(session, log)
            raise SingleMessageError("SQL query is empty")
        return sql, data.get('tables')

    @staticmethod
    def get_chart_type_from_sql_answer(res: str) -> Optional[str]:
        json_str = extract_nested_json(res)
        if json_str is None:
            return None

        chart_type: Optional[str]
        data: dict
        try:
            data = orjson.loads(json_str)

            if data['success']:
                chart_type = data['chart-type']
            else:
                return None
        except Exception:
            return None

        return chart_type

    @staticmethod
    def get_brief_from_sql_answer(res: str) -> Optional[str]:
        json_str = extract_nested_json(res)
        if json_str is None:
            return None

        brief: Optional[str]
        data: dict
        try:
            data = orjson.loads(json_str)

            if data['success']:
                brief = data['brief']
            else:
                return None
        except Exception:
            return None

        return brief

    def check_save_sql(self, session: Session, res: str, operate: OperationEnum) -> str:
        sql, *_ = self.check_sql(session=session, res=res, operate=operate)
        save_sql(session=session, sql=sql, record_id=self.record.id)

        self.chat_question.sql = sql

        return sql

    def save_checked_sql(self, session: Session, sql: str) -> str:
        save_sql(session=session, sql=sql, record_id=self.record.id)
        self.chat_question.sql = sql
        return sql

    def check_save_chart(
        self,
        session: Session,
        res: str,
        result: Optional[dict[str, Any]] = None,
    ) -> Dict[str, Any]:

        json_str = extract_nested_json(res)
        if json_str is None:
            raise SingleMessageError(orjson.dumps({'message': 'Cannot parse chart config from answer',
                                                   'traceback': "Cannot parse chart config from answer:\n" + res}).decode())
        data: dict

        chart: Dict[str, Any] = {}
        message = ''
        error = False

        try:
            data = orjson.loads(json_str)
            if data['type'] and data['type'] != 'error':
                chart = _sanitize_chart_bindings(data)
            elif data['type'] == 'error':
                message = data['reason']
                error = True
            else:
                raise Exception('Chart is empty')
        except Exception:
            error = True
            message = orjson.dumps({'message': 'Cannot parse chart config from answer',
                                    'traceback': "Cannot parse chart config from answer:\n" + res}).decode()

        if error:
            raise SingleMessageError(message)

        if result:
            chart = _ensure_chart_covers_metric_fields(
                chart,
                result.get("fields"),
                result.get("data"),
            )

        save_chart(session=session, chart=orjson.dumps(chart).decode(), record_id=self.record.id)

        return chart

    def check_save_predict_data(self, session: Session, res: str) -> bool:

        json_str = extract_nested_json(res)

        if not json_str:
            json_str = ''

        save_predict_data(session=session, record_id=self.record.id, data=json_str)

        if json_str == '':
            return False

        return True

    def save_error(self, session: Session, message: str):
        return save_error_message(session=session, record_id=self.record.id, message=message)

    def save_sql_data(self, session: Session, data_obj: Dict[str, Any]):
        try:
            data_result = data_obj.get('data')
            limit = 1000
            if getattr(self.ds, "id", None) is not None:
                data_obj['datasource'] = self.ds.id
            if data_result:
                data_result = prepare_for_orjson(data_result)
                if data_result and len(data_result) > limit and self.enable_sql_row_limit:
                    data_obj['data'] = data_result[:limit]
                    data_obj['limit'] = limit
                else:
                    data_obj['data'] = data_result
            return save_sql_exec_data(session=session, record_id=self.record.id,
                                      data=orjson.dumps(data_obj).decode())
        except Exception as e:
            raise e

    def save_permission_denied_data(self, session: Session) -> dict[str, Any]:
        data_obj = permission_denied_result(PERMISSION_DENIED_RESULT_MESSAGE)
        self.save_sql_data(session=session, data_obj=data_obj)
        return data_obj

    def finish(self, session: Session):
        return finish_record(session=session, record_id=self.record.id)

    def execute_sql(
            self,
            session: Session,
            sql: str,
            scope_sql: str | None = None,
            scope_allowed_tables: list[str] | set[str] | None = None,
    ):
        """Execute SQL query

        Args:
            ds: Data source instance
            sql: SQL query statement

        Returns:
            Query results
        """
        AppLogUtil.info(f"Executing SQL on ds_id {self.ds.id}: {sql}")
        try:
            if isinstance(self.ds, CoreDatasource):
                return execute_user_analysis_query_or_raise(
                    session=session,
                    current_user=self.current_user,
                    datasource=self.ds,
                    sql=sql,
                    allowed_tables=self.table_name_list,
                    origin_column=True,
                ).result
            return execute_external_user_query_or_raise(
                datasource=self.ds,
                sql=sql,
                allowed_tables=scope_allowed_tables or self.table_name_list,
                scope_sql=scope_sql or self.chat_question.sql,
                origin_column=True,
            ).result
        except Exception as e:
            if isinstance(e, ParseSQLResultError):
                raise e
            else:
                err = traceback.format_exc(limit=1, chain=True)
                raise AppDBError(err)

    def pop_chunk(self):
        try:
            chunk = self.chunk_list.pop(0)
            return chunk
        except IndexError:
            return None

    def await_result(self):
        idle_rounds = 0
        max_idle_rounds = max(1, settings.LLM_REQUEST_TIMEOUT * 2)
        while self.is_running():
            emitted = False
            while True:
                chunk = self.pop_chunk()
                if chunk is not None:
                    emitted = True
                    yield chunk
                else:
                    break
            if emitted:
                idle_rounds = 0
            else:
                idle_rounds += 1
                if idle_rounds >= max_idle_rounds:
                    AppLogUtil.error(
                        f"LLM stream idle timeout after {settings.LLM_REQUEST_TIMEOUT}s for record {self.record.id}"
                    )
                    try:
                        self.future.cancel()
                    except Exception:
                        pass
                    yield 'data:' + orjson.dumps({
                        'content': 'LLM 请求超时，当前模型未在限定时间内返回内容，请检查模型服务或稍后重试。',
                        'type': 'error'
                    }).decode() + '\n\n'
                    return
        while True:
            chunk = self.pop_chunk()
            if chunk is None:
                break
            yield chunk

    def run_task_async(self, in_chat: bool = True, stream: bool = True,
                       finish_step: ChatFinishStep = ChatFinishStep.GENERATE_CHART, return_img: bool = True):
        if in_chat:
            stream = True
        self.future = executor.submit(self.run_task_cache, in_chat, stream, finish_step, return_img)

    def run_task_cache(self, in_chat: bool = True, stream: bool = True,
                       finish_step: ChatFinishStep = ChatFinishStep.GENERATE_CHART, return_img: bool = True):
        for chunk in self.run_task(in_chat, stream, finish_step, return_img):
            self.chunk_list.append(chunk)

    def run_task(self, in_chat: bool = True, stream: bool = True,
                 finish_step: ChatFinishStep = ChatFinishStep.GENERATE_CHART, return_img: bool = True):
        json_result: Dict[str, Any] = {'success': True}
        _session = None
        try:
            _session = session_maker()
            if self.ds:
                ds_id = self.ds.id if isinstance(self.ds, CoreDatasource) else None

                self.load_data_skills(_session, ds_id, CustomPromptTargetScopeEnum.SMART_QA)

                self.filter_custom_prompts(_session, CustomPromptTypeEnum.GENERATE_SQL, ds_id)

                self.load_tracking_config(_session)

                self.init_messages(_session)

            # return id
            if in_chat:
                yield 'data:' + orjson.dumps({'type': 'id', 'id': self.get_record().id}).decode() + '\n\n'
                if self.get_record().regenerate_record_id:
                    yield 'data:' + orjson.dumps({'type': 'regenerate_record_id',
                                                  'regenerate_record_id': self.get_record().regenerate_record_id}).decode() + '\n\n'
                yield 'data:' + orjson.dumps(
                    {'type': 'question', 'question': self.get_record().question}).decode() + '\n\n'
            else:
                if stream:
                    yield '> ' + self.trans('i18n_chat.record_id_in_mcp') + str(self.get_record().id) + '\n'
                    yield '> ' + self.get_record().question + '\n\n'
            if not stream:
                json_result['record_id'] = self.get_record().id

                # select datasource if datasource is none
            if not self.ds:
                ds_res = self.select_datasource(_session)

                for chunk in ds_res:
                    AppLogUtil.info(chunk)
                    if in_chat:
                        yield 'data:' + orjson.dumps(
                            {'content': chunk.get('content'), 'reasoning_content': chunk.get('reasoning_content'),
                             'type': 'datasource-result'}).decode() + '\n\n'
                if in_chat:
                    yield 'data:' + orjson.dumps({'id': self.ds.id, 'datasource_name': self.ds.name,
                                                  'engine_type': self.ds.type_name or self.ds.type,
                                                  'type': 'datasource'}).decode() + '\n\n'

            else:
                self.validate_history_ds(_session)

            # check connection
            connected = check_connection(ds=self.ds, trans=None)
            if not connected:
                raise AppDBConnectionError('Connect DB failed')

            # generate sql
            sql_res = self.generate_sql(_session)
            full_sql_text = ''
            for chunk in sql_res:
                full_sql_text += chunk.get('content')
                if in_chat:
                    yield 'data:' + orjson.dumps(
                        {'content': chunk.get('content'), 'reasoning_content': chunk.get('reasoning_content'),
                         'type': 'sql-result'}).decode() + '\n\n'
            if in_chat:
                yield 'data:' + orjson.dumps({'type': 'info', 'msg': 'sql generated'}).decode() + '\n\n'
            # filter sql
            AppLogUtil.info(full_sql_text)

            chart_type = self.get_chart_type_from_sql_answer(full_sql_text)

            # return title
            if self.change_title:
                llm_brief = self.get_brief_from_sql_answer(full_sql_text)
                llm_brief_generated = bool(llm_brief)
                if llm_brief_generated or (self.chat_question.question and self.chat_question.question.strip() != ''):
                    save_brief = llm_brief if (llm_brief and llm_brief != '') else self.chat_question.question.strip()[
                                                                                   :20]
                    brief = rename_chat(session=_session,
                                        rename_object=RenameChat(id=self.get_record().chat_id,
                                                                 brief=save_brief, brief_generate=llm_brief_generated))
                    if in_chat:
                        yield 'data:' + orjson.dumps({'type': 'brief', 'brief': brief}).decode() + '\n\n'
                    if not stream:
                        json_result['title'] = brief

            use_dynamic_ds: bool = self.current_assistant and self.current_assistant.type in dynamic_ds_types
            dynamic_sql_result = None
            app_temp_sql_text = None
            assistant_dynamic_sql = None
            # row permission

            sql_operate = OperationEnum.GENERATE_SQL
            sql, tables = self.check_sql(session=_session, res=full_sql_text, operate=sql_operate)

            try:
                if use_dynamic_ds:
                    dynamic_sql_result = self.generate_assistant_dynamic_sql(_session, sql, tables)
                    app_temp_sql_text = _get_temp_sql_text(dynamic_sql_result)
                    if dynamic_sql_result and app_temp_sql_text:
                        sql_operate = OperationEnum.GENERATE_DYNAMIC_SQL
                        assistant_dynamic_sql = self.check_save_sql(
                            session=_session,
                            res=app_temp_sql_text,
                            operate=sql_operate,
                        )
                    else:
                        sql = self.check_save_sql(session=_session, res=full_sql_text, operate=sql_operate)
                else:
                    checked_sql, _actual_tables = validate_user_query_sql_or_raise(
                        session=_session,
                        current_user=self.current_user,
                        datasource=self.ds,
                        sql=sql,
                        allowed_tables=self.table_name_list,
                    )
                    sql = self.save_checked_sql(session=_session, sql=checked_sql)
            except Exception as permission_error:
                if not looks_like_permission_scope_error(str(permission_error)):
                    raise
                sql = self.save_checked_sql(session=_session, sql=sql)
                failed_result = self.save_permission_denied_data(session=_session)
                format_sql = sqlparse.format(sql, reindent=True)
                if in_chat:
                    yield 'data:' + orjson.dumps({'content': format_sql, 'type': 'sql'}).decode() + '\n\n'
                    yield 'data:' + orjson.dumps({
                        'content': 'execute-failed',
                        'type': 'sql-data',
                        'status': 'failed',
                        'error_type': PERMISSION_DENIED_ERROR_TYPE,
                        'message': PERMISSION_DENIED_RESULT_MESSAGE,
                    }).decode() + '\n\n'
                    yield 'data:' + orjson.dumps({'type': 'finish'}).decode() + '\n\n'
                else:
                    if stream:
                        yield f'```sql\n{format_sql}\n```\n\n'
                        yield f'> {PERMISSION_DENIED_RESULT_MESSAGE}\n'
                    else:
                        json_result['success'] = False
                        json_result['sql'] = sql
                        json_result['data'] = failed_result
                        json_result['message'] = PERMISSION_DENIED_RESULT_MESSAGE
                        yield json_result
                return

            AppLogUtil.info('sql: ' + sql)

            if not stream:
                json_result['sql'] = sql

            format_sql = sqlparse.format(sql, reindent=True)
            if in_chat:
                yield 'data:' + orjson.dumps({'content': format_sql, 'type': 'sql'}).decode() + '\n\n'
            else:
                if stream:
                    yield f'```sql\n{format_sql}\n```\n\n'

            # execute sql
            real_execute_sql = sql
            execute_scope_sql = sql
            execute_allowed_tables = self.table_name_list
            if app_temp_sql_text and assistant_dynamic_sql:
                execute_scope_sql = assistant_dynamic_sql
                execute_allowed_tables = [
                    f"app_dynamic_temp_table_{origin_table}"
                    for origin_table in dynamic_sql_result
                    if origin_table != APP_TEMP_SQL_TEXT_KEY
                ]
                _remove_temp_sql_text(dynamic_sql_result)
                for origin_table, subsql in dynamic_sql_result.items():
                    assistant_dynamic_sql = assistant_dynamic_sql.replace(f'{dynamic_subsql_prefix}{origin_table}',
                                                                          subsql)
                real_execute_sql = assistant_dynamic_sql

            if finish_step.value <= ChatFinishStep.GENERATE_SQL.value:
                if in_chat:
                    yield 'data:' + orjson.dumps({'type': 'finish'}).decode() + '\n\n'
                if not stream:
                    yield json_result
                return

            self.current_logs[OperationEnum.EXECUTE_SQL] = start_log(session=_session,
                                                                     operate=OperationEnum.EXECUTE_SQL,
                                                                     record_id=self.record.id, local_operation=True)
            try:
                result = self.execute_sql(
                    session=_session,
                    sql=real_execute_sql,
                    scope_sql=execute_scope_sql,
                    scope_allowed_tables=execute_allowed_tables,
                )
            except Exception as execute_error:
                if not looks_like_permission_scope_error(str(execute_error)):
                    raise
                trigger_log_error(_session, self.current_logs[OperationEnum.EXECUTE_SQL])
                failed_result = self.save_permission_denied_data(session=_session)
                if in_chat:
                    yield 'data:' + orjson.dumps({
                        'content': 'execute-failed',
                        'type': 'sql-data',
                        'status': 'failed',
                        'error_type': PERMISSION_DENIED_ERROR_TYPE,
                        'message': PERMISSION_DENIED_RESULT_MESSAGE,
                        'reason': PERMISSION_DENIED_RESULT_MESSAGE,
                    }).decode() + '\n\n'
                    yield 'data:' + orjson.dumps({'type': 'finish'}).decode() + '\n\n'
                else:
                    if stream:
                        yield f'> {PERMISSION_DENIED_RESULT_MESSAGE}\n'
                    else:
                        json_result['success'] = False
                        json_result['sql'] = sql
                        json_result['data'] = failed_result
                        json_result['message'] = PERMISSION_DENIED_RESULT_MESSAGE
                        yield json_result
                return
            self.current_logs[OperationEnum.EXECUTE_SQL] = end_log(session=_session,
                                                                   log=self.current_logs[OperationEnum.EXECUTE_SQL],
                                                                   full_message={'sql': real_execute_sql,
                                                                                 'count': len(result.get('data'))})

            _data = DataFormat.convert_large_numbers_in_object_array(result.get('data'))
            _data = DataFormat.normalize_qualified_sql_column_keys_in_object_array(_data)
            result["data"] = _data

            self.save_sql_data(session=_session, data_obj=result)
            if in_chat:
                yield 'data:' + orjson.dumps({'content': 'execute-success', 'type': 'sql-data'}).decode() + '\n\n'
            if not stream:
                json_result['data'] = get_chat_chart_data(_session, self.record.id)

            if finish_step.value <= ChatFinishStep.QUERY_DATA.value:
                if stream:
                    if in_chat:
                        yield 'data:' + orjson.dumps({'type': 'finish'}).decode() + '\n\n'
                    else:
                        _column_list = []
                        for field in result.get('fields'):
                            _column_list.append(AxisObj(name=field, value=field))

                        md_data, _fields_list = DataFormat.convert_object_array_for_pandas(_column_list,
                                                                                           result.get('data'))

                        # data, _fields_list, col_formats = self.format_pd_data(_column_list, result.get('data'))

                        if not _data or not _fields_list:
                            yield 'The SQL execution result is empty.\n\n'
                        else:
                            df = pd.DataFrame(_data, columns=_fields_list)
                            df_safe = DataFormat.safe_convert_to_string(df)
                            markdown_table = df_safe.to_markdown(index=False)
                            yield markdown_table + '\n\n'
                else:
                    yield json_result
                return

            # generate chart
            used_tables_schema, used_tables = self.out_ds_instance.get_db_schema(
                self.ds.id, self.chat_question.question, embedding=False,
                table_list=tables) if self.out_ds_instance else get_table_schema(
                session=_session,
                current_user=self.current_user,
                ds=self.ds,
                question=self.chat_question.question,
                embedding=False, table_list=tables)
            AppLogUtil.info('used_tables_schema: \n' + used_tables_schema)
            chart_res = self.generate_chart(_session, chart_type, used_tables_schema)
            full_chart_text = ''
            for chunk in chart_res:
                full_chart_text += chunk.get('content')
                if in_chat:
                    yield 'data:' + orjson.dumps(
                        {'content': chunk.get('content'), 'reasoning_content': chunk.get('reasoning_content'),
                         'type': 'chart-result'}).decode() + '\n\n'
            if in_chat:
                yield 'data:' + orjson.dumps({'type': 'info', 'msg': 'chart generated'}).decode() + '\n\n'

            # filter chart
            AppLogUtil.info(full_chart_text)
            chart = self.check_save_chart(session=_session, res=full_chart_text, result=result)
            AppLogUtil.info(chart)

            if not stream:
                json_result['chart'] = chart

            if in_chat:
                yield 'data:' + orjson.dumps(
                    {'content': orjson.dumps(chart).decode(), 'type': 'chart'}).decode() + '\n\n'
            else:
                if stream:
                    md_data, _fields_list = DataFormat.convert_data_fields_for_pandas(chart, result.get('fields'),
                                                                                      result.get('data'))
                    # data, _fields_list, col_formats = self.format_pd_data(_column_list, result.get('data'))

                    if not md_data or not _fields_list:
                        yield 'The SQL execution result is empty.\n\n'
                    else:
                        df = pd.DataFrame(md_data, columns=_fields_list)
                        df_safe = DataFormat.safe_convert_to_string(df)
                        markdown_table = df_safe.to_markdown(index=False)
                        yield markdown_table + '\n\n'

            if in_chat:
                yield 'data:' + orjson.dumps({'type': 'finish'}).decode() + '\n\n'
            else:
                # generate picture
                try:
                    if chart.get('type') != 'table' and return_img:
                        # yield '### generated chart picture\n\n'
                        self.current_logs[OperationEnum.GENERATE_PICTURE] = start_log(session=_session,
                                                                                      operate=OperationEnum.GENERATE_PICTURE,
                                                                                      record_id=self.record.id,
                                                                                      local_operation=True)
                        image_url, error = request_picture(self.record.chat_id, self.record.id, chart,
                                                           format_json_data(result))
                        AppLogUtil.info(image_url)
                        if stream:
                            yield f'![{chart.get("type")}]({image_url})'
                        else:
                            json_result['image_url'] = image_url
                        if error is not None:
                            raise error

                        self.current_logs[OperationEnum.GENERATE_PICTURE] = end_log(session=_session,
                                                                                    log=self.current_logs[
                                                                                        OperationEnum.GENERATE_PICTURE],
                                                                                    full_message=image_url)
                except Exception as e:
                    if stream:
                        if chart.get('type') != 'table':
                            yield 'generate or fetch chart picture error.\n\n'
                        raise e

            if not stream:
                yield json_result

        except Exception as e:
            traceback.print_exc()
            error_msg: str
            if isinstance(e, SingleMessageError):
                error_msg = str(e)
            elif isinstance(e, AppDBConnectionError):
                error_msg = orjson.dumps(
                    {'message': str(e), 'type': 'db-connection-err'}).decode()
            elif isinstance(e, AppDBError):
                error_msg = orjson.dumps(
                    {'message': 'Execute SQL Failed', 'traceback': str(e), 'type': 'exec-sql-err'}).decode()
            else:
                error_msg = orjson.dumps({'message': str(e), 'traceback': traceback.format_exc(limit=1)}).decode()
            if _session:
                self.save_error(session=_session, message=error_msg)
            if in_chat:
                yield 'data:' + orjson.dumps({'content': error_msg, 'type': 'error'}).decode() + '\n\n'
            else:
                if stream:
                    yield f'&#x274c; **ERROR:**\n'
                    yield f'> {error_msg}\n'
                else:
                    json_result['success'] = False
                    json_result['message'] = error_msg
                    yield json_result
        finally:
            self.finish(_session)
            session_maker.remove()

    def run_recommend_questions_task_async(self):
        self.future = executor.submit(self.run_recommend_questions_task_cache)

    def run_recommend_questions_task_cache(self):
        for chunk in self.run_recommend_questions_task():
            self.chunk_list.append(chunk)

    def run_recommend_questions_task(self):
        try:
            _session = session_maker()
            res = self.generate_recommend_questions_task(_session)

            for chunk in res:
                if chunk.get('recommended_question'):
                    yield 'data:' + orjson.dumps(
                        {'content': chunk.get('recommended_question'),
                         'type': 'recommended_question'}).decode() + '\n\n'
                else:
                    yield 'data:' + orjson.dumps(
                        {'content': chunk.get('content'), 'reasoning_content': chunk.get('reasoning_content'),
                         'type': 'recommended_question_result'}).decode() + '\n\n'
        except Exception:
            traceback.print_exc()
        finally:
            session_maker.remove()

    def run_analysis_or_predict_task_async(self, session: Session, action_type: str, base_record: ChatRecord,
                                           in_chat: bool = True, stream: bool = True):
        self.set_record(save_analysis_predict_record(session, base_record, action_type))
        self.future = executor.submit(self.run_analysis_or_predict_task_cache, action_type, in_chat, stream)

    def run_analysis_or_predict_task_cache(self, action_type: str, in_chat: bool = True, stream: bool = True):
        for chunk in self.run_analysis_or_predict_task(action_type, in_chat, stream):
            self.chunk_list.append(chunk)

    def run_analysis_or_predict_task(self, action_type: str, in_chat: bool = True, stream: bool = True):
        json_result: Dict[str, Any] = {'success': True}
        _session = None
        try:
            _session = session_maker()
            if in_chat:
                yield 'data:' + orjson.dumps({'type': 'id', 'id': self.get_record().id}).decode() + '\n\n'
            else:
                if stream:
                    yield '> ' + self.trans('i18n_chat.record_id_in_mcp') + str(self.get_record().id) + '\n'
                    yield '> ' + self.get_record().question + '\n\n'
            if not stream:
                json_result['record_id'] = self.get_record().id

            if action_type == 'analysis':
                # generate analysis
                analysis_res = self.generate_analysis(_session)
                full_text = ''
                for chunk in analysis_res:
                    full_text += chunk.get('content')
                    if in_chat:
                        yield 'data:' + orjson.dumps(
                            {'content': chunk.get('content'), 'reasoning_content': chunk.get('reasoning_content'),
                             'type': 'analysis-result'}).decode() + '\n\n'
                    else:
                        if stream:
                            yield chunk.get('content')
                if in_chat:
                    yield 'data:' + orjson.dumps({'type': 'info', 'msg': 'analysis generated'}).decode() + '\n\n'
                    yield 'data:' + orjson.dumps({'type': 'analysis_finish'}).decode() + '\n\n'
                else:
                    if stream:
                        yield '\n\n'
                if not stream:
                    json_result['content'] = full_text

            elif action_type == 'predict':
                # generate predict
                analysis_res = self.generate_predict(_session)
                full_text = ''
                for chunk in analysis_res:
                    full_text += chunk.get('content')
                    if in_chat:
                        yield 'data:' + orjson.dumps(
                            {'content': chunk.get('content'), 'reasoning_content': chunk.get('reasoning_content'),
                             'type': 'predict-result'}).decode() + '\n\n'
                if in_chat:
                    yield 'data:' + orjson.dumps({'type': 'info', 'msg': 'predict generated'}).decode() + '\n\n'

                has_data = self.check_save_predict_data(session=_session, res=full_text)
                if has_data:
                    if in_chat:
                        yield 'data:' + orjson.dumps({'type': 'predict-success'}).decode() + '\n\n'
                    else:
                        chart = get_chat_chart_config(_session, self.record.id)
                        origin_data = get_chat_chart_data(_session, self.record.id)
                        predict_data = get_chat_predict_data(_session, self.record.id)

                        if stream:
                            md_data, _fields_list = DataFormat.convert_data_fields_for_pandas(chart,
                                                                                              origin_data.get('fields'),
                                                                                              predict_data)
                            if not md_data or not _fields_list:
                                yield 'Predict data result is empty.\n\n'
                            else:
                                df = pd.DataFrame(md_data, columns=_fields_list)
                                df_safe = DataFormat.safe_convert_to_string(df)
                                markdown_table = df_safe.to_markdown(index=False)
                                yield markdown_table + '\n\n'

                        else:
                            json_result['origin_data'] = origin_data
                            json_result['predict_data'] = predict_data

                        # generate picture
                        try:
                            if chart.get('type') != 'table':
                                # yield '### generated chart picture\n\n'

                                _data = get_chat_chart_data(_session, self.record.id)
                                _data['data'] = _data.get('data') + predict_data

                                image_url, error = request_picture(self.record.chat_id, self.record.id, chart,
                                                                   format_json_data(_data))
                                AppLogUtil.info(image_url)
                                if stream:
                                    yield f'![{chart.get("type")}]({image_url})'
                                else:
                                    json_result['image_url'] = image_url
                                if error is not None:
                                    raise error
                        except Exception as e:
                            if stream:
                                if chart.get('type') != 'table':
                                    yield 'generate or fetch chart picture error.\n\n'
                                raise e
                else:
                    if in_chat:
                        yield 'data:' + orjson.dumps({'type': 'predict-failed'}).decode() + '\n\n'
                    else:
                        if stream:
                            yield full_text + '\n\n'
                    if not stream:
                        json_result['success'] = False
                        json_result['message'] = full_text
                if in_chat:
                    yield 'data:' + orjson.dumps({'type': 'predict_finish'}).decode() + '\n\n'

            self.finish(_session)

            if not stream:
                yield json_result
        except Exception as e:
            traceback.print_exc()
            error_msg: str
            if isinstance(e, SingleMessageError):
                error_msg = str(e)
            else:
                error_msg = orjson.dumps({'message': str(e), 'traceback': traceback.format_exc(limit=1)}).decode()
            if _session:
                self.save_error(session=_session, message=error_msg)
            if in_chat:
                yield 'data:' + orjson.dumps({'content': error_msg, 'type': 'error'}).decode() + '\n\n'
            else:
                if stream:
                    yield f'&#x274c; **ERROR:**\n'
                    yield f'> {error_msg}\n'
                else:
                    json_result['success'] = False
                    json_result['message'] = error_msg
                    yield json_result
        finally:
            # end
            session_maker.remove()

    def validate_history_ds(self, session: Session):
        _ds = self.ds
        if not self.current_assistant or self.current_assistant.type == 4:
            try:
                current_ds = session.get(CoreDatasource, _ds.id)
                if not current_ds:
                    raise SingleMessageError('chat.ds_is_invalid')
            except Exception:
                raise SingleMessageError("chat.ds_is_invalid")
        else:
            try:
                _ds_list: list[dict] = get_assistant_ds(session=session, llm_service=self)
                match_ds = any(item.get("id") == _ds.id for item in _ds_list)
                if not match_ds:
                    type = self.current_assistant.type
                    msg = f"[please check ds list and public ds list]" if type == 0 else f"[please check ds api]"
                    raise SingleMessageError(msg)
            except Exception as e:
                raise SingleMessageError(f"ds is invalid [{str(e)}]")


def execute_sql_with_db(db: SQLDatabase, sql: str) -> str:
    """Execute SQL query using SQLDatabase

    Args:
        db: SQLDatabase instance
        sql: SQL query statement

    Returns:
        str: Query results formatted as string
    """
    try:
        # Execute query
        result = db.run(sql)

        if not result:
            return "Query executed successfully but returned no results."

        # Format results
        return str(result)

    except Exception as e:
        error_msg = f"SQL execution failed: {str(e)}"
        AppLogUtil.exception(error_msg)
        raise RuntimeError(error_msg)


def format_chart_data_for_agent_prompt(data: dict[str, Any]) -> str:
    if isinstance(data, dict) and data.get("status") == "failed":
        payload = {
            "status": data.get("status"),
            "error_type": data.get("error_type"),
            "message": data.get("message"),
            "reason": data.get("reason") or data.get("message"),
            "warning": data.get("warning") or data.get("message"),
            "agent_guidance": data.get("agent_guidance") or PERMISSION_DENIED_AGENT_GUIDANCE,
        }
        return orjson.dumps(payload).decode()
    return orjson.dumps(data.get("data") if isinstance(data, dict) else []).decode()


def request_picture(chat_id: int, record_id: int, chart: dict, data: dict):
    file_name = f'c_{chat_id}_r_{record_id}'

    columns = chart.get('columns') if chart.get('columns') else []
    x = None
    y = None
    series = None
    multi_quota_fields = []
    multi_quota_name = None

    if chart.get('axis'):
        axis_data = chart.get('axis')
        x = axis_data.get('x')
        y = axis_data.get('y')
        series = axis_data.get('series')
        # 获取multi-quota字段列表
        if axis_data.get('multi-quota') and 'value' in axis_data.get('multi-quota'):
            multi_quota_fields = axis_data.get('multi-quota').get('value', [])
            multi_quota_name = axis_data.get('multi-quota').get('name') or '指标类型'

    axis = []
    for v in columns:
        axis.append({'name': v.get('name') or v.get('value'), 'value': v.get('value') or v.get('name')})
    if x:
        axis.append({'name': x.get('name') or x.get('value'), 'value': x.get('value') or x.get('name'), 'type': 'x'})
    if y:
        y_list = y if isinstance(y, list) else [y]

        for y_item in y_list:
            if isinstance(y_item, dict) and 'value' in y_item:
                y_obj = {
                    'name': y_item.get('name') or y_item.get('value'),
                    'value': y_item.get('value') or y_item.get('name'),
                    'type': 'y'
                }
                # 如果是multi-quota字段，添加标志
                if y_item.get('value') in multi_quota_fields:
                    y_obj['multi-quota'] = True
                axis.append(y_obj)
    if series:
        axis.append({'name': series.get('name') or series.get('value'), 'value': series.get('value') or series.get('name'), 'type': 'series'})
    if multi_quota_name:
        axis.append({'name': multi_quota_name, 'value': multi_quota_name, 'type': 'other-info'})

    request_obj = {
        "path": os.path.join(settings.MCP_IMAGE_PATH, file_name),
        "type": chart.get('type'),
        "data": orjson.dumps(data.get('data') if data.get('data') else []).decode(),
        "axis": orjson.dumps(axis).decode(),
    }

    _error = None
    try:
        requests.post(url=settings.MCP_IMAGE_HOST, json=request_obj, timeout=settings.SERVER_IMAGE_TIMEOUT)
    except Exception as e:
        _error = e

    request_path = urllib.parse.urljoin(settings.SERVER_IMAGE_HOST, f"{file_name}.png")

    return request_path, _error


def get_token_usage(chunk: BaseMessageChunk, token_usage: dict = None):
    try:
        if chunk.usage_metadata:
            if token_usage is None:
                token_usage = {}
            token_usage['input_tokens'] = chunk.usage_metadata.get('input_tokens')
            token_usage['output_tokens'] = chunk.usage_metadata.get('output_tokens')
            token_usage['total_tokens'] = chunk.usage_metadata.get('total_tokens')
    except Exception:
        pass


def process_stream(res: Iterator[BaseMessageChunk],
                   token_usage: Dict[str, Any] = None,
                   enable_tag_parsing: bool = settings.PARSE_REASONING_BLOCK_ENABLED,
                   start_tag: str = settings.DEFAULT_REASONING_CONTENT_START,
                   end_tag: str = settings.DEFAULT_REASONING_CONTENT_END
                   ):
    if token_usage is None:
        token_usage = {}
    in_thinking_block = False  # 标记是否在思考过程块中
    current_thinking = ''  # 当前收集的思考过程内容
    pending_start_tag = ''  # 用于缓存可能被截断的开始标签部分

    for chunk in res:
        AppLogUtil.info(chunk)
        reasoning_content_chunk = ''
        content = chunk.content
        output_content = ''  # 实际要输出的内容

        # 检查additional_kwargs中的reasoning_content
        if 'reasoning_content' in chunk.additional_kwargs:
            reasoning_content = chunk.additional_kwargs.get('reasoning_content', '')
            if reasoning_content is None:
                reasoning_content = ''

            # 累积additional_kwargs中的思考内容到current_thinking
            current_thinking += reasoning_content
            reasoning_content_chunk = reasoning_content

        # 只有当current_thinking不是空字符串时才跳过标签解析
        if not in_thinking_block and current_thinking.strip() != '':
            output_content = content  # 正常输出content
            yield {
                'content': output_content,
                'reasoning_content': reasoning_content_chunk
            }
            get_token_usage(chunk, token_usage)
            continue  # 跳过后续的标签解析逻辑

        # 如果没有有效的思考内容，并且启用了标签解析，才执行标签解析逻辑
        # 如果有缓存的开始标签部分，先拼接当前内容
        if pending_start_tag:
            content = pending_start_tag + content
            pending_start_tag = ''

        # 检查是否开始思考过程块（处理可能被截断的开始标签）
        if enable_tag_parsing and not in_thinking_block and start_tag:
            if start_tag in content:
                start_idx = content.index(start_tag)
                # 只有当开始标签前面没有其他文本时才认为是真正的思考块开始
                if start_idx == 0 or content[:start_idx].strip() == '':
                    # 完整标签存在且前面没有其他文本
                    output_content += content[:start_idx]  # 输出开始标签之前的内容
                    content = content[start_idx + len(start_tag):]  # 移除开始标签
                    in_thinking_block = True
                else:
                    # 开始标签前面有其他文本，不认为是思考块开始
                    output_content += content
                    content = ''
            else:
                # 检查是否可能有部分开始标签
                for i in range(1, len(start_tag)):
                    if content.endswith(start_tag[:i]):
                        # 只有当当前内容全是空白时才缓存部分标签
                        if content[:-i].strip() == '':
                            pending_start_tag = start_tag[:i]
                            content = content[:-i]  # 移除可能的部分标签
                            output_content += content
                            content = ''
                        break

        # 处理思考块内容
        if enable_tag_parsing and in_thinking_block and end_tag:
            if end_tag in content:
                # 找到结束标签
                end_idx = content.index(end_tag)
                current_thinking += content[:end_idx]  # 收集思考内容
                reasoning_content_chunk += current_thinking  # 添加到当前块的思考内容
                content = content[end_idx + len(end_tag):]  # 移除结束标签后的内容
                current_thinking = ''  # 重置当前思考内容
                in_thinking_block = False
                output_content += content  # 输出结束标签之后的内容
            else:
                # 在遇到结束标签前，持续收集思考内容
                current_thinking += content
                reasoning_content_chunk += content
                content = ''

        else:
            # 不在思考块中或标签解析未启用，正常输出
            output_content += content

        yield {
            'content': output_content,
            'reasoning_content': reasoning_content_chunk
        }
        get_token_usage(chunk, token_usage)


def get_lang_name(lang: str):
    if not lang:
        return '简体中文'
    normalized = lang.lower()
    if normalized.startswith('zh-tw'):
        return '繁体中文'
    if normalized.startswith('en'):
        return '英文'
    if normalized.startswith('ko'):
        return '韩语'
    return '简体中文'


def get_last_conversation_rounds(messages, rounds=settings.GENERATE_SQL_QUERY_HISTORY_ROUND_COUNT):
    """获取最后N轮对话，处理不完整对话的情况"""
    if not messages or rounds <= 0:
        return []

    # 找到所有用户消息的位置
    human_indices = []
    for index, msg in enumerate(messages):
        if msg.get('type') == 'human':
            human_indices.append(index)

    # 如果没有用户消息，返回空
    if not human_indices:
        return []

    # 计算从哪个索引开始
    if len(human_indices) <= rounds:
        # 如果用户消息数少于等于需要的轮数，从第一个用户消息开始
        start_index = human_indices[0]
    else:
        # 否则，从倒数第N个用户消息开始
        start_index = human_indices[-rounds]

    return messages[start_index:]
