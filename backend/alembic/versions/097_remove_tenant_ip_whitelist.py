"""迁移脚本：097_remove_tenant_ip_whitelist

迁移版本 ID： a8b9c0d1e2f3
上一版本： f7a8b9c0d1e2
创建时间： 2026-06-19 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "a8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/097_remove_tenant_ip_whitelist.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/097_remove_tenant_ip_whitelist.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/097_remove_tenant_ip_whitelist.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    table_name = "sys_tenant_security_policy"
    column_name = "ip_whitelist"
    if _has_table(table_name) and _has_column(table_name, column_name):
        op.drop_column(table_name, column_name)


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/097_remove_tenant_ip_whitelist.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    table_name = "sys_tenant_security_policy"
    column_name = "ip_whitelist"
    if _has_table(table_name) and not _has_column(table_name, column_name):
        op.add_column(table_name, sa.Column(column_name, sa.Text(), nullable=True))
