"""075_dashboard_share_store

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    if not _has_table('core_dashboard_share'):
        op.create_table(
            'core_dashboard_share',
            sa.Column('id', sa.String(length=50), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=True),
            sa.Column('datasource', sa.BigInteger(), nullable=True),
            sa.Column('share_type', sa.String(length=32), nullable=False),
            sa.Column('source_dashboard_id', sa.String(length=50), nullable=True),
            sa.Column('source_view_id', sa.String(length=50), nullable=True),
            sa.Column('component_data', sa.Text(), nullable=True),
            sa.Column('canvas_style_data', sa.Text(), nullable=True),
            sa.Column('canvas_view_info', sa.Text(), nullable=True),
            sa.Column('create_time', sa.BigInteger(), nullable=True),
            sa.Column('create_by', sa.String(length=255), nullable=True),
            sa.Column('update_time', sa.BigInteger(), nullable=True),
            sa.Column('update_by', sa.String(length=255), nullable=True),
            sa.Column('delete_flag', sa.SmallInteger(), nullable=True),
            sa.Column('delete_time', sa.BigInteger(), nullable=True),
            sa.Column('delete_by', sa.String(length=255), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
    if not _has_index('core_dashboard_share', 'idx_core_dashboard_share_datasource'):
        op.create_index(
            'idx_core_dashboard_share_datasource',
            'core_dashboard_share',
            ['datasource'],
            unique=False,
        )
    if not _has_index('core_dashboard_share', 'idx_core_dashboard_share_type'):
        op.create_index(
            'idx_core_dashboard_share_type',
            'core_dashboard_share',
            ['share_type'],
            unique=False,
        )


def downgrade():
    if _has_index('core_dashboard_share', 'idx_core_dashboard_share_type'):
        op.drop_index('idx_core_dashboard_share_type', table_name='core_dashboard_share')
    if _has_index('core_dashboard_share', 'idx_core_dashboard_share_datasource'):
        op.drop_index('idx_core_dashboard_share_datasource', table_name='core_dashboard_share')
    if _has_table('core_dashboard_share'):
        op.drop_table('core_dashboard_share')
