from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Identity, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from apps.chat.curd.custom_prompt import CustomPromptTypeEnum


class CustomPrompt(SQLModel, table=True):
    __tablename__ = "custom_prompt"

    id: Optional[int] = Field(sa_column=Column(BigInteger, Identity(always=True), primary_key=True))
    type: Optional[CustomPromptTypeEnum] = Field(default=None, max_length=20)
    create_time: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    name: Optional[str] = Field(default=None, max_length=255)
    prompt: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    specific_ds: Optional[bool] = Field(default=False, sa_column=Column(Boolean, default=False))
    datasource_ids: Optional[list[int]] = Field(default=[], sa_column=Column(JSONB))


class CustomPromptInfo(BaseModel):
    id: Optional[int] = None
    type: Optional[CustomPromptTypeEnum] = None
    create_time: Optional[datetime] = None
    name: Optional[str] = None
    prompt: Optional[str] = None
    specific_ds: Optional[bool] = False
    datasource_ids: Optional[list[int]] = []
    datasource_names: Optional[list[str]] = []
