"""089_sys_logs_tenant_scope

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-06-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "e9f0a1b2c3d4"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None

DEFAULT_TENANT_ID = 1


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    if not _has_table("sys_logs"):
        return

    if not _has_column("sys_logs", "tenant_id"):
        op.add_column(
            "sys_logs",
            sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default=str(DEFAULT_TENANT_ID)),
        )
    op.execute(
        f"""
        UPDATE sys_logs
        SET tenant_id = {DEFAULT_TENANT_ID}
        WHERE tenant_id IS NULL
        """
    )
    if not _has_index("sys_logs", "idx_sys_logs_tenant_id"):
        op.create_index("idx_sys_logs_tenant_id", "sys_logs", ["tenant_id"])


def downgrade():
    if not _has_table("sys_logs"):
        return
    if _has_index("sys_logs", "idx_sys_logs_tenant_id"):
        op.drop_index("idx_sys_logs_tenant_id", table_name="sys_logs")
    if _has_column("sys_logs", "tenant_id"):
        op.drop_column("sys_logs", "tenant_id")
