"""132_custom_prompt_skill_embedding

Revision ID: e8c1f4a6b9d2
Revises: d4f7a9c2e1b3
Create Date: 2026-06-27 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e8c1f4a6b9d2"
down_revision = "d4f7a9c2e1b3"
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
    if not _has_table("custom_prompt"):
        return
    if not _has_column("custom_prompt", "embedding"):
        op.add_column("custom_prompt", sa.Column("embedding", sa.Text(), nullable=True))
    if not _has_column("custom_prompt", "embedding_signature"):
        op.add_column("custom_prompt", sa.Column("embedding_signature", sa.String(length=128), nullable=True))


def downgrade() -> None:
    if not _has_table("custom_prompt"):
        return
    if _has_column("custom_prompt", "embedding_signature"):
        op.drop_column("custom_prompt", "embedding_signature")
    if _has_column("custom_prompt", "embedding"):
        op.drop_column("custom_prompt", "embedding")
