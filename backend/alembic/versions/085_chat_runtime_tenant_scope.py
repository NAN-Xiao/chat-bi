"""迁移脚本：085_chat_runtime_tenant_scope

迁移版本 ID： a5b6c7d8e9f0
上一版本： f4c5d6e7f8a9
创建时间： 2026-06-18 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "a5b6c7d8e9f0"
down_revision = "f4c5d6e7f8a9"
branch_labels = None
depends_on = None

DEFAULT_TENANT_ID = 1


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/085_chat_runtime_tenant_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/085_chat_runtime_tenant_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是 backend/alembic/versions/085_chat_runtime_tenant_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_index 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _add_tenant_column(table_name: str, index_name: str) -> None:
    """
    是什么：_add_tenant_column 是 backend/alembic/versions/085_chat_runtime_tenant_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：创建、初始化或组装数据库迁移相关对象和数据，并返回或写入对应状态。
    """
    if not _has_table(table_name):
        return
    if not _has_column(table_name, "tenant_id"):
        op.add_column(
            table_name,
            sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default=str(DEFAULT_TENANT_ID)),
        )
    else:
        op.execute(
            f"""
            UPDATE {table_name}
            SET tenant_id = {DEFAULT_TENANT_ID}
            WHERE tenant_id IS NULL
            """
        )
    if not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, ["tenant_id"])


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/085_chat_runtime_tenant_scope.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    _add_tenant_column("chat", "idx_chat_tenant_id")
    _add_tenant_column("chat_record", "idx_chat_record_tenant_id")
    _add_tenant_column("chat_log", "idx_chat_log_tenant_id")


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/085_chat_runtime_tenant_scope.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    for table_name, index_name in (
        ("chat_log", "idx_chat_log_tenant_id"),
        ("chat_record", "idx_chat_record_tenant_id"),
        ("chat", "idx_chat_tenant_id"),
    ):
        if not _has_table(table_name):
            continue
        if _has_index(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
        if _has_column(table_name, "tenant_id"):
            op.drop_column(table_name, "tenant_id")
