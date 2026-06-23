"""123_remove_user_knowledge_base

Revision ID: 6c9d2e4f8a10
Revises: 2f4a6c8e0b13
Create Date: 2026-06-23 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "6c9d2e4f8a10"
down_revision = "2f4a6c8e0b13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM knowledge_base WHERE visibility_scope = 'USER_PRIVATE'")
    op.alter_column(
        "knowledge_base",
        "visibility_scope",
        existing_type=sa.String(length=32),
        server_default="ADMIN_PUBLIC",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "knowledge_base",
        "visibility_scope",
        existing_type=sa.String(length=32),
        server_default="USER_PRIVATE",
        existing_nullable=False,
    )
