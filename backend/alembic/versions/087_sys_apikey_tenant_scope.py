"""迁移脚本：087_sys_apikey_tenant_scope

迁移版本 ID： c7d8e9f0a1b2
上一版本： b6c7d8e9f0a1
创建时间： 2026-06-18 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "c7d8e9f0a1b2"
down_revision = "b6c7d8e9f0a1"
branch_labels = None
depends_on = None

DEFAULT_TENANT_ID = 1


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/087_sys_apikey_tenant_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/087_sys_apikey_tenant_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是 backend/alembic/versions/087_sys_apikey_tenant_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_index 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/087_sys_apikey_tenant_scope.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table("sys_apikey"):
        return
    if not _has_column("sys_apikey", "tenant_id"):
        op.add_column(
            "sys_apikey",
            sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default=str(DEFAULT_TENANT_ID)),
        )
    else:
        op.execute(
            f"""
            UPDATE sys_apikey
            SET tenant_id = {DEFAULT_TENANT_ID}
            WHERE tenant_id IS NULL
            """
        )
    if not _has_index("sys_apikey", "idx_sys_apikey_tenant_uid"):
        op.create_index("idx_sys_apikey_tenant_uid", "sys_apikey", ["tenant_id", "uid"])


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/087_sys_apikey_tenant_scope.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table("sys_apikey"):
        return
    if _has_index("sys_apikey", "idx_sys_apikey_tenant_uid"):
        op.drop_index("idx_sys_apikey_tenant_uid", table_name="sys_apikey")
    if _has_column("sys_apikey", "tenant_id"):
        op.drop_column("sys_apikey", "tenant_id")
