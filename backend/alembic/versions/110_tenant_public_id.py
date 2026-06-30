"""迁移脚本：110_tenant_public_id

迁移版本 ID： b62f1a4d8c93
上一版本： a7d8f0c9b2e1
创建时间： 2026-06-22 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b62f1a4d8c93"
down_revision = "a7d8f0c9b2e1"
branch_labels = None
depends_on = None


def _bind():
    """
    是什么：_bind 是 backend/alembic/versions/110_tenant_public_id.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：更新数据库迁移相关状态、配置或持久化数据，并保持后续流程可继续使用。
    """
    return op.get_bind()


def _inspector():
    """
    是什么：_inspector 是 backend/alembic/versions/110_tenant_public_id.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _inspector 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/110_tenant_public_id.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/110_tenant_public_id.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _has_unique_constraint(table_name: str, constraint_name: str) -> bool:
    """
    是什么：_has_unique_constraint 是 backend/alembic/versions/110_tenant_public_id.py 中的同步函数。
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
    是什么：upgrade 是 backend/alembic/versions/110_tenant_public_id.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table("sys_tenant"):
        return
    if not _has_column("sys_tenant", "public_id"):
        op.add_column("sys_tenant", sa.Column("public_id", sa.String(length=32), nullable=True))
    op.execute(
        """
        UPDATE sys_tenant
        SET public_id = 'WS'
            || upper(to_hex(id::bigint))
            || upper(substr(md5(id::text || ':' || coalesce(name, '') || ':' || coalesce(create_time::text, '')), 1, 4))
            || '2'
        WHERE public_id IS NULL OR btrim(public_id) = ''
        """
    )
    op.alter_column("sys_tenant", "public_id", existing_type=sa.String(length=32), nullable=False)
    if not _has_unique_constraint("sys_tenant", "uq_sys_tenant_public_id"):
        op.create_unique_constraint("uq_sys_tenant_public_id", "sys_tenant", ["public_id"])


def downgrade() -> None:
    """
    是什么：downgrade 是 backend/alembic/versions/110_tenant_public_id.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table("sys_tenant") or not _has_column("sys_tenant", "public_id"):
        return
    if _has_unique_constraint("sys_tenant", "uq_sys_tenant_public_id"):
        op.drop_constraint("uq_sys_tenant_public_id", "sys_tenant", type_="unique")
    op.drop_column("sys_tenant", "public_id")
