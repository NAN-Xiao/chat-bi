"""
脚本说明：这个脚本放后端业务相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Identity, Index, String, Text
from sqlmodel import Field, SQLModel


class KnowledgeBaseVisibilityScopeEnum(str, Enum):
    """
    类说明：KnowledgeBaseVisibilityScopeEnum 收拢后端业务里固定的可选值，避免代码里到处写零散字符串。
    """
    PLATFORM_PUBLIC = "PLATFORM_PUBLIC"
    ADMIN_PUBLIC = "ADMIN_PUBLIC"


class KnowledgeBaseStatusEnum(str, Enum):
    """
    类说明：KnowledgeBaseStatusEnum 收拢后端业务里固定的可选值，避免代码里到处写零散字符串。
    """
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class KnowledgeBase(SQLModel, table=True):
    """
    类说明：KnowledgeBase 用来描述后端业务的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    __tablename__ = "knowledge_base"
    __table_args__ = (
        Index("idx_knowledge_base_tenant_scope", "tenant_id", "visibility_scope"),
        Index("idx_knowledge_base_create_by", "create_by"),
        Index("idx_knowledge_base_status", "status"),
    )

    id: Optional[int] = Field(sa_column=Column(BigInteger, Identity(always=True), primary_key=True))
    tenant_id: int = Field(default=1, sa_column=Column(BigInteger, nullable=False, server_default="1"))
    create_by: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    name: str = Field(sa_column=Column(String(255), nullable=False))
    description: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    content: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    visibility_scope: KnowledgeBaseVisibilityScopeEnum = Field(
        default=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
        sa_column=Column(
            String(32),
            nullable=False,
            server_default=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC.value,
        ),
    )
    active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, server_default="true"))
    status: KnowledgeBaseStatusEnum = Field(
        default=KnowledgeBaseStatusEnum.PENDING,
        sa_column=Column(String(32), nullable=False, server_default=KnowledgeBaseStatusEnum.PENDING.value),
    )
    file_id: Optional[str] = Field(default=None, sa_column=Column(String(255), nullable=True))
    file_name: Optional[str] = Field(default=None, sa_column=Column(String(255), nullable=True))
    file_ext: Optional[str] = Field(default=None, sa_column=Column(String(32), nullable=True))
    task_id: Optional[str] = Field(default=None, sa_column=Column(String(64), nullable=True))
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    create_time: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    update_time: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))


class KnowledgeBaseItem(BaseModel):
    """
    类说明：KnowledgeBaseItem 把后端业务相关的数据和行为放在一起，便于其他代码直接复用。
    """
    id: int
    tenant_id: int
    create_by: Optional[int] = None
    name: str
    description: Optional[str] = None
    content: Optional[str] = None
    visibility_scope: KnowledgeBaseVisibilityScopeEnum
    active: bool
    status: KnowledgeBaseStatusEnum
    file_id: Optional[str] = None
    file_name: Optional[str] = None
    file_ext: Optional[str] = None
    task_id: Optional[str] = None
    error_message: Optional[str] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    can_manage: bool = False
