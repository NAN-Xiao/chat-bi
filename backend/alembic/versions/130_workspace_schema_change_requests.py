"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c7e9a2d4f6b8"
down_revision = "b6a4d2f8c9e3"
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


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def upgrade() -> None:
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    if not _has_table("sys_tenant_schema_change_request"):
        op.create_table(
            "sys_tenant_schema_change_request",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("datasource_id", sa.BigInteger(), nullable=True),
            sa.Column("change_type", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("table_name", sa.String(length=255), nullable=False),
            sa.Column("payload", sa.Text(), nullable=True),
            sa.Column("requested_by_user_id", sa.BigInteger(), nullable=False),
            sa.Column("executed_by_user_id", sa.BigInteger(), nullable=True),
            sa.Column("request_comment", sa.Text(), nullable=True),
            sa.Column("execution_comment", sa.Text(), nullable=True),
            sa.Column("create_time", sa.BigInteger(), nullable=False),
            sa.Column("update_time", sa.BigInteger(), nullable=False),
            sa.Column("execute_time", sa.BigInteger(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    indexes = (
        ("idx_sys_tenant_schema_change_request_tenant_id", ["tenant_id"]),
        ("idx_sys_tenant_schema_change_request_datasource", ["datasource_id"]),
        ("idx_sys_tenant_schema_change_request_status", ["status"]),
        ("idx_sys_tenant_schema_change_request_table", ["tenant_id", "table_name"]),
    )
    for index_name, columns in indexes:
        if not _has_index("sys_tenant_schema_change_request", index_name):
            op.create_index(index_name, "sys_tenant_schema_change_request", columns)


def downgrade() -> None:
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    if not _has_table("sys_tenant_schema_change_request"):
        return
    for index_name in (
        "idx_sys_tenant_schema_change_request_table",
        "idx_sys_tenant_schema_change_request_status",
        "idx_sys_tenant_schema_change_request_datasource",
        "idx_sys_tenant_schema_change_request_tenant_id",
    ):
        if _has_index("sys_tenant_schema_change_request", index_name):
            op.drop_index(index_name, table_name="sys_tenant_schema_change_request")
    op.drop_table("sys_tenant_schema_change_request")
