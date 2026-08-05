"""Create knowledge retrieval, audit, and semantic-object projections."""

from __future__ import annotations

import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "154knowledgeretrieval"
down_revision = "153knowledgeversion"
branch_labels = None
depends_on = None


def _jsonb() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def _create_chunk_table() -> None:
    op.create_table(
        "knowledge_base_chunk",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("knowledge_base_id", sa.BigInteger(), nullable=False),
        sa.Column("version_id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("visibility_scope", sa.String(length=32), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("section_path", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=True),
        sa.Column("embedding_signature", sa.String(length=128), nullable=True),
        sa.Column("embedding_dimension", sa.Integer(), nullable=True),
        sa.Column("embedding", VECTOR(), nullable=True),
        sa.Column("create_time", sa.DateTime(timezone=False), nullable=True),
        sa.CheckConstraint(
            "visibility_scope IN ('PLATFORM_PUBLIC','ADMIN_PUBLIC')",
            name="ck_knowledge_base_chunk_visibility_scope",
        ),
        sa.CheckConstraint(
            "chunk_index >= 0",
            name="ck_knowledge_base_chunk_index",
        ),
        sa.CheckConstraint(
            "token_count IS NULL OR token_count >= 0",
            name="ck_knowledge_base_chunk_token_count",
        ),
        sa.CheckConstraint(
            "embedding_dimension IS NULL OR embedding_dimension > 0",
            name="ck_knowledge_base_chunk_embedding_dimension",
        ),
        sa.ForeignKeyConstraint(
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "version_id",
            "chunk_index",
            name="uq_knowledge_base_chunk_version_index",
        ),
        sa.UniqueConstraint(
            "knowledge_base_id",
            "tenant_id",
            "version_id",
            "id",
            name="uq_knowledge_base_chunk_owner_id",
        ),
    )
    op.create_index(
        "idx_knowledge_base_chunk_retrieval_scope",
        "knowledge_base_chunk",
        ["tenant_id", "visibility_scope", "version_id"],
    )
    op.create_index(
        "idx_knowledge_base_chunk_content_hash",
        "knowledge_base_chunk",
        ["content_hash"],
    )


def _create_knowledge_scope_tables() -> None:
    op.create_table(
        "knowledge_base_workspace_override",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("knowledge_base_id", sa.BigInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("update_by", sa.BigInteger(), nullable=True),
        sa.Column("update_time", sa.DateTime(timezone=False), nullable=True),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_base.id"],
            name="fk_knowledge_base_workspace_override_knowledge",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "knowledge_base_id",
            name="uq_knowledge_base_workspace_override_tenant_knowledge",
        ),
    )
    op.create_index(
        "idx_knowledge_base_workspace_override_enabled",
        "knowledge_base_workspace_override",
        ["tenant_id", "enabled"],
    )

    op.create_table(
        "knowledge_base_applicability",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("knowledge_base_id", sa.BigInteger(), nullable=False),
        sa.Column("knowledge_tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("version_id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("datasource_id", sa.BigInteger(), nullable=False),
        sa.Column("physical_schema_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="STALE", nullable=False),
        sa.Column("report", _jsonb(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=False), nullable=True),
        sa.CheckConstraint(
            "status IN ('VALID','INVALID','STALE','ERROR')",
            name="ck_knowledge_base_applicability_status",
        ),
        sa.ForeignKeyConstraint(
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "version_id",
            "tenant_id",
            "datasource_id",
            "physical_schema_hash",
            name="uq_knowledge_base_applicability_context",
        ),
    )
    op.create_index(
        "idx_knowledge_base_applicability_lookup",
        "knowledge_base_applicability",
        ["tenant_id", "datasource_id", "physical_schema_hash", "status"],
    )

    op.create_table(
        "knowledge_base_source_reference",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("knowledge_base_id", sa.BigInteger(), nullable=False),
        sa.Column("version_id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "sync_mode",
            sa.String(length=16),
            server_default="READ_ONLY",
            nullable=False,
        ),
        sa.Column("create_time", sa.DateTime(timezone=False), nullable=True),
        sa.CheckConstraint(
            "source_type IN ('TRACKING_CONFIG','TRACKING_TABLE','TRACKING_FIELD')",
            name="ck_knowledge_base_source_reference_source_type",
        ),
        sa.CheckConstraint(
            "sync_mode = 'READ_ONLY'",
            name="ck_knowledge_base_source_reference_sync_mode",
        ),
        sa.ForeignKeyConstraint(
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "version_id",
            "source_type",
            "source_id",
            name="uq_knowledge_base_source_reference_version_source",
        ),
    )
    op.create_index(
        "idx_knowledge_base_source_reference_source",
        "knowledge_base_source_reference",
        ["tenant_id", "source_type", "source_id"],
    )


def _create_audit_tables() -> None:
    op.create_table(
        "knowledge_retrieval_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("surface", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("datasource_id", sa.BigInteger(), nullable=True),
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column("model_signature", sa.String(length=128), nullable=True),
        sa.Column(
            "hit_snapshot",
            _jsonb(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "warnings",
            _jsonb(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("failure_type", sa.String(length=64), nullable=True),
        sa.Column("create_time", sa.DateTime(timezone=False), nullable=True),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_knowledge_retrieval_log_latency",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_knowledge_retrieval_log_request",
        "knowledge_retrieval_log",
        ["request_id"],
    )
    op.create_index(
        "idx_knowledge_retrieval_log_scope_time",
        "knowledge_retrieval_log",
        ["tenant_id", "datasource_id", "create_time"],
    )

    op.create_table(
        "semantic_context_audit",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("datasource_id", sa.BigInteger(), nullable=False),
        sa.Column("surface", sa.String(length=64), nullable=False),
        sa.Column("permission_version", sa.String(length=128), nullable=False),
        sa.Column("schema_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "knowledge_snapshot",
            _jsonb(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "skill_snapshot",
            _jsonb(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "warnings",
            _jsonb(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("create_time", sa.DateTime(timezone=False), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_semantic_context_audit_request",
        "semantic_context_audit",
        ["request_id"],
    )
    op.create_index(
        "idx_semantic_context_audit_scope_time",
        "semantic_context_audit",
        ["tenant_id", "user_id", "datasource_id", "create_time"],
    )


def _create_object_projection_tables() -> None:
    op.create_table(
        "data_skill_object_projection",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("skill_id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("target_scope", sa.String(length=32), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("projector_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column("reference_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=False), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING','READY','FAILED','STALE')",
            name="ck_data_skill_object_projection_status",
        ),
        sa.CheckConstraint(
            "reference_count >= 0",
            name="ck_data_skill_object_projection_reference_count",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["custom_prompt.id"],
            name="fk_data_skill_object_projection_skill",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "skill_id",
            name="uq_data_skill_object_projection_skill",
        ),
        sa.UniqueConstraint(
            "skill_id",
            "tenant_id",
            name="uq_data_skill_object_projection_skill_tenant",
        ),
    )
    op.create_index(
        "idx_data_skill_object_projection_ready",
        "data_skill_object_projection",
        ["tenant_id", "target_scope", "status"],
    )

    op.create_table(
        "semantic_object_reference",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("owner_type", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("knowledge_base_id", sa.BigInteger(), nullable=True),
        sa.Column("version_id", sa.BigInteger(), nullable=True),
        sa.Column("chunk_id", sa.BigInteger(), nullable=True),
        sa.Column("skill_id", sa.BigInteger(), nullable=True),
        sa.Column("object_type", sa.String(length=32), nullable=False),
        sa.Column("datasource_id", sa.BigInteger(), nullable=True),
        sa.Column("catalog_name", sa.String(length=255), nullable=True),
        sa.Column("schema_name", sa.String(length=255), nullable=True),
        sa.Column("table_name", sa.String(length=255), nullable=True),
        sa.Column("field_name", sa.String(length=255), nullable=True),
        sa.Column("json_path", sa.String(length=1024), nullable=True),
        sa.Column("event_name", sa.String(length=255), nullable=True),
        sa.Column("event_property_key", sa.String(length=255), nullable=True),
        sa.Column("declared_key", sa.String(length=64), nullable=False),
        sa.Column(
            "resolution_status",
            sa.String(length=32),
            server_default="UNRESOLVED",
            nullable=False,
        ),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("create_time", sa.DateTime(timezone=False), nullable=True),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "object_type IN ('SCHEMA','TABLE','FIELD','JSON_PATH','EVENT','EVENT_PROPERTY')",
            name="ck_semantic_object_reference_object_type",
        ),
        sa.CheckConstraint(
            "resolution_status IN ('RESOLVED','UNRESOLVED','AMBIGUOUS','STALE')",
            name="ck_semantic_object_reference_resolution_status",
        ),
        sa.CheckConstraint(
            "source_kind IN ('EXPLICIT','SQL_AST','STRUCTURED_PAYLOAD','SKILL_RULE','INHERITED')",
            name="ck_semantic_object_reference_source_kind",
        ),
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_type",
            "owner_id",
            "declared_key",
            "source_kind",
            name="uq_semantic_object_reference_owner_declared_source",
        ),
    )
    op.create_index(
        "idx_semantic_object_reference_owner",
        "semantic_object_reference",
        ["tenant_id", "owner_type", "owner_id"],
    )
    op.create_index(
        "idx_semantic_object_reference_resolution",
        "semantic_object_reference",
        ["tenant_id", "datasource_id", "resolution_status"],
    )

    op.create_table(
        "semantic_object_resolution",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("reference_id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("datasource_id", sa.BigInteger(), nullable=False),
        sa.Column("physical_schema_hash", sa.String(length=64), nullable=False),
        sa.Column("canonical_key", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="UNRESOLVED",
            nullable=False,
        ),
        sa.Column("report", _jsonb(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=False), nullable=True),
        sa.CheckConstraint(
            "status IN ('RESOLVED','UNRESOLVED','AMBIGUOUS','STALE')",
            name="ck_semantic_object_resolution_status",
        ),
        sa.CheckConstraint(
            "(status = 'RESOLVED' AND canonical_key IS NOT NULL) OR "
            "(status <> 'RESOLVED' AND canonical_key IS NULL)",
            name="ck_semantic_object_resolution_canonical_state",
        ),
        sa.ForeignKeyConstraint(
            ["reference_id"],
            ["semantic_object_reference.id"],
            name="fk_semantic_object_resolution_reference",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "reference_id",
            "tenant_id",
            "datasource_id",
            "physical_schema_hash",
            name="uq_semantic_object_resolution_context",
        ),
    )
    op.create_index(
        "idx_semantic_object_resolution_lookup",
        "semantic_object_resolution",
        ["tenant_id", "datasource_id", "physical_schema_hash", "status"],
    )


def upgrade() -> None:
    _create_chunk_table()
    _create_knowledge_scope_tables()
    _create_audit_tables()
    _create_object_projection_tables()


def downgrade() -> None:
    op.drop_index(
        "idx_semantic_object_resolution_lookup",
        table_name="semantic_object_resolution",
    )
    op.drop_table("semantic_object_resolution")
    op.drop_index(
        "idx_semantic_object_reference_resolution",
        table_name="semantic_object_reference",
    )
    op.drop_index(
        "idx_semantic_object_reference_owner",
        table_name="semantic_object_reference",
    )
    op.drop_table("semantic_object_reference")
    op.drop_index(
        "idx_data_skill_object_projection_ready",
        table_name="data_skill_object_projection",
    )
    op.drop_table("data_skill_object_projection")

    op.drop_index(
        "idx_semantic_context_audit_scope_time",
        table_name="semantic_context_audit",
    )
    op.drop_index(
        "idx_semantic_context_audit_request",
        table_name="semantic_context_audit",
    )
    op.drop_table("semantic_context_audit")
    op.drop_index(
        "idx_knowledge_retrieval_log_scope_time",
        table_name="knowledge_retrieval_log",
    )
    op.drop_index(
        "idx_knowledge_retrieval_log_request",
        table_name="knowledge_retrieval_log",
    )
    op.drop_table("knowledge_retrieval_log")

    op.drop_index(
        "idx_knowledge_base_source_reference_source",
        table_name="knowledge_base_source_reference",
    )
    op.drop_table("knowledge_base_source_reference")
    op.drop_index(
        "idx_knowledge_base_applicability_lookup",
        table_name="knowledge_base_applicability",
    )
    op.drop_table("knowledge_base_applicability")
    op.drop_index(
        "idx_knowledge_base_workspace_override_enabled",
        table_name="knowledge_base_workspace_override",
    )
    op.drop_table("knowledge_base_workspace_override")

    op.drop_index(
        "idx_knowledge_base_chunk_content_hash",
        table_name="knowledge_base_chunk",
    )
    op.drop_index(
        "idx_knowledge_base_chunk_retrieval_scope",
        table_name="knowledge_base_chunk",
    )
    op.drop_table("knowledge_base_chunk")
