"""
脚本说明：这个脚本定义系统管理用到的数据表或数据对象，便于代码和数据库对齐。
"""
# 作者：Junjun
# 日期：2026/1/26

from datetime import datetime
from typing import List

from sqlalchemy import Column, BigInteger, Identity, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import SQLModel, Field


class SystemVariable(SQLModel, table=True):
    """
    类说明：SystemVariable 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
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
