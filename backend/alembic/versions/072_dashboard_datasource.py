"""072_dashboard_datasource

Revision ID: f2a4b6c8d0e1
Revises: d9e0f1a2b3c4
Create Date: 2026-06-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2a4b6c8d0e1'
down_revision = 'd9e0f1a2b3c4'
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    if not _has_column('core_dashboard', 'datasource'):
        op.add_column('core_dashboard', sa.Column('datasource', sa.BigInteger(), nullable=True))
    if not _has_index('core_dashboard', 'idx_core_dashboard_datasource'):
        op.create_index('idx_core_dashboard_datasource', 'core_dashboard', ['datasource'], unique=False)


def downgrade():
    if _has_index('core_dashboard', 'idx_core_dashboard_datasource'):
        op.drop_index('idx_core_dashboard_datasource', table_name='core_dashboard')
    if _has_column('core_dashboard', 'datasource'):
        op.drop_column('core_dashboard', 'datasource')
