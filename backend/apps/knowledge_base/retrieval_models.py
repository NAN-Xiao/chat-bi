"""Database models for versioned knowledge retrieval projections."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from apps.knowledge_base import models as _knowledge_models  # noqa: F401


class KnowledgeApplicabilityStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    STALE = "STALE"
    ERROR = "ERROR"


class KnowledgeSourceType(str, Enum):
    TRACKING_CONFIG = "TRACKING_CONFIG"
    TRACKING_TABLE = "TRACKING_TABLE"
    TRACKING_FIELD = "TRACKING_FIELD"


class KnowledgeBaseChunk(SQLModel, table=True):
    __tablename__ = "knowledge_base_chunk"
    __table_args__ = (
        ForeignKeyConstraint(
            ["knowledge_base_id", "tenant_id", "version_id"],
            [
                "knowledge_base_version.knowledge_base_id",
                "knowledge_base_version.tenant_id",
                "knowledge_base_version.id",
            ],
            name="fk_knowledge_base_chunk_version",
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint(
            "version_id",
            "chunk_index",
            name="uq_knowledge_base_chunk_version_index",
        ),
        UniqueConstraint(
            "knowledge_base_id",
            "tenant_id",
            "version_id",
            "id",
            name="uq_knowledge_base_chunk_owner_id",
        ),
        CheckConstraint(
            "visibility_scope IN ('PLATFORM_PUBLIC','ADMIN_PUBLIC')",
            name="ck_knowledge_base_chunk_visibility_scope",
        ),
        CheckConstraint(
            "chunk_index >= 0",
            name="ck_knowledge_base_chunk_index",
        ),
        CheckConstraint(
            "token_count IS NULL OR token_count >= 0",
            name="ck_knowledge_base_chunk_token_count",
        ),
        CheckConstraint(
            "embedding_dimension IS NULL OR embedding_dimension > 0",
            name="ck_knowledge_base_chunk_embedding_dimension",
        ),
        Index(
            "idx_knowledge_base_chunk_retrieval_scope",
            "tenant_id",
            "visibility_scope",
            "version_id",
        ),
        Index("idx_knowledge_base_chunk_content_hash", "content_hash"),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, Identity(always=True), primary_key=True),
    )
    knowledge_base_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    version_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    tenant_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    visibility_scope: str = Field(sa_column=Column(String(32), nullable=False))
    chunk_index: int = Field(sa_column=Column(Integer, nullable=False))
    section_path: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    content: str = Field(sa_column=Column(Text, nullable=False))
    token_count: int | None = Field(
        default=None, sa_column=Column(Integer, nullable=True)
    )
    content_hash: str = Field(sa_column=Column(String(64), nullable=False))
    embedding_model: str | None = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )
    embedding_signature: str | None = Field(
        default=None, sa_column=Column(String(128), nullable=True)
    )
    embedding_dimension: int | None = Field(
        default=None, sa_column=Column(Integer, nullable=True)
    )
    embedding: list[float] | None = Field(
        default=None, sa_column=Column(VECTOR(), nullable=True)
    )
    create_time: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )


class KnowledgeBaseWorkspaceOverride(SQLModel, table=True):
    __tablename__ = "knowledge_base_workspace_override"
    __table_args__ = (
        ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_base.id"],
            name="fk_knowledge_base_workspace_override_knowledge",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id",
            "knowledge_base_id",
            name="uq_knowledge_base_workspace_override_tenant_knowledge",
        ),
        Index(
            "idx_knowledge_base_workspace_override_enabled",
            "tenant_id",
            "enabled",
        ),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, Identity(always=True), primary_key=True),
    )
    tenant_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    knowledge_base_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true"),
    )
    reason: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    update_by: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True)
    )
    update_time: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )


class KnowledgeBaseApplicability(SQLModel, table=True):
    __tablename__ = "knowledge_base_applicability"
    __table_args__ = (
        ForeignKeyConstraint(
            ["knowledge_base_id", "knowledge_tenant_id", "version_id"],
            [
                "knowledge_base_version.knowledge_base_id",
                "knowledge_base_version.tenant_id",
                "knowledge_base_version.id",
            ],
            name="fk_knowledge_base_applicability_version",
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint(
            "version_id",
            "tenant_id",
            "datasource_id",
            "physical_schema_hash",
            name="uq_knowledge_base_applicability_context",
        ),
        CheckConstraint(
            "status IN ('VALID','INVALID','STALE','ERROR')",
            name="ck_knowledge_base_applicability_status",
        ),
        Index(
            "idx_knowledge_base_applicability_lookup",
            "tenant_id",
            "datasource_id",
            "physical_schema_hash",
            "status",
        ),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, Identity(always=True), primary_key=True),
    )
    knowledge_base_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    knowledge_tenant_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    version_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    tenant_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    datasource_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    physical_schema_hash: str = Field(sa_column=Column(String(64), nullable=False))
    status: KnowledgeApplicabilityStatus = Field(
        default=KnowledgeApplicabilityStatus.STALE,
        sa_column=Column(String(32), nullable=False, server_default="STALE"),
    )
    report: dict | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    checked_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )


class KnowledgeBaseSourceReference(SQLModel, table=True):
    __tablename__ = "knowledge_base_source_reference"
    __table_args__ = (
        ForeignKeyConstraint(
            ["knowledge_base_id", "tenant_id", "version_id"],
            [
                "knowledge_base_version.knowledge_base_id",
                "knowledge_base_version.tenant_id",
                "knowledge_base_version.id",
            ],
            name="fk_knowledge_base_source_reference_version",
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint(
            "version_id",
            "source_type",
            "source_id",
            name="uq_knowledge_base_source_reference_version_source",
        ),
        CheckConstraint(
            "source_type IN ('TRACKING_CONFIG','TRACKING_TABLE','TRACKING_FIELD')",
            name="ck_knowledge_base_source_reference_source_type",
        ),
        CheckConstraint(
            "sync_mode = 'READ_ONLY'",
            name="ck_knowledge_base_source_reference_sync_mode",
        ),
        Index(
            "idx_knowledge_base_source_reference_source",
            "tenant_id",
            "source_type",
            "source_id",
        ),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, Identity(always=True), primary_key=True),
    )
    knowledge_base_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    version_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    tenant_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    source_type: KnowledgeSourceType = Field(
        sa_column=Column(String(32), nullable=False)
    )
    source_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    source_hash: str = Field(sa_column=Column(String(64), nullable=False))
    sync_mode: str = Field(
        default="READ_ONLY",
        sa_column=Column(String(16), nullable=False, server_default="READ_ONLY"),
    )
    create_time: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )
