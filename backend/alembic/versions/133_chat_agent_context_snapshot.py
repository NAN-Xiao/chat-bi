"""133_chat_agent_context_snapshot

Revision ID: f3a9d2c7b6e1
Revises: e8c1f4a6b9d2
Create Date: 2026-06-28 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f3a9d2c7b6e1"
down_revision = "e8c1f4a6b9d2"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return column_name in {column["name"] for column in _inspector().get_columns(table_name)}


def upgrade() -> None:
    if not _has_table("chat_record"):
        return
    if not _has_column("chat_record", "agent_context_snapshot"):
        op.add_column(
            "chat_record",
            sa.Column("agent_context_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )


def downgrade() -> None:
    if _has_table("chat_record") and _has_column("chat_record", "agent_context_snapshot"):
        op.drop_column("chat_record", "agent_context_snapshot")
