"""迁移脚本：091_sys_tenant_usage_daily

迁移版本 ID： a2b3c4d5e6f7
上一版本： f0a1b2c3d4e5
创建时间： 2026-06-18 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "a2b3c4d5e6f7"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/091_sys_tenant_usage_daily.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是 backend/alembic/versions/091_sys_tenant_usage_daily.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_index 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/091_sys_tenant_usage_daily.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
    是什么：downgrade 是 backend/alembic/versions/091_sys_tenant_usage_daily.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table("sys_tenant_usage_daily"):
        return
    if _has_index("sys_tenant_usage_daily", "idx_sys_tenant_usage_daily_metric"):
        op.drop_index("idx_sys_tenant_usage_daily_metric", table_name="sys_tenant_usage_daily")
    if _has_index("sys_tenant_usage_daily", "idx_sys_tenant_usage_daily_tenant_date"):
        op.drop_index("idx_sys_tenant_usage_daily_tenant_date", table_name="sys_tenant_usage_daily")
    op.drop_table("sys_tenant_usage_daily")
