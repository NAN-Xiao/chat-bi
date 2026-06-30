"""迁移脚本：111_analysis_assistant_conversation

迁移版本 ID： c9d12e7f4a6b
上一版本： b62f1a4d8c93
创建时间： 2026-06-22 00:00:00.000000
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
    是什么：_bind 是 backend/alembic/versions/111_analysis_assistant_conversation.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：更新数据库迁移相关状态、配置或持久化数据，并保持后续流程可继续使用。
    """
    return op.get_bind()


def _inspector():
    """
    是什么：_inspector 是 backend/alembic/versions/111_analysis_assistant_conversation.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _inspector 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/111_analysis_assistant_conversation.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in _inspector().get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是 backend/alembic/versions/111_analysis_assistant_conversation.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_index 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def upgrade() -> None:
    """
    是什么：upgrade 是 backend/alembic/versions/111_analysis_assistant_conversation.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
    是什么：downgrade 是 backend/alembic/versions/111_analysis_assistant_conversation.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
