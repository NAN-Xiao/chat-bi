"""迁移脚本：089_sys_logs_tenant_scope

迁移版本 ID： e9f0a1b2c3d4
上一版本： d8e9f0a1b2c3
创建时间： 2026-06-18 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "e9f0a1b2c3d4"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None

DEFAULT_TENANT_ID = 1


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/089_sys_logs_tenant_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/089_sys_logs_tenant_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是 backend/alembic/versions/089_sys_logs_tenant_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_index 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/089_sys_logs_tenant_scope.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
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
    """
    是什么：downgrade 是 backend/alembic/versions/089_sys_logs_tenant_scope.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table("sys_logs"):
        return
    if _has_index("sys_logs", "idx_sys_logs_tenant_id"):
        op.drop_index("idx_sys_logs_tenant_id", table_name="sys_logs")
    if _has_column("sys_logs", "tenant_id"):
        op.drop_column("sys_logs", "tenant_id")
