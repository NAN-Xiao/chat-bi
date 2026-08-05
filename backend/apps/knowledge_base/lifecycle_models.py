"""Database models for knowledge-base version lifecycle state."""

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
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class KnowledgeVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    READY_TO_PUBLISH = "READY_TO_PUBLISH"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    PUBLISH_FAILED = "PUBLISH_FAILED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class KnowledgeMigrationPhase(str, Enum):
    LEGACY_OPEN = "LEGACY_OPEN"
    CUTOVER_BARRIER = "CUTOVER_BARRIER"
    V2_ACTIVE = "V2_ACTIVE"


class KnowledgeIndexStatus(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


ACTIVE_DRAFT_STATUSES = (
    KnowledgeVersionStatus.DRAFT.value,
    KnowledgeVersionStatus.VALIDATING.value,
    KnowledgeVersionStatus.VALIDATION_FAILED.value,
    KnowledgeVersionStatus.READY_TO_PUBLISH.value,
    KnowledgeVersionStatus.PUBLISHING.value,
    KnowledgeVersionStatus.PUBLISH_FAILED.value,
)
ACTIVE_PUBLISH_JOB_STATUSES = ("QUEUING", "QUEUED", "RUNNING")


class KnowledgeBaseVersion(SQLModel, table=True):
    __tablename__ = "knowledge_base_version"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_base_id",
            "version_number",
            name="uq_knowledge_base_version_number",
        ),
        UniqueConstraint(
            "knowledge_base_id",
            "tenant_id",
            "id",
            name="uq_knowledge_base_version_knowledge_tenant_id",
        ),
        ForeignKeyConstraint(
            ["knowledge_base_id", "tenant_id"],
            ["knowledge_base.id", "knowledge_base.tenant_id"],
            name="fk_knowledge_base_version_knowledge_tenant",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "status IN ('DRAFT','VALIDATING','VALIDATION_FAILED',"
            "'READY_TO_PUBLISH','PUBLISHING','PUBLISHED','PUBLISH_FAILED',"
            "'SUPERSEDED','ARCHIVED')",
            name="ck_knowledge_base_version_status",
        ),
        CheckConstraint(
            "index_status IN ('NOT_REQUIRED','PENDING','PROCESSING','READY','FAILED')",
            name="ck_knowledge_base_version_index_status",
        ),
        Index(
            "uq_knowledge_base_version_active_draft",
            "knowledge_base_id",
            unique=True,
            postgresql_where=text(
                "status IN ('DRAFT','VALIDATING','VALIDATION_FAILED',"
                "'READY_TO_PUBLISH','PUBLISHING','PUBLISH_FAILED')"
            ),
        ),
        Index(
            "idx_knowledge_base_version_tenant_knowledge_status",
            "tenant_id",
            "knowledge_base_id",
            "status",
        ),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, Identity(always=True), primary_key=True),
    )
    knowledge_base_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    tenant_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    version_number: int = Field(sa_column=Column(Integer, nullable=False))
    revision: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, server_default="1"),
    )
    status: KnowledgeVersionStatus = Field(
        default=KnowledgeVersionStatus.DRAFT,
        sa_column=Column(String(32), nullable=False, server_default="DRAFT"),
    )
    index_status: KnowledgeIndexStatus = Field(
        default=KnowledgeIndexStatus.NOT_REQUIRED,
        sa_column=Column(String(32), nullable=False, server_default="NOT_REQUIRED"),
    )
    payload: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    normalized_content: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    validation_report: dict | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    content_hash: str | None = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    file_id: str | None = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )
    file_name: str | None = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )
    file_ext: str | None = Field(
        default=None, sa_column=Column(String(32), nullable=True)
    )
    parser_version: str | None = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    create_by: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True)
    )
    create_time: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )
    publish_by: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True)
    )
    publish_time: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )
    error_message: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )


