from sqlmodel import SQLModel, Field
from sqlalchemy import Column, Text, BigInteger, DateTime, Integer, Identity
from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional


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
    create_by: int = Field(sa_column=Column(BigInteger, nullable=True))
    datasource: int = Field(sa_column=Column(Integer, nullable=False))
    engine_type: str = Field(max_length=64)
    question: str = Field(sa_column=Column(Text, nullable=True))
    full_question: str = Field(sa_column=Column(Text, nullable=True))
    answer: str = Field(sa_column=Column(Text, nullable=True))
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
