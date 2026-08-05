"""Create knowledge-base version lifecycle and deferred pointer constraints."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "153knowledgeversion"
down_revision = "152platformsqlaliasquote"
branch_labels = None
depends_on = None


ACTIVE_DRAFT_SQL = (
    "status IN ('DRAFT','VALIDATING','VALIDATION_FAILED',"
    "'READY_TO_PUBLISH','PUBLISHING','PUBLISH_FAILED')"
)
ACTIVE_PUBLISH_JOB_SQL = "status IN ('QUEUING','QUEUED','RUNNING')"


def upgrade() -> None:
    op.add_column(
        "knowledge_base",
        sa.Column("knowledge_type", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "knowledge_base",
        sa.Column("stable_key", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "knowledge_base",
        sa.Column("archived", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "knowledge_base",
        sa.Column("update_by", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "knowledge_base",
        sa.Column("publish_by", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "knowledge_base",
        sa.Column("publish_time", sa.DateTime(timezone=False), nullable=True),
    )
    op.create_check_constraint(
        "ck_knowledge_base_knowledge_type",
        "knowledge_base",
        "knowledge_type IS NULL OR knowledge_type IN "
        "('DOCUMENT','BUSINESS','EVENT','JSON_FIELD')",
    )
    op.create_unique_constraint(
        "uq_knowledge_base_tenant_scope_stable_key",
        "knowledge_base",
        ["tenant_id", "visibility_scope", "stable_key"],
    )
    op.create_unique_constraint(
        "uq_knowledge_base_id_tenant",
        "knowledge_base",
        ["id", "tenant_id"],
    )
    op.create_table(
        "knowledge_base_version",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("knowledge_base_id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="DRAFT", nullable=False),
        sa.Column(
            "index_status",
            sa.String(length=32),
            server_default="NOT_REQUIRED",
            nullable=False,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("normalized_content", sa.Text(), nullable=True),
        sa.Column(
            "validation_report",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("file_id", sa.String(length=255), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("file_ext", sa.String(length=32), nullable=True),
        sa.Column("parser_version", sa.String(length=64), nullable=True),
        sa.Column("create_by", sa.BigInteger(), nullable=True),
        sa.Column("create_time", sa.DateTime(timezone=False), nullable=True),
        sa.Column("publish_by", sa.BigInteger(), nullable=True),
        sa.Column("publish_time", sa.DateTime(timezone=False), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('DRAFT','VALIDATING','VALIDATION_FAILED',"
            "'READY_TO_PUBLISH','PUBLISHING','PUBLISHED','PUBLISH_FAILED',"
            "'SUPERSEDED','ARCHIVED')",
            name="ck_knowledge_base_version_status",
        ),
        sa.CheckConstraint(
            "index_status IN ('NOT_REQUIRED','PENDING','PROCESSING','READY','FAILED')",
            name="ck_knowledge_base_version_index_status",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id", "tenant_id"],
            ["knowledge_base.id", "knowledge_base.tenant_id"],
            name="fk_knowledge_base_version_knowledge_tenant",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "knowledge_base_id",
            "version_number",
            name="uq_knowledge_base_version_number",
        ),
        sa.UniqueConstraint(
            "knowledge_base_id",
            "tenant_id",
            "id",
            name="uq_knowledge_base_version_knowledge_tenant_id",
        ),
    )
    op.create_index(
        "uq_knowledge_base_version_active_draft",
        "knowledge_base_version",
        ["knowledge_base_id"],
        unique=True,
        postgresql_where=sa.text(ACTIVE_DRAFT_SQL),
    )
    op.create_index(
        "idx_knowledge_base_version_tenant_knowledge_status",
        "knowledge_base_version",
        ["tenant_id", "knowledge_base_id", "status"],
    )

    for pointer in ("draft_version_id", "current_version_id", "publishing_version_id"):
        op.add_column(
            "knowledge_base",
            sa.Column(pointer, sa.BigInteger(), nullable=True),
        )
        op.create_foreign_key(
            f"fk_knowledge_base_{pointer}_version",
            "knowledge_base",
            "knowledge_base_version",
            ["id", "tenant_id", pointer],
            ["knowledge_base_id", "tenant_id", "id"],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        )

    op.create_table(
        "knowledge_publish_job",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("knowledge_base_id", sa.BigInteger(), nullable=False),
        sa.Column("version_id", sa.BigInteger(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="QUEUING", nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column("enqueue_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_enqueue_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("attempt", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("stage", sa.String(length=32), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("create_by", sa.BigInteger(), nullable=True),
        sa.Column("create_time", sa.DateTime(timezone=False), nullable=True),
        sa.Column("update_time", sa.DateTime(timezone=False), nullable=True),
        sa.CheckConstraint(
            "status IN ('QUEUING','QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')",
            name="ck_knowledge_publish_job_status",
        ),
        sa.CheckConstraint(
            "stage IS NULL OR stage IN ('PARSE','NORMALIZE','CHUNK','EMBED','FINALIZE')",
            name="ck_knowledge_publish_job_stage",
        ),
        sa.ForeignKeyConstraint(
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_knowledge_publish_job_active_knowledge_base",
        "knowledge_publish_job",
        ["knowledge_base_id"],
        unique=True,
        postgresql_where=sa.text(ACTIVE_PUBLISH_JOB_SQL),
    )
    op.create_index(
        "uq_knowledge_publish_job_active_snapshot",
        "knowledge_publish_job",
        ["version_id", "revision", "content_hash"],
        unique=True,
        postgresql_where=sa.text(ACTIVE_PUBLISH_JOB_SQL),
    )
    op.create_index(
        "idx_knowledge_publish_job_tenant_status_deadline",
        "knowledge_publish_job",
        ["tenant_id", "status", "deadline_at"],
    )

    op.create_table(
        "knowledge_migration_state",
        sa.Column("id", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column(
            "phase",
            sa.String(length=32),
            server_default="LEGACY_OPEN",
            nullable=False,
        ),
        sa.Column("scan_cursor", sa.BigInteger(), nullable=True),
        sa.Column("last_caught_up_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("revision", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=False), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_knowledge_migration_state_singleton"),
        sa.CheckConstraint(
            "phase IN ('LEGACY_OPEN','CUTOVER_BARRIER','V2_ACTIVE')",
            name="ck_knowledge_migration_state_phase",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO knowledge_migration_state (id, phase, revision) "
            "VALUES (1, 'LEGACY_OPEN', 0)"
        )
    )

    op.create_table(
        "knowledge_storage_probe",
        sa.Column("id", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("generation", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("config_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("file_id", sa.String(length=255), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("update_time", sa.DateTime(timezone=False), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_knowledge_storage_probe_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        sa.text("INSERT INTO knowledge_storage_probe (id, generation) VALUES (1, 0)")
    )
    op.create_table(
        "knowledge_storage_probe_receipt",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=False),
        sa.Column("queue_name", sa.String(length=128), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("create_time", sa.DateTime(timezone=False), nullable=True),
        sa.Column("update_time", sa.DateTime(timezone=False), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "generation",
            "worker_id",
            "queue_name",
            name="uq_knowledge_storage_probe_receipt_consumer",
        ),
    )
    op.create_index(
        "idx_knowledge_storage_probe_receipt_generation_heartbeat",
        "knowledge_storage_probe_receipt",
        ["generation", "heartbeat_at"],
    )

    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION enforce_knowledge_base_pointer_states()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $$
            DECLARE
                target_knowledge_base_id BIGINT;
                target_tenant_id BIGINT;
                previous_knowledge_base_id BIGINT;
                previous_tenant_id BIGINT;
            BEGIN
                IF TG_TABLE_NAME = 'knowledge_base' THEN
                    target_knowledge_base_id := NEW.id;
                    target_tenant_id := NEW.tenant_id;
                ELSIF TG_OP = 'DELETE' THEN
                    target_knowledge_base_id := OLD.knowledge_base_id;
                    target_tenant_id := OLD.tenant_id;
                ELSE
                    target_knowledge_base_id := NEW.knowledge_base_id;
                    target_tenant_id := NEW.tenant_id;
                    IF TG_OP = 'UPDATE' THEN
                        previous_knowledge_base_id := OLD.knowledge_base_id;
                        previous_tenant_id := OLD.tenant_id;
                    END IF;
                END IF;

                PERFORM 1
                FROM knowledge_base AS kb
                WHERE (
                    kb.id = target_knowledge_base_id
                    AND kb.tenant_id = target_tenant_id
                ) OR (
                    previous_knowledge_base_id IS NOT NULL
                    AND kb.id = previous_knowledge_base_id
                    AND kb.tenant_id = previous_tenant_id
                )
                FOR UPDATE;

                IF EXISTS (
                    SELECT 1
                    FROM knowledge_base AS kb
                    LEFT JOIN knowledge_base_version AS draft
                      ON draft.knowledge_base_id = kb.id
                     AND draft.tenant_id = kb.tenant_id
                     AND draft.id = kb.draft_version_id
                    LEFT JOIN knowledge_base_version AS current_version
                      ON current_version.knowledge_base_id = kb.id
                     AND current_version.tenant_id = kb.tenant_id
                     AND current_version.id = kb.current_version_id
                    LEFT JOIN knowledge_base_version AS publishing
                      ON publishing.knowledge_base_id = kb.id
                     AND publishing.tenant_id = kb.tenant_id
                     AND publishing.id = kb.publishing_version_id
                    WHERE (
                        (
                            kb.id = target_knowledge_base_id
                            AND kb.tenant_id = target_tenant_id
                        ) OR (
                            previous_knowledge_base_id IS NOT NULL
                            AND kb.id = previous_knowledge_base_id
                            AND kb.tenant_id = previous_tenant_id
                        )
                    ) AND (
                        (
                            kb.draft_version_id IS NOT NULL
                            AND (
                                draft.id IS NULL
                                OR draft.status NOT IN (
                                    'DRAFT','VALIDATING','VALIDATION_FAILED',
                                    'READY_TO_PUBLISH','PUBLISHING','PUBLISH_FAILED'
                                )
                            )
                        ) OR (
                            kb.current_version_id IS NOT NULL
                            AND (
                                current_version.id IS NULL
                                OR current_version.status <> 'PUBLISHED'
                            )
                        ) OR (
                            kb.publishing_version_id IS NOT NULL
                            AND (
                                publishing.id IS NULL
                                OR publishing.status <> 'PUBLISHING'
                                OR kb.draft_version_id IS DISTINCT FROM
                                   kb.publishing_version_id
                            )
                        )
                    )
                ) THEN
                    RAISE EXCEPTION USING
                        ERRCODE = '23514',
                        MESSAGE = 'knowledge_base version pointer has an invalid final state';
                END IF;
                RETURN NULL;
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE CONSTRAINT TRIGGER trg_knowledge_base_pointer_state
            AFTER INSERT OR UPDATE ON knowledge_base
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW
            EXECUTE FUNCTION enforce_knowledge_base_pointer_states()
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE CONSTRAINT TRIGGER trg_knowledge_base_version_pointer_state
            AFTER INSERT OR UPDATE OR DELETE ON knowledge_base_version
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW
            EXECUTE FUNCTION enforce_knowledge_base_pointer_states()
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_knowledge_base_version_pointer_state "
            "ON knowledge_base_version"
        )
    )
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_knowledge_base_pointer_state ON knowledge_base"
        )
    )
    op.execute(
        sa.text("DROP FUNCTION IF EXISTS enforce_knowledge_base_pointer_states()")
    )

    op.drop_index(
        "idx_knowledge_storage_probe_receipt_generation_heartbeat",
        table_name="knowledge_storage_probe_receipt",
    )
    op.drop_table("knowledge_storage_probe_receipt")
    op.drop_table("knowledge_storage_probe")
    op.drop_table("knowledge_migration_state")

    op.drop_index(
        "idx_knowledge_publish_job_tenant_status_deadline",
        table_name="knowledge_publish_job",
    )
    op.drop_index(
        "uq_knowledge_publish_job_active_snapshot",
        table_name="knowledge_publish_job",
    )
    op.drop_index(
        "uq_knowledge_publish_job_active_knowledge_base",
        table_name="knowledge_publish_job",
    )
    op.drop_table("knowledge_publish_job")

    for pointer in ("publishing_version_id", "current_version_id", "draft_version_id"):
        op.drop_constraint(
            f"fk_knowledge_base_{pointer}_version",
            "knowledge_base",
            type_="foreignkey",
        )
        op.drop_column("knowledge_base", pointer)

    op.drop_index(
        "idx_knowledge_base_version_tenant_knowledge_status",
        table_name="knowledge_base_version",
    )
    op.drop_index(
        "uq_knowledge_base_version_active_draft",
        table_name="knowledge_base_version",
    )
    op.drop_table("knowledge_base_version")
    op.drop_constraint(
        "uq_knowledge_base_id_tenant",
        "knowledge_base",
        type_="unique",
    )
    op.drop_constraint(
        "uq_knowledge_base_tenant_scope_stable_key",
        "knowledge_base",
        type_="unique",
    )
    op.drop_constraint(
        "ck_knowledge_base_knowledge_type",
        "knowledge_base",
        type_="check",
    )
    for column in (
        "publish_time",
        "publish_by",
        "update_by",
        "archived",
        "stable_key",
        "knowledge_type",
    ):
        op.drop_column("knowledge_base", column)
