"""
脚本说明：这个脚本定义聊天问数据和 Agent用到的数据表或数据对象，便于代码和数据库对齐。
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional, Any, Union

from fastapi import Body
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from pydantic import BaseModel
from sqlalchemy import Column, Integer, Text, BigInteger, DateTime, Identity, Boolean, Index
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import SQLModel, Field

from apps.db.constant import DB
from apps.template.filter.generator import get_permissions_template
from apps.template.generate_analysis.generator import get_analysis_template
from apps.template.generate_chart.generator import get_chart_template
from apps.template.generate_dynamic.generator import get_dynamic_template
from apps.template.generate_guess_question.generator import get_guess_question_template
from apps.template.generate_predict.generator import get_predict_template
from apps.template.generate_sql.generator import get_sql_template, get_sql_example_template
from apps.template.select_datasource.generator import get_datasource_template


def enum_values(enum_class: type[Enum]) -> list:
    """
    是什么：enum_values 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return [status.value for status in enum_class]


class TypeEnum(Enum):
    """
    类说明：TypeEnum 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    CHAT = "0"


#     待办：其他用法

class OperationEnum(Enum):
    """
    类说明：OperationEnum 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    GENERATE_SQL = '0'
    GENERATE_CHART = '1'
    ANALYSIS = '2'
    PREDICT_DATA = '3'
    GENERATE_RECOMMENDED_QUESTIONS = '4'
    GENERATE_SQL_WITH_PERMISSIONS = '5'
    CHOOSE_DATASOURCE = '6'
    GENERATE_DYNAMIC_SQL = '7'
    CHOOSE_TABLE = '8'
    FILTER_TERMS = '9'
    FILTER_SQL_EXAMPLE = '10'
    FILTER_CUSTOM_PROMPT = '11'
    EXECUTE_SQL = '12'
    GENERATE_PICTURE = '13'
    FILTER_DATA_SKILL = '14'


class ChatFinishStep(Enum):
    """
    类说明：ChatFinishStep 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    GENERATE_SQL = 1
    QUERY_DATA = 2
    GENERATE_CHART = 3


class QuickCommand(Enum):
    """
    类说明：QuickCommand 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    REGENERATE = '/regenerate'
    ANALYSIS = '/analysis'
    PREDICT_DATA = '/predict'


#     待办：选表 / 检查连接 / 生成描述

class ChatLog(SQLModel, table=True):
    """
    类说明：ChatLog 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "chat_log"
    __table_args__ = (
        Index("idx_chat_log_tenant_id", "tenant_id"),
    )
    id: Optional[int] = Field(sa_column=Column(BigInteger, Identity(always=True), primary_key=True))
    tenant_id: int = Field(default=1, sa_column=Column(BigInteger, nullable=False, server_default="1"))
    type: TypeEnum = Field(
        sa_column=Column(SQLAlchemyEnum(TypeEnum, native_enum=False, values_callable=enum_values, length=3)))
    operate: OperationEnum = Field(
        sa_column=Column(SQLAlchemyEnum(OperationEnum, native_enum=False, values_callable=enum_values, length=3)))
    pid: Optional[int] = Field(sa_column=Column(BigInteger, nullable=True))
    ai_modal_id: Optional[int] = Field(sa_column=Column(BigInteger))
    base_modal: Optional[str] = Field(max_length=255)
    messages: Optional[list[dict]] = Field(sa_column=Column(JSONB))
    reasoning_content: Optional[str | None] = Field(sa_column=Column(Text, nullable=True))
    start_time: datetime = Field(sa_column=Column(DateTime(timezone=False), nullable=True))
    finish_time: datetime = Field(sa_column=Column(DateTime(timezone=False), nullable=True))
    token_usage: Optional[dict | None | int] = Field(sa_column=Column(JSONB))
    local_operation: bool = Field(default=False)
    error: bool = Field(default=False)


class Chat(SQLModel, table=True):
    """
    类说明：Chat 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "chat"
    __table_args__ = (
        Index("idx_chat_tenant_id", "tenant_id"),
    )
    id: Optional[int] = Field(sa_column=Column(BigInteger, Identity(always=True), primary_key=True))
    tenant_id: int = Field(default=1, sa_column=Column(BigInteger, nullable=False, server_default="1"))
    create_time: datetime = Field(sa_column=Column(DateTime(timezone=False), nullable=True))
    create_by: int = Field(sa_column=Column(BigInteger, nullable=True))
    brief: str = Field(max_length=64, nullable=True)
    chat_type: str = Field(max_length=20, default="chat")  # 聊天与数据源
    datasource: int = Field(sa_column=Column(BigInteger, nullable=True))
    engine_type: str = Field(max_length=64)
    origin: Optional[int] = Field(
        sa_column=Column(Integer, nullable=False, default=0))  # 0：默认，1：MCP，2：助手
    brief_generate: bool = Field(default=False)
    recommended_question_answer: str = Field(sa_column=Column(Text, nullable=True))
    recommended_question: str = Field(sa_column=Column(Text, nullable=True))
    recommended_generate: bool = Field(default=False)


