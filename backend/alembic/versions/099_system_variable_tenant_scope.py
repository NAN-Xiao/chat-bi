"""迁移脚本：099_system_variable_tenant_scope

迁移版本 ID： c0d1e2f3a4b5
上一版本： b9c0d1e2f3a4
创建时间： 2026-06-19 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None

DEFAULT_TENANT_ID = 1


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/099_system_variable_tenant_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/099_system_variable_tenant_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是 backend/alembic/versions/099_system_variable_tenant_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_index 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/099_system_variable_tenant_scope.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    table_name = "system_variable"
    column_name = "tenant_id"
    if not _has_table(table_name):
        return
    if not _has_column(table_name, column_name):
        op.add_column(
            table_name,
            sa.Column(
                column_name,
                sa.BigInteger(),
                nullable=False,
                server_default=str(DEFAULT_TENANT_ID),
            ),
        )
    op.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET tenant_id = :tenant_id
            WHERE tenant_id IS NULL
            """
        ).bindparams(tenant_id=DEFAULT_TENANT_ID)
    )
    if not _has_index(table_name, "idx_system_variable_tenant_id"):
        op.create_index("idx_system_variable_tenant_id", table_name, ["tenant_id"])


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/099_system_variable_tenant_scope.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    table_name = "system_variable"
    column_name = "tenant_id"
    if not _has_table(table_name):
        return
    if _has_index(table_name, "idx_system_variable_tenant_id"):
        op.drop_index("idx_system_variable_tenant_id", table_name=table_name)
    if _has_column(table_name, column_name):
        op.drop_column(table_name, column_name)
