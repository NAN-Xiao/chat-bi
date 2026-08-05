"""Database model for monotonic semantic authority epochs."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Identity,
    Index,
    String,
    text,
)
from sqlmodel import Field, SQLModel


class SemanticScopeType(str, Enum):
    PERMISSION = "PERMISSION"
    SYSTEM_ROLE = "SYSTEM_ROLE"
    MEMBERSHIP = "MEMBERSHIP"
    DATASOURCE_ACCESS = "DATASOURCE_ACCESS"
    DATASOURCE_ROLE = "DATASOURCE_ROLE"
    TRACKING = "TRACKING"
    DATASOURCE_BINDING = "DATASOURCE_BINDING"
    SCHEMA = "SCHEMA"


class SemanticScopeEpoch(SQLModel, table=True):
    __tablename__ = "semantic_scope_epoch"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('PERMISSION','SYSTEM_ROLE','MEMBERSHIP',"
            "'DATASOURCE_ACCESS','DATASOURCE_ROLE','TRACKING',"
            "'DATASOURCE_BINDING','SCHEMA')",
            name="ck_semantic_scope_epoch_scope_type",
        ),
        Index(
            "uq_semantic_scope_epoch_scope",
            "scope_type",
            "tenant_id",
            text("COALESCE(datasource_id, 0)"),
            text("COALESCE(subject_id, 0)"),
            unique=True,
        ),
        Index(
            "idx_semantic_scope_epoch_tenant",
            "tenant_id",
            "scope_type",
        ),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, Identity(always=True), primary_key=True),
    )
    scope_type: SemanticScopeType = Field(
        sa_column=Column(String(32), nullable=False)
    )
    tenant_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    datasource_id: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True)
    )
    subject_id: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True)
    )
    epoch: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False, server_default="0"),
    )
    update_time: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )
