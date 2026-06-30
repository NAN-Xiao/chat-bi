"""
脚本说明：这个脚本放分析助手相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field as PydanticField
from sqlalchemy import BigInteger, Column, DateTime, Identity, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field as SQLModelField, SQLModel


class AnalysisAssistantConversation(SQLModel, table=True):
    """
    类说明：AnalysisAssistantConversation 把分析助手相关的数据和行为放在一起，便于其他代码直接复用。
    """
    __tablename__ = "analysis_assistant_conversation"
    __table_args__ = (
        Index("idx_analysis_assistant_conversation_tenant_user", "tenant_id", "create_by"),
        Index("idx_analysis_assistant_conversation_datasource", "datasource_id"),
        Index("idx_analysis_assistant_conversation_update_time", "update_time"),
    )

    id: Optional[int] = SQLModelField(sa_column=Column(BigInteger, Identity(always=True), primary_key=True))
    tenant_id: int = SQLModelField(default=1, sa_column=Column(BigInteger, nullable=False, server_default="1"))
    create_by: int = SQLModelField(sa_column=Column(BigInteger, nullable=False))
    title: str = SQLModelField(default="", sa_column=Column(String(128), nullable=False, server_default=""))
    datasource_id: Optional[int] = SQLModelField(default=None, sa_column=Column(BigInteger, nullable=True))
    datasource_name: Optional[str] = SQLModelField(default=None, sa_column=Column(String(255), nullable=True))
    custom_prompt_id: Optional[int] = SQLModelField(default=None, sa_column=Column(BigInteger, nullable=True))
    data_skill_id: Optional[int] = SQLModelField(default=None, sa_column=Column(BigInteger, nullable=True))
    messages: list[dict] = SQLModelField(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    )
    create_time: datetime = SQLModelField(sa_column=Column(DateTime(timezone=False), nullable=False))
    update_time: datetime = SQLModelField(sa_column=Column(DateTime(timezone=False), nullable=False))


class AnalysisAssistantConversationMessage(BaseModel):
    """
    类说明：AnalysisAssistantConversationMessage 把分析助手相关的数据和行为放在一起，便于其他代码直接复用。
    """
    role: str
    content: str = ""
    plan: dict | None = None
    planText: str | None = None
    traces: list[str] | None = None
    blocks: list[dict] | None = None
    final: str | None = None
    agentContextSnapshot: dict | None = None
    error: bool | None = None


class AnalysisAssistantConversationSave(BaseModel):
    """
    类说明：AnalysisAssistantConversationSave 把分析助手相关的数据和行为放在一起，便于其他代码直接复用。
    """
    id: Optional[int] = None
    title: Optional[str] = None
    datasource_id: Optional[int] = None
    datasource_name: Optional[str] = None
    custom_prompt_id: Optional[int] = None
    data_skill_id: Optional[int] = None
    messages: list[AnalysisAssistantConversationMessage] = PydanticField(default_factory=list)


class AnalysisAssistantConversationSummary(BaseModel):
    """
    类说明：AnalysisAssistantConversationSummary 把分析助手相关的数据和行为放在一起，便于其他代码直接复用。
    """
    id: int
    title: str
    datasource_id: Optional[int] = None
    datasource_name: Optional[str] = None
    custom_prompt_id: Optional[int] = None
    data_skill_id: Optional[int] = None
    message_count: int = 0
    create_time: datetime
    update_time: datetime


class AnalysisAssistantConversationDetail(AnalysisAssistantConversationSummary):
    """
    类说明：AnalysisAssistantConversationDetail 把分析助手相关的数据和行为放在一起，便于其他代码直接复用。
    """
    messages: list[dict] = PydanticField(default_factory=list)
