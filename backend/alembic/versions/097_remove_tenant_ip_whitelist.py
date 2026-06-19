"""097_remove_tenant_ip_whitelist

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-06-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "a8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade():
    table_name = "sys_tenant_security_policy"
    column_name = "ip_whitelist"
    if _has_table(table_name) and _has_column(table_name, column_name):
        op.drop_column(table_name, column_name)


def downgrade():
    table_name = "sys_tenant_security_policy"
    column_name = "ip_whitelist"
    if _has_table(table_name) and not _has_column(table_name, column_name):
        op.add_column(table_name, sa.Column(column_name, sa.Text(), nullable=True))