class ChatRecord(SQLModel, table=True):
    """
    类说明：ChatRecord 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "chat_record"
    __table_args__ = (
        Index("idx_chat_record_tenant_id", "tenant_id"),
    )
    id: Optional[int] = Field(sa_column=Column(BigInteger, Identity(always=True), primary_key=True))
    tenant_id: int = Field(default=1, sa_column=Column(BigInteger, nullable=False, server_default="1"))
    chat_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    ai_modal_id: Optional[int] = Field(sa_column=Column(BigInteger))
    first_chat: bool = Field(sa_column=Column(Boolean, nullable=True, default=False))
    create_time: datetime = Field(sa_column=Column(DateTime(timezone=False), nullable=True))
    finish_time: datetime = Field(sa_column=Column(DateTime(timezone=False), nullable=True))
    create_by: int = Field(sa_column=Column(BigInteger, nullable=True))
    datasource: int = Field(sa_column=Column(BigInteger, nullable=True))
    engine_type: str = Field(max_length=64, nullable=True)
    question: str = Field(sa_column=Column(Text, nullable=True))
    sql_answer: str = Field(sa_column=Column(Text, nullable=True))
    sql: str = Field(sa_column=Column(Text, nullable=True))
    sql_exec_result: str = Field(sa_column=Column(Text, nullable=True))
    data: str = Field(sa_column=Column(Text, nullable=True))
    chart_answer: str = Field(sa_column=Column(Text, nullable=True))
    chart: str = Field(sa_column=Column(Text, nullable=True))
    analysis: str = Field(sa_column=Column(Text, nullable=True))
    predict: str = Field(sa_column=Column(Text, nullable=True))
    predict_data: str = Field(sa_column=Column(Text, nullable=True))
    recommended_question_answer: str = Field(sa_column=Column(Text, nullable=True))
    recommended_question: str = Field(sa_column=Column(Text, nullable=True))
    datasource_select_answer: str = Field(sa_column=Column(Text, nullable=True))
    finish: bool = Field(sa_column=Column(Boolean, nullable=True, default=False))
    error: str = Field(sa_column=Column(Text, nullable=True))
    analysis_record_id: int = Field(sa_column=Column(BigInteger, nullable=True))
    predict_record_id: int = Field(sa_column=Column(BigInteger, nullable=True))
    regenerate_record_id: int = Field(sa_column=Column(BigInteger, nullable=True))
    custom_prompt_id: int = Field(sa_column=Column(BigInteger, nullable=True))
    data_skill_id: int = Field(sa_column=Column(BigInteger, nullable=True))
    agent_context_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSONB, nullable=True))


class ChatRecordResult(BaseModel):
    """
    类说明：ChatRecordResult 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    id: Optional[int] = None
    tenant_id: Optional[int] = None
    chat_id: Optional[int] = None
    ai_modal_id: Optional[int] = None
    first_chat: bool = False
    create_time: Optional[datetime] = None
    finish_time: Optional[datetime] = None
    question: Optional[str] = None
    sql_answer: Optional[str] = None
    sql: Optional[str] = None
    datasource: Optional[int] = None
    data: Optional[str] = None
    chart_answer: Optional[str] = None
    chart: Optional[str] = None
    analysis: Optional[str] = None
    predict: Optional[str] = None
    predict_data: Optional[str] = None
    recommended_question: Optional[str] = None
    datasource_select_answer: Optional[str] = None
    finish: Optional[bool] = None
    error: Optional[str] = None
    analysis_record_id: Optional[int] = None
    predict_record_id: Optional[int] = None
    regenerate_record_id: Optional[int] = None
    custom_prompt_id: Optional[int] = None
    data_skill_id: Optional[int] = None
    agent_context_snapshot: Optional[dict] = None
    sql_reasoning_content: Optional[str] = None
    chart_reasoning_content: Optional[str] = None
    analysis_reasoning_content: Optional[str] = None
    predict_reasoning_content: Optional[str] = None
    duration: Optional[float] = None  # 耗时字段（单位：秒）
    total_tokens: Optional[int] = None  # 令牌总消耗


