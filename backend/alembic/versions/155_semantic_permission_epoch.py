"""Add complete catalog identity and semantic permission epochs."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "155semanticpermepoch"
down_revision = "154knowledgeretrieval"
branch_labels = None
depends_on = None


def _add_catalog_columns() -> None:
    op.add_column(
        "core_datasource",
        sa.Column(
            "catalog_complete",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.add_column(
        "core_datasource",
        sa.Column("catalog_incomplete_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "core_datasource",
        sa.Column("physical_schema_hash", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        "ck_core_datasource_catalog_complete_hash",
        "core_datasource",
        "catalog_complete = false OR physical_schema_hash IS NOT NULL",
    )

    for name in ("catalog_name", "schema_name", "catalog_key", "schema_key", "table_key"):
        op.add_column(
            "core_table",
            sa.Column(name, sa.String(length=255), nullable=True),
        )
    op.add_column(
        "core_field",
        sa.Column("field_key", sa.String(length=255), nullable=True),
    )


def _backfill_catalog_keys() -> None:
    op.execute(
        sa.text(
            """
            UPDATE core_table
            SET catalog_key = BTRIM(COALESCE(catalog_name, '')),
                schema_key = CASE
                    WHEN BTRIM(COALESCE(schema_name, '')) = ''
                    THEN CONCAT('__legacy_schema__:', id)
                    ELSE BTRIM(schema_name)
                END,
                table_key = BTRIM(COALESCE(table_name, ''))
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE core_field
            SET field_key = BTRIM(COALESCE(field_name, ''))
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE core_datasource
            SET catalog_complete = false,
                catalog_incomplete_reason = 'LEGACY_CATALOG_REQUIRES_REFRESH',
                physical_schema_hash = NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM core_table
                    WHERE table_key IS NULL OR table_key = ''
                ) THEN
                    RAISE EXCEPTION '存在空表名，无法建立完整物理对象键，请先修复数据源目录';
                END IF;
                IF EXISTS (
                    SELECT 1 FROM core_field
                    WHERE field_key IS NULL OR field_key = ''
                ) THEN
                    RAISE EXCEPTION '存在空字段名，无法建立完整物理对象键，请先修复数据源目录';
                END IF;
                IF EXISTS (
                    SELECT 1
                    FROM core_table
                    GROUP BY ds_id, catalog_key, schema_key, table_key
                    HAVING COUNT(*) > 1
                ) THEN
                    RAISE EXCEPTION '存在重复表目录键，请刷新或清理数据源目录后重试';
                END IF;
                IF EXISTS (
                    SELECT 1
                    FROM core_field
                    GROUP BY table_id, field_key
                    HAVING COUNT(*) > 1
                ) THEN
                    RAISE EXCEPTION '存在重复字段目录键，请刷新或清理数据源目录后重试';
                END IF;
            END;
            $$
            """
        )
    )

    for name in ("catalog_key", "schema_key", "table_key"):
        op.alter_column(
            "core_table",
            name,
            existing_type=sa.String(length=255),
            nullable=False,
        )
    op.alter_column(
        "core_field",
        "field_key",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_core_table_full_identity",
        "core_table",
        ["ds_id", "catalog_key", "schema_key", "table_key"],
    )
    op.create_unique_constraint(
        "uq_core_field_full_identity",
        "core_field",
        ["table_id", "field_key"],
    )


def _create_legacy_catalog_write_guards() -> None:
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION fill_legacy_core_table_catalog_keys()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $$
            DECLARE
                used_legacy_fallback BOOLEAN := false;
            BEGIN
                IF NEW.catalog_key IS NULL THEN
                    NEW.catalog_key := BTRIM(COALESCE(NEW.catalog_name, ''));
                    used_legacy_fallback := true;
                END IF;
                IF NEW.schema_key IS NULL OR BTRIM(NEW.schema_key) = '' THEN
                    NEW.schema_key := CASE
                        WHEN BTRIM(COALESCE(NEW.schema_name, '')) = ''
                        THEN CONCAT('__legacy_schema__:', NEW.id)
                        ELSE BTRIM(NEW.schema_name)
                    END;
                    used_legacy_fallback := true;
                END IF;
                IF NEW.table_key IS NULL OR BTRIM(NEW.table_key) = '' THEN
                    NEW.table_key := BTRIM(COALESCE(NEW.table_name, ''));
                    used_legacy_fallback := true;
                END IF;

                IF TG_OP = 'UPDATE' THEN
                    IF NEW.catalog_name IS DISTINCT FROM OLD.catalog_name
                       AND NEW.catalog_key IS NOT DISTINCT FROM OLD.catalog_key THEN
                        NEW.catalog_key := BTRIM(COALESCE(NEW.catalog_name, ''));
                        used_legacy_fallback := true;
                    END IF;
                    IF NEW.schema_name IS DISTINCT FROM OLD.schema_name
                       AND NEW.schema_key IS NOT DISTINCT FROM OLD.schema_key THEN
                        NEW.schema_key := CASE
                            WHEN BTRIM(COALESCE(NEW.schema_name, '')) = ''
                            THEN CONCAT('__legacy_schema__:', NEW.id)
                            ELSE BTRIM(NEW.schema_name)
                        END;
                        used_legacy_fallback := true;
                    END IF;
                    IF NEW.table_name IS DISTINCT FROM OLD.table_name
                       AND NEW.table_key IS NOT DISTINCT FROM OLD.table_key THEN
                        NEW.table_key := BTRIM(COALESCE(NEW.table_name, ''));
                        used_legacy_fallback := true;
                    END IF;
                END IF;

                IF NEW.table_key = '' THEN
                    RAISE EXCEPTION '表名不能为空，无法生成目录键';
                END IF;
                IF used_legacy_fallback THEN
                    UPDATE core_datasource
                    SET catalog_complete = false,
                        catalog_incomplete_reason = 'LEGACY_CATALOG_REQUIRES_REFRESH',
                        physical_schema_hash = NULL
                    WHERE id = NEW.ds_id;
                END IF;
                RETURN NEW;
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_core_table_legacy_catalog_keys
            BEFORE INSERT OR UPDATE ON core_table
            FOR EACH ROW
            EXECUTE FUNCTION fill_legacy_core_table_catalog_keys()
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION fill_legacy_core_field_catalog_key()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $$
            DECLARE
                used_legacy_fallback BOOLEAN := false;
            BEGIN
                IF NEW.field_key IS NULL OR BTRIM(NEW.field_key) = '' THEN
                    NEW.field_key := BTRIM(COALESCE(NEW.field_name, ''));
                    used_legacy_fallback := true;
                END IF;
                IF TG_OP = 'UPDATE'
                   AND NEW.field_name IS DISTINCT FROM OLD.field_name
                   AND NEW.field_key IS NOT DISTINCT FROM OLD.field_key THEN
                    NEW.field_key := BTRIM(COALESCE(NEW.field_name, ''));
                    used_legacy_fallback := true;
                END IF;
                IF NEW.field_key = '' THEN
                    RAISE EXCEPTION '字段名不能为空，无法生成目录键';
                END IF;
                IF used_legacy_fallback THEN
                    UPDATE core_datasource
                    SET catalog_complete = false,
                        catalog_incomplete_reason = 'LEGACY_CATALOG_REQUIRES_REFRESH',
                        physical_schema_hash = NULL
                    WHERE id = NEW.ds_id;
                END IF;
                RETURN NEW;
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_core_field_legacy_catalog_keys
            BEFORE INSERT OR UPDATE ON core_field
            FOR EACH ROW
            EXECUTE FUNCTION fill_legacy_core_field_catalog_key()
            """
        )
    )


