"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
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
    是什么：_bind 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移相关的信息改成最新状态，并保存这些变化。
    """
    return op.get_bind()


def _inspector():
    """
    是什么：_inspector 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _has_unique_constraint(table_name: str, constraint_name: str) -> bool:
    """
    是什么：_has_unique_constraint 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not _has_table(table_name):
        return False
    return any(
        constraint["name"] == constraint_name
        for constraint in _inspector().get_unique_constraints(table_name)
    )


def upgrade() -> None:
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
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
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    if not _has_table("sys_tenant") or not _has_column("sys_tenant", "public_id"):
        return
    if _has_unique_constraint("sys_tenant", "uq_sys_tenant_public_id"):
        op.drop_constraint("uq_sys_tenant_public_id", "sys_tenant", type_="unique")
    op.drop_column("sys_tenant", "public_id")
