"""迁移脚本：109_remove_tenant_code

迁移版本 ID： a7d8f0c9b2e1
上一版本： f30c9a2e8b71
创建时间： 2026-06-22 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a7d8f0c9b2e1"
down_revision = "f30c9a2e8b71"
branch_labels = None
depends_on = None


def _bind():
    """
    是什么：_bind 是 backend/alembic/versions/109_remove_tenant_code.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：更新数据库迁移相关状态、配置或持久化数据，并保持后续流程可继续使用。
    """
    return op.get_bind()


def _inspector():
    """
    是什么：_inspector 是 backend/alembic/versions/109_remove_tenant_code.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _inspector 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/109_remove_tenant_code.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/109_remove_tenant_code.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是 backend/alembic/versions/109_remove_tenant_code.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_index 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _has_unique_constraint(table_name: str, constraint_name: str) -> bool:
    """
    是什么：_has_unique_constraint 是 backend/alembic/versions/109_remove_tenant_code.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_unique_constraint 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return any(
        constraint["name"] == constraint_name
        for constraint in _inspector().get_unique_constraints(table_name)
    )


def upgrade() -> None:
    """
    是什么：upgrade 是 backend/alembic/versions/109_remove_tenant_code.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if _has_table("sys_tenant_application"):
        if _has_index("sys_tenant_application", "idx_sys_tenant_application_tenant_code"):
            op.drop_index("idx_sys_tenant_application_tenant_code", table_name="sys_tenant_application")
        if _has_column("sys_tenant_application", "tenant_code"):
            op.drop_column("sys_tenant_application", "tenant_code")

    if _has_table("sys_tenant"):
        if _has_unique_constraint("sys_tenant", "uq_sys_tenant_code"):
            op.drop_constraint("uq_sys_tenant_code", "sys_tenant", type_="unique")
        if _has_column("sys_tenant", "code"):
            op.drop_column("sys_tenant", "code")


def downgrade() -> None:
    """
    是什么：downgrade 是 backend/alembic/versions/109_remove_tenant_code.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if _has_table("sys_tenant") and not _has_column("sys_tenant", "code"):
        op.add_column("sys_tenant", sa.Column("code", sa.String(length=64), nullable=True))
        op.execute("UPDATE sys_tenant SET code = 'tenant-' || id::text WHERE code IS NULL")
        op.alter_column("sys_tenant", "code", existing_type=sa.String(length=64), nullable=False)
        if not _has_unique_constraint("sys_tenant", "uq_sys_tenant_code"):
            op.create_unique_constraint("uq_sys_tenant_code", "sys_tenant", ["code"])

    if _has_table("sys_tenant_application") and not _has_column("sys_tenant_application", "tenant_code"):
        op.add_column("sys_tenant_application", sa.Column("tenant_code", sa.String(length=64), nullable=True))
        op.execute(
            "UPDATE sys_tenant_application SET tenant_code = COALESCE("
            "(SELECT code FROM sys_tenant WHERE sys_tenant.id = sys_tenant_application.tenant_id), '')"
        )
        op.alter_column(
            "sys_tenant_application",
            "tenant_code",
            existing_type=sa.String(length=64),
            nullable=False,
        )
        if not _has_index("sys_tenant_application", "idx_sys_tenant_application_tenant_code"):
            op.create_index(
                "idx_sys_tenant_application_tenant_code",
                "sys_tenant_application",
                ["tenant_code"],
            )
