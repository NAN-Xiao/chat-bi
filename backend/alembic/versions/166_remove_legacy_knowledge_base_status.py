"""Remove the legacy knowledge-base processing state columns."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "166removelegacykbstate"
down_revision = "165mergerelease1into2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_knowledge_base_status", table_name="knowledge_base")
    op.drop_column("knowledge_base", "error_message")
    op.drop_column("knowledge_base", "task_id")
    op.drop_column("knowledge_base", "status")


def downgrade() -> None:
    op.add_column(
        "knowledge_base",
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=True,
        ),
    )
    op.add_column(
        "knowledge_base",
        sa.Column("task_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "knowledge_base",
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_knowledge_base_status",
        "knowledge_base",
        ["status"],
    )