class KnowledgePublishJob(SQLModel, table=True):
    __tablename__ = "knowledge_publish_job"
    __table_args__ = (
        ForeignKeyConstraint(
            ["knowledge_base_id", "tenant_id", "version_id"],
            [
                "knowledge_base_version.knowledge_base_id",
                "knowledge_base_version.tenant_id",
                "knowledge_base_version.id",
            ],
            name="fk_knowledge_publish_job_version",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "status IN ('QUEUING','QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')",
            name="ck_knowledge_publish_job_status",
        ),
        CheckConstraint(
            "stage IS NULL OR stage IN ('PARSE','NORMALIZE','CHUNK','EMBED','FINALIZE')",
            name="ck_knowledge_publish_job_stage",
        ),
        Index(
            "uq_knowledge_publish_job_active_knowledge_base",
            "knowledge_base_id",
            unique=True,
            postgresql_where=text("status IN ('QUEUING','QUEUED','RUNNING')"),
        ),
        Index(
            "uq_knowledge_publish_job_active_snapshot",
            "version_id",
            "revision",
            "content_hash",
            unique=True,
            postgresql_where=text("status IN ('QUEUING','QUEUED','RUNNING')"),
        ),
        Index(
            "idx_knowledge_publish_job_tenant_status_deadline",
            "tenant_id",
            "status",
            "deadline_at",
        ),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, Identity(always=True), primary_key=True),
    )
    tenant_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    knowledge_base_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    version_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    revision: int = Field(sa_column=Column(Integer, nullable=False))
    content_hash: str = Field(sa_column=Column(String(64), nullable=False))
    status: str = Field(
        default="QUEUING",
        sa_column=Column(String(32), nullable=False, server_default="QUEUING"),
    )
    task_id: str | None = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    enqueue_attempts: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    last_enqueue_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )
    attempt: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    max_attempts: int = Field(
        default=3,
        sa_column=Column(Integer, nullable=False, server_default="3"),
    )
    heartbeat_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )
    deadline_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )
    stage: str | None = Field(
        default=None, sa_column=Column(String(32), nullable=True)
    )
    error_code: str | None = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    error_message: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    create_by: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True)
    )
    create_time: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )
    update_time: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )

class KnowledgeMigrationState(SQLModel, table=True):
    __tablename__ = "knowledge_migration_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_knowledge_migration_state_singleton"),
        CheckConstraint(
            "phase IN ('LEGACY_OPEN','CUTOVER_BARRIER','V2_ACTIVE')",
            name="ck_knowledge_migration_state_phase",
        ),
    )

    id: int = Field(
        default=1,
        sa_column=Column(SmallInteger, primary_key=True, server_default="1"),
    )
    phase: KnowledgeMigrationPhase = Field(
        default=KnowledgeMigrationPhase.LEGACY_OPEN,
        sa_column=Column(String(32), nullable=False, server_default="LEGACY_OPEN"),
    )
    scan_cursor: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True)
    )
    last_caught_up_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )
    revision: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False, server_default="0"),
    )
    update_time: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )


class KnowledgeStorageProbe(SQLModel, table=True):
    __tablename__ = "knowledge_storage_probe"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_knowledge_storage_probe_singleton"),
    )

    id: int = Field(
        default=1,
        sa_column=Column(SmallInteger, primary_key=True, server_default="1"),
    )
    generation: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False, server_default="0"),
    )
    config_fingerprint: str | None = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    file_id: str | None = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )
    token_hash: str | None = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    content_hash: str | None = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    update_time: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )


class KnowledgeStorageProbeReceipt(SQLModel, table=True):
    __tablename__ = "knowledge_storage_probe_receipt"
    __table_args__ = (
        UniqueConstraint(
            "generation",
            "worker_id",
            "queue_name",
            name="uq_knowledge_storage_probe_receipt_consumer",
        ),
        Index(
            "idx_knowledge_storage_probe_receipt_generation_heartbeat",
            "generation",
            "heartbeat_at",
        ),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, Identity(always=True), primary_key=True),
    )
    generation: int = Field(sa_column=Column(BigInteger, nullable=False))
    worker_id: str = Field(sa_column=Column(String(128), nullable=False))
    queue_name: str = Field(sa_column=Column(String(128), nullable=False))
    content_hash: str = Field(sa_column=Column(String(64), nullable=False))
    heartbeat_at: datetime = Field(
        sa_column=Column(DateTime(timezone=False), nullable=False)
    )
    create_time: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )
    update_time: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=False), nullable=True)
    )
