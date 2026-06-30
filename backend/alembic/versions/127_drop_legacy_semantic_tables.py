"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from __future__ import annotations

from alembic import op
import pgvector
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e7c9f1a3b5d6"
down_revision = "c4d8f2a6b901"
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


def upgrade() -> None:
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    if _has_table("task_queue") and _has_column("task_queue", "task_name"):
        op.execute(
            """
            DELETE FROM task_queue
            WHERE task_name IN (
                'terminology.embedding',
                'terminology.fill_empty_embedding',
                'data_training.embedding',
                'data_training.fill_empty_embedding'
            )
            """
        )

    if _has_table("data_training"):
        op.drop_table("data_training")
    if _has_table("terminology"):
        op.drop_table("terminology")


def downgrade() -> None:
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    if not _has_table("terminology"):
        op.create_table(
            "terminology",
            sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default="1"),
            sa.Column("scope", sa.String(length=32), nullable=False, server_default="TENANT"),
            sa.Column("pid", sa.BigInteger(), nullable=True),
            sa.Column("create_time", sa.DateTime(timezone=False), nullable=True),
            sa.Column("word", sa.String(length=255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(), nullable=True),
            sa.Column("specific_ds", sa.Boolean(), nullable=True),
            sa.Column("datasource_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=True),
        )

    if not _has_table("data_training"):
        op.create_table(
            "data_training",
            sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default="1"),
            sa.Column("scope", sa.String(length=32), nullable=False, server_default="TENANT"),
            sa.Column("datasource", sa.BigInteger(), nullable=True),
            sa.Column("create_time", sa.DateTime(timezone=False), nullable=True),
            sa.Column("question", sa.String(length=255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=True),
            sa.Column("advanced_application", sa.BigInteger(), nullable=True),
        )
