"""迁移脚本：094_platform_semantic_foundation_scope

迁移版本 ID： d5e6f7a8b9c0
上一版本： c4d5e6f7a8b9
创建时间： 2026-06-18 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/094_platform_semantic_foundation_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/094_platform_semantic_foundation_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是 backend/alembic/versions/094_platform_semantic_foundation_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_index 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _add_scope_column(table_name: str, index_name: str) -> None:
    """
    是什么：_add_scope_column 是 backend/alembic/versions/094_platform_semantic_foundation_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：创建、初始化或组装数据库迁移相关对象和数据，并返回或写入对应状态。
    """
    if not _has_table(table_name):
        return
    if not _has_column(table_name, "scope"):
        op.add_column(
            table_name,
            sa.Column("scope", sa.String(length=32), nullable=False, server_default="TENANT"),
        )
    else:
        op.execute(
            f"""
            UPDATE {table_name}
            SET scope = 'TENANT'
            WHERE scope IS NULL OR scope NOT IN ('TENANT', 'PLATFORM')
            """
        )
        op.alter_column(
            table_name,
            "scope",
            existing_type=sa.String(length=32),
            nullable=False,
            server_default="TENANT",
        )
    if not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, ["scope"])


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/094_platform_semantic_foundation_scope.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    _add_scope_column("terminology", "idx_terminology_scope")
    _add_scope_column("data_training", "idx_data_training_scope")


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/094_platform_semantic_foundation_scope.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    for table_name, index_name in (
        ("data_training", "idx_data_training_scope"),
        ("terminology", "idx_terminology_scope"),
    ):
        if not _has_table(table_name):
            continue
        if _has_index(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
        if _has_column(table_name, "scope"):
            op.drop_column(table_name, "scope")
