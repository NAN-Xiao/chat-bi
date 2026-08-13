"""Add the workspace-level ROI project identifier.

Revision ID: 157workspaceprojectid
Revises: 156knowledgedocblock
"""

import sqlalchemy as sa

from alembic import op

revision = "157workspaceprojectid"
down_revision = "156knowledgedocblock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sys_tenant",
        sa.Column("roi_project_id", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sys_tenant", "roi_project_id")