class CreateChat(BaseModel):
    """
    类说明：CreateChat 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    id: int = None
    question: str = None
    datasource: int = None
    origin: Optional[int] = 0  # 0 表示页面来源，1 表示 MCP，2 表示小助手


class RenameChat(BaseModel):
    """
    类说明：RenameChat 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    id: int = None
    brief: str = ''
    brief_generate: bool = True


class ChatInfo(BaseModel):
    """
    类说明：ChatInfo 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    id: Optional[int] = None
    tenant_id: Optional[int] = None
    create_time: datetime = None
    create_by: int = None
    brief: str = ''
    chat_type: str = "chat"
    datasource: Optional[int] = None
    engine_type: str = ''
    ds_type: str = ''
    datasource_name: str = ''
    datasource_exists: bool = True
    recommended_question: Optional[str] = None
    recommended_generate: Optional[bool] = False
    records: List[ChatRecord | dict] = []


class ChatLogHistoryItem(BaseModel):
    """
    类说明：ChatLogHistoryItem 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    start_time: Optional[datetime] = None
    finish_time: Optional[datetime] = None
    duration: Optional[float] = None  # 耗时字段（单位：秒）
    total_tokens: Optional[int] = None  # 令牌总消耗
    operate: Optional[str] = None
    local_operation: Optional[bool] = False
    message: Optional[str | dict | list] = None
    error: Optional[bool] = False


