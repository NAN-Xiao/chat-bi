"""Track the user-maintained document block behind each retrieval chunk.

Revision ID: 156knowledgedocblock
Revises: 155semanticpermepoch
"""

from alembic import op
import sqlalchemy as sa


revision = "156knowledgedocblock"
down_revision = "155semanticpermepoch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_base_chunk",
        sa.Column("source_block_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "idx_knowledge_base_chunk_source_block",
        "knowledge_base_chunk",
        ["version_id", "source_block_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_knowledge_base_chunk_source_block", table_name="knowledge_base_chunk")
    op.drop_column("knowledge_base_chunk", "source_block_id")