def _create_catalog_invalidation_guards() -> None:
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION invalidate_core_datasource_catalog()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    UPDATE core_datasource
                    SET catalog_complete = false,
                        catalog_incomplete_reason = 'LEGACY_CATALOG_REQUIRES_REFRESH',
                        physical_schema_hash = NULL
                    WHERE id = OLD.ds_id;
                ELSIF TG_OP = 'INSERT' THEN
                    UPDATE core_datasource
                    SET catalog_complete = false,
                        catalog_incomplete_reason = 'LEGACY_CATALOG_REQUIRES_REFRESH',
                        physical_schema_hash = NULL
                    WHERE id = NEW.ds_id;
                ELSE
                    UPDATE core_datasource
                    SET catalog_complete = false,
                        catalog_incomplete_reason = 'LEGACY_CATALOG_REQUIRES_REFRESH',
                        physical_schema_hash = NULL
                    WHERE id IN (OLD.ds_id, NEW.ds_id);
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
            CREATE TRIGGER trg_core_table_catalog_invalidation
            AFTER INSERT OR UPDATE OR DELETE ON core_table
            FOR EACH ROW
            EXECUTE FUNCTION invalidate_core_datasource_catalog()
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_core_field_catalog_invalidation
            AFTER INSERT OR UPDATE OR DELETE ON core_field
            FOR EACH ROW
            EXECUTE FUNCTION invalidate_core_datasource_catalog()
            """
        )
    )


def _create_semantic_scope_epoch() -> None:
    op.create_table(
        "semantic_scope_epoch",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("datasource_id", sa.BigInteger(), nullable=True),
        sa.Column("subject_id", sa.BigInteger(), nullable=True),
        sa.Column("epoch", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=False), nullable=True),
        sa.CheckConstraint(
            "scope_type IN ('PERMISSION','SYSTEM_ROLE','MEMBERSHIP',"
            "'DATASOURCE_ACCESS','DATASOURCE_ROLE','TRACKING',"
            "'DATASOURCE_BINDING','SCHEMA')",
            name="ck_semantic_scope_epoch_scope_type",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_semantic_scope_epoch_scope",
        "semantic_scope_epoch",
        [
            "scope_type",
            "tenant_id",
            sa.text("COALESCE(datasource_id, 0)"),
            sa.text("COALESCE(subject_id, 0)"),
        ],
        unique=True,
    )
    op.create_index(
        "idx_semantic_scope_epoch_tenant",
        "semantic_scope_epoch",
        ["tenant_id", "scope_type"],
    )


def upgrade() -> None:
    _add_catalog_columns()
    _backfill_catalog_keys()
    _create_legacy_catalog_write_guards()
    _create_catalog_invalidation_guards()
    _create_semantic_scope_epoch()


def downgrade() -> None:
    op.drop_index(
        "idx_semantic_scope_epoch_tenant",
        table_name="semantic_scope_epoch",
    )
    op.drop_index(
        "uq_semantic_scope_epoch_scope",
        table_name="semantic_scope_epoch",
    )
    op.drop_table("semantic_scope_epoch")

    op.execute(
        sa.text("DROP TRIGGER IF EXISTS trg_core_field_catalog_invalidation ON core_field")
    )
    op.execute(
        sa.text("DROP TRIGGER IF EXISTS trg_core_table_catalog_invalidation ON core_table")
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS invalidate_core_datasource_catalog()"))

    op.execute(
        sa.text("DROP TRIGGER IF EXISTS trg_core_field_legacy_catalog_keys ON core_field")
    )
    op.execute(
        sa.text("DROP FUNCTION IF EXISTS fill_legacy_core_field_catalog_key()")
    )
    op.execute(
        sa.text("DROP TRIGGER IF EXISTS trg_core_table_legacy_catalog_keys ON core_table")
    )
    op.execute(
        sa.text("DROP FUNCTION IF EXISTS fill_legacy_core_table_catalog_keys()")
    )

    op.drop_constraint(
        "uq_core_field_full_identity",
        "core_field",
        type_="unique",
    )
    op.drop_column("core_field", "field_key")

    op.drop_constraint(
        "uq_core_table_full_identity",
        "core_table",
        type_="unique",
    )
    for column in (
        "table_key",
        "schema_key",
        "catalog_key",
        "schema_name",
        "catalog_name",
    ):
        op.drop_column("core_table", column)

    op.drop_constraint(
        "ck_core_datasource_catalog_complete_hash",
        "core_datasource",
        type_="check",
    )
    for column in (
        "physical_schema_hash",
        "catalog_incomplete_reason",
        "catalog_complete",
    ):
        op.drop_column("core_datasource", column)