class ChatLogHistory(BaseModel):
    """
    类说明：ChatLogHistory 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    start_time: Optional[datetime] = None
    finish_time: Optional[datetime] = None
    duration: Optional[float] = None  # 耗时字段（单位：秒）
    total_tokens: Optional[int] = None  # 令牌总消耗
    steps: List[ChatLogHistoryItem | dict] = []


class AiModelQuestion(BaseModel):
    """
    类说明：AiModelQuestion 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    question: str = None
    ai_modal_id: int = None
    ai_modal_name: str = None  # 具体模型名称
    engine: str = ""
    db_schema: str = ""
    sql: str = ""
    rule: str = ""
    fields: str = ""
    data: str = ""
    lang: str = "简体中文"
    filter: str = []
    sub_query: Optional[list[dict]] = None
    custom_prompt: str = ""
    custom_prompt_id: Optional[int] = None
    tracking_config: str = ""
    data_skill: str = ""
    data_skill_id: Optional[int] = None
    error_msg: str = ""
    regenerate_record_id: Optional[int] = None
    sample_data: str = ""
    shuzhi_name: str = "星通数智"

    def sql_sys_question(self, db_type: Union[str, DB], enable_query_limit: bool = True):
        """
        是什么：AiModelQuestion.sql_sys_question 是 AiModelQuestion 里的一个步骤，帮它完成聊天问数据和 Agent相关的一件事。
        谁调用：拿到 AiModelQuestion 对象的代码，需要完成这个动作时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        templates: dict[str, str] = {}
        _sql_template = get_sql_example_template(db_type)
        _base_template = get_sql_template()
        _process_check = _sql_template.get('process_check') if _sql_template.get('process_check') else _base_template[
            'process_check']
        _query_limit = _base_template['query_limit'] if enable_query_limit else _base_template['no_query_limit']
        _other_rule = _sql_template['other_rule'].format(multi_table_condition=_base_template['multi_table_condition'])
        _base_sql_rules = _sql_template['quot_rule'] + _query_limit + _sql_template['limit_rule'] + _other_rule
        _sql_examples = _sql_template['basic_example']
        _example_engine = _sql_template['example_engine']
        _example_answer_1 = _sql_template['example_answer_1_with_limit'] if enable_query_limit else _sql_template[
            'example_answer_1']
        _example_answer_2 = _sql_template['example_answer_2_with_limit'] if enable_query_limit else _sql_template[
            'example_answer_2']
        _example_answer_3 = _sql_template['example_answer_3_with_limit'] if enable_query_limit else _sql_template[
            'example_answer_3']

        templates['system'] = _base_template['system'].format(lang=self.lang, process_check=_process_check,
                                                              shuzhi_name=self.shuzhi_name)
        templates['rules'] = _base_template['generate_rules'].format(lang=self.lang,
                                                                     shuzhi_name=self.shuzhi_name,
                                                                     base_sql_rules=_base_sql_rules,
                                                                     basic_sql_examples=_sql_examples,
                                                                     example_engine=_example_engine,
                                                                     example_answer_1=_example_answer_1,
                                                                     example_answer_2=_example_answer_2,
                                                                     example_answer_3=_example_answer_3)
        templates['schema'] = _base_template['generate_basic_info'].format(engine=self.engine, schema=self.db_schema,
                                                                           sample_data=self.sample_data)

        if self.custom_prompt:
            templates['custom_prompt'] = _base_template['generate_custom_prompt_info'].format(
                custom_prompt=self.custom_prompt)

        if self.tracking_config:
            templates['tracking_config'] = _base_template['generate_tracking_config_info'].format(
                tracking_config=self.tracking_config)

        if self.data_skill:
            templates['data_skill'] = _base_template['generate_data_skill_info'].format(
                data_skill=self.data_skill)

        return templates

    def sql_user_question(self, current_time: str, change_title: bool):
        """
        是什么：AiModelQuestion.sql_user_question 是 AiModelQuestion 里的一个步骤，帮它完成聊天问数据和 Agent相关的一件事。
        谁调用：拿到 AiModelQuestion 对象的代码，需要完成这个动作时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        _question = self.question
        if self.regenerate_record_id:
            _question = get_sql_template()['regenerate_hint'] + self.question
        return get_sql_template()['user'].format(lang=self.lang, engine=self.engine, schema=self.db_schema,
                                                 question=_question,
                                                 rule=self.rule, current_time=current_time, error_msg=self.error_msg,
                                                 change_title=change_title)

    def chart_sys_question(self):
        """
        是什么：AiModelQuestion.chart_sys_question 是 AiModelQuestion 里的一个步骤，帮它完成聊天问数据和 Agent相关的一件事。
        谁调用：拿到 AiModelQuestion 对象的代码，需要完成这个动作时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        templates: dict[str, str] = {
            'system': get_chart_template()['system'].format(lang=self.lang, shuzhi_name=self.shuzhi_name),
            'rules': get_chart_template()['generate_rules'].format(lang=self.lang)
        }
        return templates

    def chart_user_question(self, chart_type: Optional[str] = '', schema: Optional[str] = ''):
        """
        是什么：AiModelQuestion.chart_user_question 是 AiModelQuestion 里的一个步骤，帮它完成聊天问数据和 Agent相关的一件事。
        谁调用：拿到 AiModelQuestion 对象的代码，需要完成这个动作时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return get_chart_template()['user'].format(lang=self.lang, sql=self.sql, question=self.question, rule=self.rule,
                                                   chart_type=chart_type, schema=schema, data_skill=self.data_skill)

    def analysis_sys_question(self):
        """
        是什么：AiModelQuestion.analysis_sys_question 是 AiModelQuestion 里的一个步骤，帮它完成聊天问数据和 Agent相关的一件事。
        谁调用：拿到 AiModelQuestion 对象的代码，需要完成这个动作时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return get_analysis_template()['system'].format(lang=self.lang, terminologies="",
                                                        custom_prompt=self.custom_prompt,
                                                        data_skill=self.data_skill,
                                                        shuzhi_name=self.shuzhi_name)

    def analysis_user_question(self):
        """
        是什么：AiModelQuestion.analysis_user_question 是 AiModelQuestion 里的一个步骤，帮它完成聊天问数据和 Agent相关的一件事。
        谁调用：拿到 AiModelQuestion 对象的代码，需要完成这个动作时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return get_analysis_template()['user'].format(fields=self.fields, data=self.data)

    def predict_sys_question(self):
        """
        是什么：AiModelQuestion.predict_sys_question 是 AiModelQuestion 里的一个步骤，帮它完成聊天问数据和 Agent相关的一件事。
        谁调用：拿到 AiModelQuestion 对象的代码，需要完成这个动作时会调用它。
        做了什么：根据已有信息生成聊天问数据和 Agent的结果，比如答案、SQL、图表或建议。
        """
        return get_predict_template()['system'].format(lang=self.lang, custom_prompt=self.custom_prompt,
                                                       data_skill=self.data_skill,
                                                       shuzhi_name=self.shuzhi_name)

    def predict_user_question(self):
        """
        是什么：AiModelQuestion.predict_user_question 是 AiModelQuestion 里的一个步骤，帮它完成聊天问数据和 Agent相关的一件事。
        谁调用：拿到 AiModelQuestion 对象的代码，需要完成这个动作时会调用它。
        做了什么：根据已有信息生成聊天问数据和 Agent的结果，比如答案、SQL、图表或建议。
        """
        return get_predict_template()['user'].format(fields=self.fields, data=self.data)

    def datasource_sys_question(self):
        """
        是什么：AiModelQuestion.datasource_sys_question 是 AiModelQuestion 里的一个步骤，帮它完成聊天问数据和 Agent相关的一件事。
        谁调用：拿到 AiModelQuestion 对象的代码，需要完成这个动作时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return get_datasource_template()['system'].format(lang=self.lang, shuzhi_name=self.shuzhi_name)

    def datasource_user_question(self, datasource_list: str = "[]"):
        """
        是什么：AiModelQuestion.datasource_user_question 是 AiModelQuestion 里的一个步骤，帮它完成聊天问数据和 Agent相关的一件事。
        谁调用：拿到 AiModelQuestion 对象的代码，需要完成这个动作时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return get_datasource_template()['user'].format(lang=self.lang, question=self.question, data=datasource_list)

    def guess_sys_question(self, articles_number: int = 4):
        """
        是什么：AiModelQuestion.guess_sys_question 是 AiModelQuestion 里的一个步骤，帮它完成聊天问数据和 Agent相关的一件事。
        谁调用：拿到 AiModelQuestion 对象的代码，需要完成这个动作时会调用它。
        做了什么：根据已有信息生成聊天问数据和 Agent的结果，比如答案、SQL、图表或建议。
        """
        return get_guess_question_template()['system'].format(lang=self.lang, articles_number=articles_number,
                                                              shuzhi_name=self.shuzhi_name)

    def guess_user_question(self, old_questions: str = "[]"):
        """
        是什么：AiModelQuestion.guess_user_question 是 AiModelQuestion 里的一个步骤，帮它完成聊天问数据和 Agent相关的一件事。
        谁调用：拿到 AiModelQuestion 对象的代码，需要完成这个动作时会调用它。
        做了什么：根据已有信息生成聊天问数据和 Agent的结果，比如答案、SQL、图表或建议。
        """
        return get_guess_question_template()['user'].format(question=self.question, schema=self.db_schema,
                                                            old_questions=old_questions)

    def filter_sys_question(self):
        """
        是什么：AiModelQuestion.filter_sys_question 是 AiModelQuestion 里的一个步骤，帮它完成聊天问数据和 Agent相关的一件事。
        谁调用：拿到 AiModelQuestion 对象的代码，需要完成这个动作时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return get_permissions_template()['system'].format(lang=self.lang, engine=self.engine,
                                                           shuzhi_name=self.shuzhi_name)

    def filter_user_question(self):
        """
        是什么：AiModelQuestion.filter_user_question 是 AiModelQuestion 里的一个步骤，帮它完成聊天问数据和 Agent相关的一件事。
        谁调用：拿到 AiModelQuestion 对象的代码，需要完成这个动作时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return get_permissions_template()['user'].format(sql=self.sql, filter=self.filter)

    def dynamic_sys_question(self):
        """
        是什么：AiModelQuestion.dynamic_sys_question 是 AiModelQuestion 里的一个步骤，帮它完成聊天问数据和 Agent相关的一件事。
        谁调用：拿到 AiModelQuestion 对象的代码，需要完成这个动作时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return get_dynamic_template()['system'].format(lang=self.lang, engine=self.engine, shuzhi_name=self.shuzhi_name)

    def dynamic_user_question(self):
        """
        是什么：AiModelQuestion.dynamic_user_question 是 AiModelQuestion 里的一个步骤，帮它完成聊天问数据和 Agent相关的一件事。
        谁调用：拿到 AiModelQuestion 对象的代码，需要完成这个动作时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return get_dynamic_template()['user'].format(sql=self.sql, sub_query=self.sub_query)


