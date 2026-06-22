"""111_analysis_assistant_conversation

Revision ID: c9d12e7f4a6b
Revises: b62f1a4d8c93
Create Date: 2026-06-22 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c9d12e7f4a6b"
down_revision = "b62f1a4d8c93"
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
    if not _has_table("analysis_assistant_conversation"):
        op.create_table(
            "analysis_assistant_conversation",
            sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), server_default="1", nullable=False),
            sa.Column("create_by", sa.BigInteger(), nullable=False),
            sa.Column("title", sa.String(length=128), server_default="", nullable=False),
            sa.Column("datasource_id", sa.BigInteger(), nullable=True),
            sa.Column("datasource_name", sa.String(length=255), nullable=True),
            sa.Column("custom_prompt_id", sa.BigInteger(), nullable=True),
            sa.Column("data_skill_id", sa.BigInteger(), nullable=True),
            sa.Column("messages", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
            sa.Column("create_time", sa.DateTime(timezone=False), nullable=False),
            sa.Column("update_time", sa.DateTime(timezone=False), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _has_index("analysis_assistant_conversation", "idx_analysis_assistant_conversation_tenant_user"):
        op.create_index(
            "idx_analysis_assistant_conversation_tenant_user",
            "analysis_assistant_conversation",
            ["tenant_id", "create_by"],
        )
    if not _has_index("analysis_assistant_conversation", "idx_analysis_assistant_conversation_datasource"):
        op.create_index(
            "idx_analysis_assistant_conversation_datasource",
            "analysis_assistant_conversation",
            ["datasource_id"],
        )
    if not _has_index("analysis_assistant_conversation", "idx_analysis_assistant_conversation_update_time"):
        op.create_index(
            "idx_analysis_assistant_conversation_update_time",
            "analysis_assistant_conversation",
            ["update_time"],
        )


def downgrade() -> None:
    if not _has_table("analysis_assistant_conversation"):
        return
    for index_name in (
        "idx_analysis_assistant_conversation_update_time",
        "idx_analysis_assistant_conversation_datasource",
        "idx_analysis_assistant_conversation_tenant_user",
    ):
        if _has_index("analysis_assistant_conversation", index_name):
            op.drop_index(index_name, table_name="analysis_assistant_conversation")
    op.drop_table("analysis_assistant_conversation")
