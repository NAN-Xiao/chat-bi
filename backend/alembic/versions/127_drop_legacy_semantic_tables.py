"""127_drop_legacy_semantic_tables

Revision ID: e7c9f1a3b5d6
Revises: c4d8f2a6b901
Create Date: 2026-06-26 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import pgvector
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e7c9f1a3b5d6"
down_revision = "c4d8f2a6b901"
branch_labels = None
depends_on = None


def _bind():
    return op.get_bind()


def _inspector():
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def upgrade() -> None:
    if _has_table("task_queue") and _has_column("task_queue", "task_name"):
        op.execute(
            """
            DELETE FROM task_queue
            WHERE task_name IN (
                'terminology.embedding',
                'terminology.fill_empty_embedding',
                'data_training.embedding',
                'data_training.fill_empty_embedding'
            )
            """
        )

    if _has_table("data_training"):
        op.drop_table("data_training")
    if _has_table("terminology"):
        op.drop_table("terminology")


def downgrade() -> None:
    if not _has_table("terminology"):
        op.create_table(
            "terminology",
            sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default="1"),
            sa.Column("scope", sa.String(length=32), nullable=False, server_default="TENANT"),
            sa.Column("pid", sa.BigInteger(), nullable=True),
            sa.Column("create_time", sa.DateTime(timezone=False), nullable=True),
            sa.Column("word", sa.String(length=255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(), nullable=True),
            sa.Column("specific_ds", sa.Boolean(), nullable=True),
            sa.Column("datasource_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=True),
        )

    if not _has_table("data_training"):
        op.create_table(
            "data_training",
            sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default="1"),
            sa.Column("scope", sa.String(length=32), nullable=False, server_default="TENANT"),
            sa.Column("datasource", sa.BigInteger(), nullable=True),
            sa.Column("create_time", sa.DateTime(timezone=False), nullable=True),
            sa.Column("question", sa.String(length=255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=True),
            sa.Column("advanced_application", sa.BigInteger(), nullable=True),
        )
