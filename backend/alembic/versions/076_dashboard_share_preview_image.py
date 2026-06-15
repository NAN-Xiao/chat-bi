"""076_dashboard_share_preview_image

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade():
    if _has_table('core_dashboard_share') and not _has_column('core_dashboard_share', 'preview_image'):
        op.add_column('core_dashboard_share', sa.Column('preview_image', sa.Text(), nullable=True))


def downgrade():
    if _has_table('core_dashboard_share') and _has_column('core_dashboard_share', 'preview_image'):
        op.drop_column('core_dashboard_share', 'preview_image')
