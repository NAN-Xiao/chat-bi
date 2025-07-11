from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel
from sqlalchemy import Column, Text, BigInteger, DateTime, Identity, Boolean
from sqlmodel import SQLModel, Field

from apps.template.generate_analysis.generator import get_analysis_template
from apps.template.generate_chart.generator import get_chart_template
from apps.template.generate_guess_question.generator import get_guess_question_template
from apps.template.generate_predict.generator import get_predict_template
from apps.template.generate_sql.generator import get_sql_template
from apps.template.select_datasource.generator import get_datasource_template


class Chat(SQLModel, table=True):
    __tablename__ = "chat"
    id: Optional[int] = Field(sa_column=Column(BigInteger, Identity(always=True), primary_key=True))
    create_time: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    create_by: int = Field(sa_column=Column(BigInteger, nullable=True))
    brief: str = Field(max_length=64, nullable=True)
    chat_type: str = Field(max_length=20, default="chat")  # chat, datasource
    datasource: int = Field(sa_column=Column(BigInteger, nullable=True))
    engine_type: str = Field(max_length=64)


class ChatRecord(SQLModel, table=True):
    __tablename__ = "chat_record"
    id: Optional[int] = Field(sa_column=Column(BigInteger, Identity(always=True), primary_key=True))
    chat_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    ai_modal_id: Optional[int] = Field(sa_column=Column(BigInteger))
    first_chat: bool = Field(sa_column=Column(Boolean, nullable=True, default=False))
    create_time: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    finish_time: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    create_by: int = Field(sa_column=Column(BigInteger, nullable=True))
    datasource: int = Field(sa_column=Column(BigInteger, nullable=True))
    engine_type: str = Field(max_length=64)
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
    full_sql_message: str = Field(sa_column=Column(Text, nullable=True))
    token_sql: str = Field(max_length=256, nullable=True)
    full_chart_message: str = Field(sa_column=Column(Text, nullable=True))
    token_chart: str = Field(max_length=256, nullable=True)
    full_analysis_message: str = Field(sa_column=Column(Text, nullable=True))
    token_analysis: str = Field(max_length=256, nullable=True)
    full_predict_message: str = Field(sa_column=Column(Text, nullable=True))
    token_predict: str = Field(max_length=256, nullable=True)
    full_recommended_question_message: str = Field(sa_column=Column(Text, nullable=True))
    token_recommended_question: str = Field(max_length=256, nullable=True)
    full_select_datasource_message: str = Field(sa_column=Column(Text, nullable=True))
    token_select_datasource_question: str = Field(max_length=256, nullable=True)
    finish: bool = Field(sa_column=Column(Boolean, nullable=True, default=False))
    error: str = Field(sa_column=Column(Text, nullable=True))
    analysis_record_id: int = Field(sa_column=Column(BigInteger, nullable=True))
    predict_record_id: int = Field(sa_column=Column(BigInteger, nullable=True))

class CreateChat(BaseModel):
    id: int = None
    question: str = None
    datasource: int = None


class RenameChat(BaseModel):
    id: int = None
    brief: str = ''


class ChatInfo(BaseModel):
    id: Optional[int] = None
    create_time: datetime = None
    create_by: int = None
    brief: str = ''
    chat_type: str = "chat"
    datasource: Optional[int] = None
    engine_type: str = ''
    datasource_name: str = ''
    datasource_exists: bool = True
    records: List[ChatRecord | dict] = []


class AiModelQuestion(BaseModel):
    ai_modal_id: int = None
    engine: str = ""
    db_schema: str = ""
    sql: str = ""
    rule: str = ""
    fields: str = ""
    data: str = ""
    lang: str = "zh-CN"

    def sql_sys_question(self):
        return get_sql_template()['system'].format(engine=self.engine, schema=self.db_schema, question=self.question)

    def sql_user_question(self):
        return get_sql_template()['user'].format(engine=self.engine, schema=self.db_schema, question=self.question,
                                                 rule=self.rule, lang=self.lang)

    def chart_sys_question(self):
        return get_chart_template()['system'].format(sql=self.sql, question=self.question)

    def chart_user_question(self):
        return get_chart_template()['user'].format(sql=self.sql, question=self.question, rule=self.rule, lang=self.lang)

    def analysis_sys_question(self):
        return get_analysis_template()['system']

    def analysis_user_question(self):
        return get_analysis_template()['user'].format(fields=self.fields, data=self.data, lang=self.lang)

    def predict_sys_question(self):
        return get_predict_template()['system']

    def predict_user_question(self):
        return get_predict_template()['user'].format(fields=self.fields, data=self.data, lang=self.lang)

    def datasource_sys_question(self):
        return get_datasource_template()['system']

    def datasource_user_question(self, datasource_list: str = "[]"):
        return get_datasource_template()['user'].format(question=self.question, data=datasource_list, lang=self.lang)

    def guess_sys_question(self):
        return get_guess_question_template()['system']

    def guess_user_question(self, old_questions: str = "[]"):
        return get_guess_question_template()['user'].format(question=self.question, schema=self.db_schema,
                                                            old_questions=old_questions, lang=self.lang)


class ChatQuestion(AiModelQuestion):
    question: str = ''
    chat_id: int = 0


class ChatMcp(ChatQuestion):
    token: str = ''


class ChatStart(BaseModel):
    username: str = ''
    password: str = ''
