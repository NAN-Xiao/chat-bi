"""迁移脚本：133_chat_agent_context_snapshot

迁移版本 ID： f3a9d2c7b6e1
上一版本： e8c1f4a6b9d2
创建时间： 2026-06-28 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f3a9d2c7b6e1"
down_revision = "e8c1f4a6b9d2"
branch_labels = None
depends_on = None


def _inspector():
    """
    是什么：_inspector 是 backend/alembic/versions/133_chat_agent_context_snapshot.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _inspector 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/133_chat_agent_context_snapshot.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/133_chat_agent_context_snapshot.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return column_name in {column["name"] for column in _inspector().get_columns(table_name)}


def upgrade() -> None:
    """
    是什么：upgrade 是 backend/alembic/versions/133_chat_agent_context_snapshot.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table("chat_record"):
        return
    if not _has_column("chat_record", "agent_context_snapshot"):
        op.add_column(
            "chat_record",
            sa.Column("agent_context_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )


def downgrade() -> None:
    """
    是什么：downgrade 是 backend/alembic/versions/133_chat_agent_context_snapshot.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if _has_table("chat_record") and _has_column("chat_record", "agent_context_snapshot"):
        op.drop_column("chat_record", "agent_context_snapshot")