class ChatQuestion(AiModelQuestion):
    """
    类说明：ChatQuestion 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    chat_id: int
    datasource_id: Optional[int] = None


class ChatMcp(ChatQuestion):
    """
    类说明：ChatMcp 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    token: str


class McpDs(BaseModel):
    """
    类说明：McpDs 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    token: str = Body(description='用户token')


class ChatStart(BaseModel):
    """
    类说明：ChatStart 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    username: str = Body(description='用户名')
    password: str = Body(description='密码')


class ChatQuestionBase(BaseModel):
    """
    类说明：ChatQuestionBase 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    question: str = Body(description='用户提问')
    chat_id: int = Body(description='会话ID')
    custom_prompt_id: Optional[int] = Body(description='本次提问选择的自定义 Agent ID', default=None)
    data_skill_id: Optional[int] = Body(description='本次提问选择的数据 Skill ID', default=None)


class McpQuestion(ChatQuestionBase):
    """
    类说明：McpQuestion 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    token: str = Body(description='token')
    stream: Optional[bool] = Body(description='是否流式输出，默认为true开启, 关闭false则返回JSON对象', default=True)
    lang: Optional[str] = Body(description='语言：zh-CN|zh-TW|en|ko-KR', default='zh-CN')
    datasource_id: Optional[int | str] = Body(description='数据源ID，仅当当前对话没有确定数据源时有效', default=None)
    return_img: Optional[bool] = Body(description='是否返回图表，默认为true开启, 关闭false则仅返回数据', default=True)


