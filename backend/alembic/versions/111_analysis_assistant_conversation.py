"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c9d12e7f4a6b"
down_revision = "b62f1a4d8c93"
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
    if not _has_table("analysis_assistant_conversation"):
        op.create_table(
            "analysis_assistant_conversation",
            sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), server_default="1", nullable=False),
            sa.Column("create_by", sa.BigInteger(), nullable=False),
            sa.Column("title", sa.String(length=128), server_default="", nullable=False),
            sa.Column("datasource_id", sa.BigInteger(), nullable=True),
            sa.Column("datasource_name", sa.String(length=255), nullable=True),
            sa.Column("custom_prompt_id", sa.BigInteger(), nullable=True),
            sa.Column("data_skill_id", sa.BigInteger(), nullable=True),
            sa.Column(
                "messages",
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'[]'::jsonb"),
                nullable=False,
            ),
            sa.Column("create_time", sa.DateTime(timezone=False), nullable=False),
            sa.Column("update_time", sa.DateTime(timezone=False), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _has_index("analysis_assistant_conversation", "idx_analysis_assistant_conversation_tenant_user"):
        op.create_index(
            "idx_analysis_assistant_conversation_tenant_user",
            "analysis_assistant_conversation",
            ["tenant_id", "create_by"],
        )
    if not _has_index("analysis_assistant_conversation", "idx_analysis_assistant_conversation_datasource"):
        op.create_index(
            "idx_analysis_assistant_conversation_datasource",
            "analysis_assistant_conversation",
            ["datasource_id"],
        )
    if not _has_index("analysis_assistant_conversation", "idx_analysis_assistant_conversation_update_time"):
        op.create_index(
            "idx_analysis_assistant_conversation_update_time",
            "analysis_assistant_conversation",
            ["update_time"],
        )


def downgrade() -> None:
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    if not _has_table("analysis_assistant_conversation"):
        return
    for index_name in (
        "idx_analysis_assistant_conversation_update_time",
        "idx_analysis_assistant_conversation_datasource",
        "idx_analysis_assistant_conversation_tenant_user",
    ):
        if _has_index("analysis_assistant_conversation", index_name):
            op.drop_index(index_name, table_name="analysis_assistant_conversation")
    op.drop_table("analysis_assistant_conversation")
