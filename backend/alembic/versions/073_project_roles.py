"""073_project_roles

Revision ID: c3d4e5f6a7b8
Revises: f2a4b6c8d0e1
Create Date: 2026-06-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'f2a4b6c8d0e1'
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
    if not _has_column('core_datasource_user', 'role'):
        op.add_column(
            'core_datasource_user',
            sa.Column('role', sa.String(length=32), nullable=False, server_default='viewer'),
        )
    op.execute("UPDATE core_datasource_user SET role = 'viewer' WHERE role IS NULL OR role = ''")


def downgrade():
    if _has_column('core_datasource_user', 'role'):
        op.drop_column('core_datasource_user', 'role')
