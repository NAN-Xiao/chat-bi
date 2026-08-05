"""Database models for redacted retrieval and semantic-context audits."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Identity,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class KnowledgeRetrievalLog(SQLModel, table=True):
    __tablename__ = "knowledge_retrieval_log"
    __table_args__ = (
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_knowledge_retrieval_log_latency",
        ),
        Index("idx_knowledge_retrieval_log_request", "request_id"),
        Index(
            "idx_knowledge_retrieval_log_scope_time",
            "tenant_id",
            "datasource_id",
            "create_time",
        ),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, Identity(always=True), primary_key=True),
    )
    request_id: str = Field(sa_column=Column(String(64), nullable=False))
    surface: str = Field(sa_column=Column(String(64), nullable=False))
    tenant_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    user_id: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True)
    )
    datasource_id: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True)
    )
    query_hash: str = Field(sa_column=Column(String(64), nullable=False))
    model_signature: str | None = Field(
        default=None, sa_column=Column(String(128), nullable=True)
    )
    hit_snapshot: list[dict] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
    )
    latency_ms: int | None = Field(
        default=None, sa_column=Column(Integer, nullable=True)
    )
    warnings: list[dict] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
    )
    failure_type: str | None = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    create_time: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )


class SemanticContextAudit(SQLModel, table=True):
    __tablename__ = "semantic_context_audit"
    __table_args__ = (
        Index("idx_semantic_context_audit_request", "request_id"),
        Index(
            "idx_semantic_context_audit_scope_time",
            "tenant_id",
            "user_id",
            "datasource_id",
            "create_time",
        ),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, Identity(always=True), primary_key=True),
    )
    request_id: str = Field(sa_column=Column(String(64), nullable=False))
    tenant_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    user_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    datasource_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    surface: str = Field(sa_column=Column(String(64), nullable=False))
    permission_version: str = Field(sa_column=Column(String(128), nullable=False))
    schema_hash: str = Field(sa_column=Column(String(64), nullable=False))
    knowledge_snapshot: list[dict] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
    )
    skill_snapshot: list[dict] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
    )
    warnings: list[dict] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
    )
    create_time: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )
