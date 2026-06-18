"""091_sys_tenant_usage_daily

Revision ID: a1b2c3d4e5f6
Revises: f0a1b2c3d4e5
Create Date: 2026-06-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    if not _has_table("sys_tenant_usage_daily"):
        op.create_table(
            "sys_tenant_usage_daily",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("usage_date", sa.String(length=10), nullable=False),
            sa.Column("metric", sa.String(length=128), nullable=False),
            sa.Column("request_count", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("success_count", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("failure_count", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("total_tokens", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("task_count", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("create_time", sa.BigInteger(), nullable=False),
            sa.Column("update_time", sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "usage_date", "metric", name="uq_sys_tenant_usage_daily_key"),
        )
    if not _has_index("sys_tenant_usage_daily", "idx_sys_tenant_usage_daily_tenant_date"):
        op.create_index(
            "idx_sys_tenant_usage_daily_tenant_date",
            "sys_tenant_usage_daily",
            ["tenant_id", "usage_date"],
        )
    if not _has_index("sys_tenant_usage_daily", "idx_sys_tenant_usage_daily_metric"):
        op.create_index("idx_sys_tenant_usage_daily_metric", "sys_tenant_usage_daily", ["metric"])


def downgrade():
    if not _has_table("sys_tenant_usage_daily"):
        return
    if _has_index("sys_tenant_usage_daily", "idx_sys_tenant_usage_daily_metric"):
        op.drop_index("idx_sys_tenant_usage_daily_metric", table_name="sys_tenant_usage_daily")
    if _has_index("sys_tenant_usage_daily", "idx_sys_tenant_usage_daily_tenant_date"):
        op.drop_index("idx_sys_tenant_usage_daily_tenant_date", table_name="sys_tenant_usage_daily")
    op.drop_table("sys_tenant_usage_daily")
