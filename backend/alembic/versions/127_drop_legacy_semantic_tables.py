"""迁移脚本：127_drop_legacy_semantic_tables

迁移版本 ID： e7c9f1a3b5d6
上一版本： c4d8f2a6b901
创建时间： 2026-06-26 00:00:00.000000
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
    是什么：_bind 是 backend/alembic/versions/127_drop_legacy_semantic_tables.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：更新数据库迁移相关状态、配置或持久化数据，并保持后续流程可继续使用。
    """
    return op.get_bind()


def _inspector():
    """
    是什么：_inspector 是 backend/alembic/versions/127_drop_legacy_semantic_tables.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _inspector 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/127_drop_legacy_semantic_tables.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/127_drop_legacy_semantic_tables.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def upgrade() -> None:
    """
    是什么：upgrade 是 backend/alembic/versions/127_drop_legacy_semantic_tables.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
    是什么：downgrade 是 backend/alembic/versions/127_drop_legacy_semantic_tables.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
