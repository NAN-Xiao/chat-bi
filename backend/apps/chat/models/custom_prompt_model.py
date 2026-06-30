"""
脚本说明：这个脚本定义聊天问数据和 Agent用到的数据表或数据对象，便于代码和数据库对齐。
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Identity, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from apps.chat.curd.custom_prompt import (
    CustomPromptTargetScopeEnum,
    CustomPromptTypeEnum,
    CustomPromptVisibilityScopeEnum,
)


class CustomPrompt(SQLModel, table=True):
    """
    类说明：CustomPrompt 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "custom_prompt"

    id: Optional[int] = Field(sa_column=Column(BigInteger, Identity(always=True), primary_key=True))
    tenant_id: int = Field(default=1, sa_column=Column(BigInteger, nullable=False, server_default="1"))
    type: Optional[CustomPromptTypeEnum] = Field(default=None, max_length=20)
    create_time: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    target_scope: Optional[CustomPromptTargetScopeEnum] = Field(
        default=CustomPromptTargetScopeEnum.SMART_QA,
        max_length=32,
    )
    active: Optional[bool] = Field(default=False, sa_column=Column(Boolean, default=False))
    visible: Optional[bool] = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true"),
    )
    ai_model_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    create_by: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    visibility_scope: Optional[CustomPromptVisibilityScopeEnum] = Field(
        default=CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC,
        sa_column=Column(String(32), nullable=False, server_default=CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC.value),
    )
    prompt: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    embedding: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    embedding_signature: Optional[str] = Field(default=None, sa_column=Column(String(128), nullable=True))
    specific_ds: Optional[bool] = Field(default=False, sa_column=Column(Boolean, default=False))
    datasource_ids: Optional[list[int]] = Field(default=[], sa_column=Column(JSONB))


class CustomPromptUserPreference(SQLModel, table=True):
    """
    类说明：CustomPromptUserPreference 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "custom_prompt_user_preference"
    __table_args__ = (
        UniqueConstraint("custom_prompt_id", "user_id", name="uq_custom_prompt_user_preference_prompt_user"),
        Index("idx_custom_prompt_user_preference_user", "user_id"),
        Index("idx_custom_prompt_user_preference_prompt", "custom_prompt_id"),
    )

    id: Optional[int] = Field(sa_column=Column(BigInteger, Identity(always=True), primary_key=True))
    tenant_id: int = Field(default=1, sa_column=Column(BigInteger, nullable=False, server_default="1"))
    custom_prompt_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    user_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    enabled: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, server_default="true"))
    update_time: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))


class CustomPromptInfo(BaseModel):
    """
    类说明：CustomPromptInfo 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    id: Optional[int] = None
    tenant_id: Optional[int] = None
    type: Optional[CustomPromptTypeEnum] = None
    create_time: Optional[datetime] = None
    name: Optional[str] = None
    description: Optional[str] = None
    target_scope: Optional[CustomPromptTargetScopeEnum] = CustomPromptTargetScopeEnum.SMART_QA
    active: Optional[bool] = False
    visible: Optional[bool] = None
    ai_model_id: Optional[int] = None
    ai_model_name: Optional[str] = None
    can_manage: Optional[bool] = False
    is_owner: Optional[bool] = False
    prompt_visible: Optional[bool] = True
    user_enabled: Optional[bool] = True
    effective_active: Optional[bool] = True
    visibility_scope: Optional[CustomPromptVisibilityScopeEnum] = CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC
    prompt: Optional[str] = None
    specific_ds: Optional[bool] = False
    datasource_ids: Optional[list[int]] = []
    datasource_names: Optional[list[str]] = []


class CustomPromptOption(BaseModel):
    """
    类说明：CustomPromptOption 表示聊天问数据和 Agent里的一类数据，通常用来和数据库表或业务对象对应。
    """
    id: int
    type: Optional[CustomPromptTypeEnum] = None
    name: Optional[str] = None
    description: Optional[str] = None
    target_scope: Optional[CustomPromptTargetScopeEnum] = CustomPromptTargetScopeEnum.SMART_QA
    ai_model_id: Optional[int] = None
    ai_model_name: Optional[str] = None
    visible: Optional[bool] = True
    visibility_scope: Optional[CustomPromptVisibilityScopeEnum] = CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC
