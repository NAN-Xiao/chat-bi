"""迁移脚本：123_remove_user_knowledge_base

迁移版本 ID： 6c9d2e4f8a10
上一版本： 2f4a6c8e0b13
创建时间： 2026-06-23 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "6c9d2e4f8a10"
down_revision = "2f4a6c8e0b13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    是什么：upgrade 是 backend/alembic/versions/123_remove_user_knowledge_base.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.execute("DELETE FROM knowledge_base WHERE visibility_scope = 'USER_PRIVATE'")
    op.alter_column(
        "knowledge_base",
        "visibility_scope",
        existing_type=sa.String(length=32),
        server_default="ADMIN_PUBLIC",
        existing_nullable=False,
    )


def downgrade() -> None:
    """
    是什么：downgrade 是 backend/alembic/versions/123_remove_user_knowledge_base.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.alter_column(
        "knowledge_base",
        "visibility_scope",
        existing_type=sa.String(length=32),
        server_default="USER_PRIVATE",
        existing_nullable=False,
    )
