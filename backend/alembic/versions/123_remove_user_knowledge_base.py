"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
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
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
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
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.alter_column(
        "knowledge_base",
        "visibility_scope",
        existing_type=sa.String(length=32),
        server_default="USER_PRIVATE",
        existing_nullable=False,
    )
