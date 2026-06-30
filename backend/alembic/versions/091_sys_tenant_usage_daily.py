"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa


revision = "a2b3c4d5e6f7"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
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
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    if not _has_table("sys_tenant_usage_daily"):
        return
    if _has_index("sys_tenant_usage_daily", "idx_sys_tenant_usage_daily_metric"):
        op.drop_index("idx_sys_tenant_usage_daily_metric", table_name="sys_tenant_usage_daily")
    if _has_index("sys_tenant_usage_daily", "idx_sys_tenant_usage_daily_tenant_date"):
        op.drop_index("idx_sys_tenant_usage_daily_tenant_date", table_name="sys_tenant_usage_daily")
    op.drop_table("sys_tenant_usage_daily")