class AxisObj(BaseModel):
    """
    类说明：AxisObj 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    name: str = ''
    value: str = ''
    type: str | None = None


class ExcelData(BaseModel):
    """
    类说明：ExcelData 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    axis: list[AxisObj] = []
    data: list[dict] = []
    name: str = 'Excel'


class McpAssistant(BaseModel):
    """
    类说明：McpAssistant 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    token: str = Body(description='token')
    question: str = Body(description='用户提问')
    url: str = Body(description='第三方数据接口')
    authorization: str = Body(description='第三方接口凭证')
    stream: Optional[bool] = Body(description='是否流式输出，默认为true开启, 关闭false则返回JSON对象', default=True)


class SystemPromptMessage(SystemMessage):
    """
    类说明：SystemPromptMessage 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    app_system: bool = True

    def __init__(
            self, content: Union[str, list[Union[str, dict]]], **kwargs: Any
    ) -> None:
        """
        是什么：SystemPromptMessage.__init__ 是 SystemPromptMessage 里的一个步骤，帮它完成聊天问数据和 Agent相关的一件事。
        谁调用：创建 SystemPromptMessage 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        super().__init__(content=content, **kwargs)


class HumanPromptMessage(HumanMessage):
    """
    类说明：HumanPromptMessage 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    app_system: bool = True

    def __init__(
            self, content: Union[str, list[Union[str, dict]]], **kwargs: Any
    ) -> None:
        """
        是什么：HumanPromptMessage.__init__ 是 HumanPromptMessage 里的一个步骤，帮它完成聊天问数据和 Agent相关的一件事。
        谁调用：创建 HumanPromptMessage 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        super().__init__(content=content, **kwargs)


class AIPromptMessage(AIMessage):
    """
    类说明：AIPromptMessage 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    app_system: bool = True

    def __init__(
            self, content: Union[str, list[Union[str, dict]]], **kwargs: Any
    ) -> None:
        """
        是什么：AIPromptMessage.__init__ 是 AIPromptMessage 里的一个步骤，帮它完成聊天问数据和 Agent相关的一件事。
        谁调用：创建 AIPromptMessage 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        super().__init__(content=content, **kwargs)
