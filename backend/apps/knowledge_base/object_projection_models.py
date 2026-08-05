"""Database models for semantic-object references and resolution state."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from apps.chat.models import custom_prompt_model as _custom_prompt_model  # noqa: F401
from apps.knowledge_base import retrieval_models as _retrieval_models  # noqa: F401


class SemanticObjectOwnerType(str, Enum):
    KNOWLEDGE_VERSION = "KNOWLEDGE_VERSION"
    KNOWLEDGE_CHUNK = "KNOWLEDGE_CHUNK"
    DATA_SKILL = "DATA_SKILL"


class SemanticObjectType(str, Enum):
    SCHEMA = "SCHEMA"
    TABLE = "TABLE"
    FIELD = "FIELD"
    JSON_PATH = "JSON_PATH"
    EVENT = "EVENT"
    EVENT_PROPERTY = "EVENT_PROPERTY"


class SemanticResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    STALE = "STALE"


class SemanticReferenceSourceKind(str, Enum):
    EXPLICIT = "EXPLICIT"
    SQL_AST = "SQL_AST"
    STRUCTURED_PAYLOAD = "STRUCTURED_PAYLOAD"
    SKILL_RULE = "SKILL_RULE"
    INHERITED = "INHERITED"


class DataSkillProjectionStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    FAILED = "FAILED"
    STALE = "STALE"


class DataSkillObjectProjection(SQLModel, table=True):
    __tablename__ = "data_skill_object_projection"
    __table_args__ = (
        ForeignKeyConstraint(
            ["skill_id"],
            ["custom_prompt.id"],
            name="fk_data_skill_object_projection_skill",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "skill_id",
            name="uq_data_skill_object_projection_skill",
        ),
        UniqueConstraint(
            "skill_id",
            "tenant_id",
            name="uq_data_skill_object_projection_skill_tenant",
        ),
        CheckConstraint(
            "status IN ('PENDING','READY','FAILED','STALE')",
            name="ck_data_skill_object_projection_status",
        ),
        CheckConstraint(
            "reference_count >= 0",
            name="ck_data_skill_object_projection_reference_count",
        ),
        Index(
            "idx_data_skill_object_projection_ready",
            "tenant_id",
            "target_scope",
            "status",
        ),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, Identity(always=True), primary_key=True),
    )
    skill_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    tenant_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    user_id: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True)
    )
    target_scope: str | None = Field(
        default=None, sa_column=Column(String(32), nullable=True)
    )
    source_hash: str = Field(sa_column=Column(String(64), nullable=False))
    projector_version: str = Field(sa_column=Column(String(64), nullable=False))
    status: DataSkillProjectionStatus = Field(
        default=DataSkillProjectionStatus.PENDING,
        sa_column=Column(String(32), nullable=False, server_default="PENDING"),
    )
    reference_count: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    error_code: str | None = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    checked_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )


class SemanticObjectReference(SQLModel, table=True):
    __tablename__ = "semantic_object_reference"
    __table_args__ = (
        ForeignKeyConstraint(
            ["knowledge_base_id", "tenant_id", "version_id"],
            [
                "knowledge_base_version.knowledge_base_id",
                "knowledge_base_version.tenant_id",
                "knowledge_base_version.id",
            ],
            name="fk_semantic_object_reference_version",
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["knowledge_base_id", "tenant_id", "version_id", "chunk_id"],
            [
                "knowledge_base_chunk.knowledge_base_id",
                "knowledge_base_chunk.tenant_id",
                "knowledge_base_chunk.version_id",
                "knowledge_base_chunk.id",
            ],
            name="fk_semantic_object_reference_chunk",
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["skill_id", "tenant_id"],
            [
                "data_skill_object_projection.skill_id",
                "data_skill_object_projection.tenant_id",
            ],
            name="fk_semantic_object_reference_skill_projection",
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint(
            "owner_type",
            "owner_id",
            "declared_key",
            "source_kind",
            name="uq_semantic_object_reference_owner_declared_source",
        ),
        CheckConstraint(
            "(owner_type = 'KNOWLEDGE_VERSION' "
            "AND owner_id = version_id "
            "AND knowledge_base_id IS NOT NULL "
            "AND version_id IS NOT NULL "
            "AND chunk_id IS NULL "
            "AND skill_id IS NULL) OR "
            "(owner_type = 'KNOWLEDGE_CHUNK' "
            "AND owner_id = chunk_id "
            "AND knowledge_base_id IS NOT NULL "
            "AND version_id IS NOT NULL "
            "AND chunk_id IS NOT NULL "
            "AND skill_id IS NULL) OR "
            "(owner_type = 'DATA_SKILL' "
            "AND owner_id = skill_id "
            "AND knowledge_base_id IS NULL "
            "AND version_id IS NULL "
            "AND chunk_id IS NULL "
            "AND skill_id IS NOT NULL)",
            name="ck_semantic_object_reference_owner",
        ),
        CheckConstraint(
            "object_type IN ('SCHEMA','TABLE','FIELD','JSON_PATH','EVENT','EVENT_PROPERTY')",
            name="ck_semantic_object_reference_object_type",
        ),
        CheckConstraint(
            "resolution_status IN ('RESOLVED','UNRESOLVED','AMBIGUOUS','STALE')",
            name="ck_semantic_object_reference_resolution_status",
        ),
        CheckConstraint(
            "source_kind IN ('EXPLICIT','SQL_AST','STRUCTURED_PAYLOAD','SKILL_RULE','INHERITED')",
            name="ck_semantic_object_reference_source_kind",
        ),
        Index(
            "idx_semantic_object_reference_owner",
            "tenant_id",
            "owner_type",
            "owner_id",
        ),
        Index(
            "idx_semantic_object_reference_resolution",
            "tenant_id",
            "datasource_id",
            "resolution_status",
        ),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, Identity(always=True), primary_key=True),
    )
    tenant_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    owner_type: SemanticObjectOwnerType = Field(
        sa_column=Column(String(32), nullable=False)
    )
    owner_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    knowledge_base_id: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True)
    )
    version_id: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True)
    )
    chunk_id: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True)
    )
    skill_id: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True)
    )
    object_type: SemanticObjectType = Field(
        sa_column=Column(String(32), nullable=False)
    )
    datasource_id: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True)
    )
    catalog_name: str | None = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )
    schema_name: str | None = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )
    table_name: str | None = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )
    field_name: str | None = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )
    json_path: str | None = Field(
        default=None, sa_column=Column(String(1024), nullable=True)
    )
    event_name: str | None = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )
    event_property_key: str | None = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )
    declared_key: str = Field(sa_column=Column(String(64), nullable=False))
    resolution_status: SemanticResolutionStatus = Field(
        default=SemanticResolutionStatus.UNRESOLVED,
        sa_column=Column(String(32), nullable=False, server_default="UNRESOLVED"),
    )
    source_kind: SemanticReferenceSourceKind = Field(
        sa_column=Column(String(32), nullable=False)
    )
    create_time: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )


class SemanticObjectResolution(SQLModel, table=True):
    __tablename__ = "semantic_object_resolution"
    __table_args__ = (
        ForeignKeyConstraint(
            ["reference_id"],
            ["semantic_object_reference.id"],
            name="fk_semantic_object_resolution_reference",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "reference_id",
            "tenant_id",
            "datasource_id",
            "physical_schema_hash",
            name="uq_semantic_object_resolution_context",
        ),
        CheckConstraint(
            "status IN ('RESOLVED','UNRESOLVED','AMBIGUOUS','STALE')",
            name="ck_semantic_object_resolution_status",
        ),
        CheckConstraint(
            "(status = 'RESOLVED' AND canonical_key IS NOT NULL) OR "
            "(status <> 'RESOLVED' AND canonical_key IS NULL)",
            name="ck_semantic_object_resolution_canonical_state",
        ),
        Index(
            "idx_semantic_object_resolution_lookup",
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
    reference_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    tenant_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    datasource_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    physical_schema_hash: str = Field(sa_column=Column(String(64), nullable=False))
    canonical_key: str | None = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    status: SemanticResolutionStatus = Field(
        default=SemanticResolutionStatus.UNRESOLVED,
        sa_column=Column(String(32), nullable=False, server_default="UNRESOLVED"),
    )
    report: dict | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    checked_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )
