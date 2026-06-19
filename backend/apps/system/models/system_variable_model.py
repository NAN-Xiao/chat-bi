# Author: Junjun
# Date: 2026/1/26

from datetime import datetime
from typing import List

from sqlalchemy import Column, BigInteger, Identity, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import SQLModel, Field


class SystemVariable(SQLModel, table=True):
    __tablename__ = "system_variable"
    __table_args__ = (
        Index("idx_system_variable_tenant_id", "tenant_id"),
    )
    id: int = Field(sa_column=Column(BigInteger, Identity(always=True), nullable=False, primary_key=True))
    tenant_id: int = Field(default=1, sa_column=Column(BigInteger(), nullable=False, server_default="1"))
    name: str = Field(max_length=128, nullable=False)
    var_type: str = Field(max_length=128, nullable=False)
    type: str = Field(max_length=128, nullable=False)
    value: List = Field(sa_column=Column(JSONB, nullable=True))
    create_time: datetime = Field(sa_column=Column(DateTime(timezone=False), nullable=True))
    create_by: int = Field(sa_column=Column(BigInteger()))
