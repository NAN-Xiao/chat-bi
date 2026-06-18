from datetime import datetime
from typing import List, Optional

from pgvector.sqlalchemy import VECTOR
from pydantic import BaseModel
from sqlalchemy import Column, Text, BigInteger, DateTime, Identity, Boolean, String
from sqlmodel import SQLModel, Field

from apps.system.schemas.semantic_scope import SemanticRecordScopeEnum


class DataTraining(SQLModel, table=True):
    __tablename__ = "data_training"
    id: Optional[int] = Field(sa_column=Column(BigInteger, Identity(always=True), primary_key=True))
    tenant_id: int = Field(default=1, sa_column=Column(BigInteger, nullable=False, server_default="1"))
    scope: SemanticRecordScopeEnum = Field(
        default=SemanticRecordScopeEnum.TENANT,
        sa_column=Column(String(32), nullable=False, server_default=SemanticRecordScopeEnum.TENANT.value),
    )
    datasource: Optional[int] = Field(sa_column=Column(BigInteger, nullable=True))
    create_time: Optional[datetime] = Field(sa_column=Column(DateTime(timezone=False), nullable=True))
    question: Optional[str] = Field(max_length=255)
    description: Optional[str] = Field(sa_column=Column(Text, nullable=True))
    embedding: Optional[List[float]] = Field(sa_column=Column(VECTOR(), nullable=True))
    enabled: Optional[bool] = Field(sa_column=Column(Boolean, default=True))
    advanced_application: Optional[int] = Field(sa_column=Column(BigInteger, nullable=True))


class DataTrainingInfo(BaseModel):
    id: Optional[int] = None
    tenant_id: Optional[int] = None
    scope: Optional[SemanticRecordScopeEnum] = SemanticRecordScopeEnum.TENANT
    datasource: Optional[int] = None
    datasource_name: Optional[str] = None
    create_time: Optional[datetime] = None
    question: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = True
    advanced_application: Optional[int] = None
    advanced_application_name: Optional[str] = None
    can_manage: Optional[bool] = False


class DataTrainingInfoResult(BaseModel):
    id: Optional[str] = None
    tenant_id: Optional[int] = None
    scope: Optional[SemanticRecordScopeEnum] = SemanticRecordScopeEnum.TENANT
    datasource: Optional[int] = None
    datasource_name: Optional[str] = None
    create_time: Optional[datetime] = None
    question: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = True
    advanced_application: Optional[str] = None
    advanced_application_name: Optional[str] = None
    can_manage: Optional[bool] = False
