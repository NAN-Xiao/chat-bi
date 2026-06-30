"""迁移脚本：132_custom_prompt_skill_embedding

迁移版本 ID： e8c1f4a6b9d2
上一版本： d4f7a9c2e1b3
创建时间： 2026-06-27 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e8c1f4a6b9d2"
down_revision = "d4f7a9c2e1b3"
branch_labels = None
depends_on = None


def _inspector():
    """
    是什么：_inspector 是 backend/alembic/versions/132_custom_prompt_skill_embedding.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _inspector 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/132_custom_prompt_skill_embedding.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/132_custom_prompt_skill_embedding.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return column_name in {column["name"] for column in _inspector().get_columns(table_name)}


def upgrade() -> None:
    """
    是什么：upgrade 是 backend/alembic/versions/132_custom_prompt_skill_embedding.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table("custom_prompt"):
        return
    if not _has_column("custom_prompt", "embedding"):
        op.add_column("custom_prompt", sa.Column("embedding", sa.Text(), nullable=True))
    if not _has_column("custom_prompt", "embedding_signature"):
        op.add_column("custom_prompt", sa.Column("embedding_signature", sa.String(length=128), nullable=True))


def downgrade() -> None:
    """
    是什么：downgrade 是 backend/alembic/versions/132_custom_prompt_skill_embedding.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table("custom_prompt"):
        return
    if _has_column("custom_prompt", "embedding_signature"):
        op.drop_column("custom_prompt", "embedding_signature")
    if _has_column("custom_prompt", "embedding"):
        op.drop_column("custom_prompt", "embedding")
