"""128_workspace_tracking_metadata

Revision ID: a5f2d8c9e7b1
Revises: e7c9f1a3b5d6
Create Date: 2026-06-26 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a5f2d8c9e7b1"
down_revision = "e7c9f1a3b5d6"
branch_labels = None
depends_on = None


def _bind():
    return op.get_bind()


def _inspector():
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def upgrade() -> None:
    if not _has_table("sys_tenant_tracking_config"):
        op.create_table(
            "sys_tenant_tracking_config",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("default_event_table", sa.String(length=255), nullable=True),
            sa.Column("default_subject_field", sa.String(length=255), nullable=True),
            sa.Column("default_event_name_field", sa.String(length=255), nullable=True),
            sa.Column("default_event_time_field", sa.String(length=255), nullable=True),
            sa.Column("field_role_mappings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("event_name_mappings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("sql_rules", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("create_by", sa.BigInteger(), nullable=True),
            sa.Column("update_by", sa.BigInteger(), nullable=True),
            sa.Column("create_time", sa.BigInteger(), nullable=False),
            sa.Column("update_time", sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", name="uq_sys_tenant_tracking_config_tenant_id"),
        )
    if not _has_index("sys_tenant_tracking_config", "idx_sys_tenant_tracking_config_tenant_id"):
        op.create_index(
            "idx_sys_tenant_tracking_config_tenant_id",
            "sys_tenant_tracking_config",
            ["tenant_id"],
        )

    if not _has_table("sys_tenant_tracking_table"):
        op.create_table(
            "sys_tenant_tracking_table",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("table_name", sa.String(length=255), nullable=False),
            sa.Column("table_comment", sa.Text(), nullable=True),
            sa.Column("table_role", sa.String(length=64), nullable=True),
            sa.Column("aliases", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("ai_notes", sa.Text(), nullable=True),
            sa.Column("create_by", sa.BigInteger(), nullable=True),
            sa.Column("update_by", sa.BigInteger(), nullable=True),
            sa.Column("create_time", sa.BigInteger(), nullable=False),
            sa.Column("update_time", sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "table_name", name="uq_sys_tenant_tracking_table_name"),
        )
    if not _has_index("sys_tenant_tracking_table", "idx_sys_tenant_tracking_table_tenant_id"):
        op.create_index(
            "idx_sys_tenant_tracking_table_tenant_id",
            "sys_tenant_tracking_table",
            ["tenant_id"],
        )

    if not _has_table("sys_tenant_tracking_field"):
        op.create_table(
            "sys_tenant_tracking_field",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("table_name", sa.String(length=255), nullable=False),
            sa.Column("field_name", sa.String(length=255), nullable=False),
            sa.Column("field_comment", sa.Text(), nullable=True),
            sa.Column("field_role", sa.String(length=64), nullable=True),
            sa.Column("semantic_type", sa.String(length=64), nullable=True),
            sa.Column("aliases", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("value_mappings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("expression", sa.Text(), nullable=True),
            sa.Column("required", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("example_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("ai_notes", sa.Text(), nullable=True),
            sa.Column("create_by", sa.BigInteger(), nullable=True),
            sa.Column("update_by", sa.BigInteger(), nullable=True),
            sa.Column("create_time", sa.BigInteger(), nullable=False),
            sa.Column("update_time", sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id",
                "table_name",
                "field_name",
                name="uq_sys_tenant_tracking_field_name",
            ),
        )
    if not _has_index("sys_tenant_tracking_field", "idx_sys_tenant_tracking_field_tenant_id"):
        op.create_index(
            "idx_sys_tenant_tracking_field_tenant_id",
            "sys_tenant_tracking_field",
            ["tenant_id"],
        )
    if not _has_index("sys_tenant_tracking_field", "idx_sys_tenant_tracking_field_table"):
        op.create_index(
            "idx_sys_tenant_tracking_field_table",
            "sys_tenant_tracking_field",
            ["tenant_id", "table_name"],
        )


def downgrade() -> None:
    if _has_index("sys_tenant_tracking_field", "idx_sys_tenant_tracking_field_table"):
        op.drop_index("idx_sys_tenant_tracking_field_table", table_name="sys_tenant_tracking_field")
    if _has_index("sys_tenant_tracking_field", "idx_sys_tenant_tracking_field_tenant_id"):
        op.drop_index("idx_sys_tenant_tracking_field_tenant_id", table_name="sys_tenant_tracking_field")
    if _has_table("sys_tenant_tracking_field"):
        op.drop_table("sys_tenant_tracking_field")

    if _has_index("sys_tenant_tracking_table", "idx_sys_tenant_tracking_table_tenant_id"):
        op.drop_index("idx_sys_tenant_tracking_table_tenant_id", table_name="sys_tenant_tracking_table")
    if _has_table("sys_tenant_tracking_table"):
        op.drop_table("sys_tenant_tracking_table")

    if _has_index("sys_tenant_tracking_config", "idx_sys_tenant_tracking_config_tenant_id"):
        op.drop_index("idx_sys_tenant_tracking_config_tenant_id", table_name="sys_tenant_tracking_config")
    if _has_table("sys_tenant_tracking_config"):
        op.drop_table("sys_tenant_tracking_config")
