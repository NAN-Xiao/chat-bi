"""074_user_system_roles

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
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
    if not _has_column('sys_user', 'system_role'):
        op.add_column(
            'sys_user',
            sa.Column('system_role', sa.String(length=32), nullable=False, server_default='viewer'),
        )
    op.execute("UPDATE sys_user SET system_role = 'viewer' WHERE system_role IS NULL OR system_role = ''")
    op.execute("UPDATE sys_user SET system_role = 'system_admin' WHERE account = 'admin'")


def downgrade():
    if _has_column('sys_user', 'system_role'):
        op.drop_column('sys_user', 'system_role')
