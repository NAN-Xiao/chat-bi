from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel
from sqlalchemy import Column, Text, BigInteger, DateTime, Integer, Identity, Boolean
from sqlmodel import SQLModel, Field

from apps.template.generate_chart.generator import get_chart_template
from apps.template.generate_sql.generator import get_sql_template


class Chat(SQLModel, table=True):
    __tablename__ = "chat"
    id: Optional[int] = Field(sa_column=Column(Integer, Identity(always=True), primary_key=True))
    create_time: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    create_by: int = Field(sa_column=Column(BigInteger, nullable=True))
    brief: str = Field(max_length=64, nullable=True)
    chat_type: str = Field(max_length=20, default="chat")  # chat, datasource
    datasource: int = Field(sa_column=Column(Integer, nullable=False))
    engine_type: str = Field(max_length=64)


class ChatRecord(SQLModel, table=True):
    __tablename__ = "chat_record"
    id: Optional[int] = Field(sa_column=Column(Integer, Identity(always=True), primary_key=True))
    chat_id: int = Field(sa_column=Column(Integer))
    create_time: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    finish_time: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    create_by: int = Field(sa_column=Column(BigInteger, nullable=True))
    datasource: int = Field(sa_column=Column(Integer, nullable=False))
    engine_type: str = Field(max_length=64)
    question: str = Field(sa_column=Column(Text, nullable=True))
    sql_answer: str = Field(sa_column=Column(Text, nullable=True))
    sql: str = Field(sa_column=Column(Text, nullable=True))
    sql_exec_result: str = Field(sa_column=Column(Text, nullable=True))
    data: str = Field(sa_column=Column(Text, nullable=True))
    chart_answer: str = Field(sa_column=Column(Text, nullable=True))
    chart: str = Field(sa_column=Column(Text, nullable=True))
    full_sql_message: str = Field(sa_column=Column(Text, nullable=True))
    full_chart_message: str = Field(sa_column=Column(Text, nullable=True))
    finish: bool = Field(sa_column=Column(Boolean, nullable=True, default=False))
    error: str = Field(sa_column=Column(Text, nullable=True))
    run_time: float = Field(default=0)


class CreateChat(BaseModel):
    id: int = None
    question: str = ''
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
    datasource: int = None
    engine_type: str = ''
    datasource_name: str = ''
    datasource_exists: bool = True
    records: List[ChatRecord] = []


class AiModelQuestion(BaseModel):
    engine: str = ""
    db_schema: str = ""
    sql: str = ""
    rule: str = ""

    def sql_sys_question(self):
        return get_sql_template()['system'].format(engine=self.engine, schema=self.db_schema, question=self.question)

    def sql_user_question(self):
        return get_sql_template()['user'].format(engine=self.engine, schema=self.db_schema, question=self.question,
                                                 rule=self.rule)

    def chart_sys_question(self):
        return get_chart_template()['system'].format(sql=self.sql, question=self.question)

    def chart_user_question(self):
        return get_chart_template()['user'].format(sql=self.sql, question=self.question, rule=self.rule)


class ChatQuestion(AiModelQuestion):
    question: str
    chat_id: int
