"""126_custom_prompt_visible

Revision ID: c4d8f2a6b901
Revises: 8e3f5a7b9c01
Create Date: 2026-06-25 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c4d8f2a6b901"
down_revision = "8e3f5a7b9c01"
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
    if _has_table("custom_prompt") and not _has_column("custom_prompt", "visible"):
        op.add_column(
            "custom_prompt",
            sa.Column("visible", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )


def downgrade() -> None:
    if _has_table("custom_prompt") and _has_column("custom_prompt", "visible"):
        op.drop_column("custom_prompt", "visible")
