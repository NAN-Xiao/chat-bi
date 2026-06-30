"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c86d2f9a31b4"
down_revision = "a75d8e3c91bf"
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


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def upgrade():
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    if not _has_table("core_dashboard"):
        return

    if not _has_column("core_dashboard", "is_default"):
        op.add_column(
            "core_dashboard",
            sa.Column("is_default", sa.SmallInteger(), nullable=False, server_default="0"),
        )

    if not _has_index("core_dashboard", "idx_core_dashboard_default_tenant"):
        op.create_index(
            "idx_core_dashboard_default_tenant",
            "core_dashboard",
            ["tenant_id", "is_default"],
            unique=False,
        )


def downgrade():
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    if not _has_table("core_dashboard"):
        return

    if _has_index("core_dashboard", "idx_core_dashboard_default_tenant"):
        op.drop_index("idx_core_dashboard_default_tenant", table_name="core_dashboard")
    if _has_column("core_dashboard", "is_default"):
        op.drop_column("core_dashboard", "is_default")
