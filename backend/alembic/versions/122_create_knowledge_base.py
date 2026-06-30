"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "2f4a6c8e0b13"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.create_table(
        "knowledge_base",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), server_default="1", nullable=False),
        sa.Column("create_by", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("visibility_scope", sa.String(length=32), server_default="ADMIN_PUBLIC", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column("file_id", sa.String(length=255), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("file_ext", sa.String(length=32), nullable=True),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("create_time", sa.DateTime(timezone=False), nullable=True),
        sa.Column("update_time", sa.DateTime(timezone=False), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_knowledge_base_tenant_scope", "knowledge_base", ["tenant_id", "visibility_scope"])
    op.create_index("idx_knowledge_base_create_by", "knowledge_base", ["create_by"])
    op.create_index("idx_knowledge_base_status", "knowledge_base", ["status"])


def downgrade() -> None:
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.drop_index("idx_knowledge_base_status", table_name="knowledge_base")
    op.drop_index("idx_knowledge_base_create_by", table_name="knowledge_base")
    op.drop_index("idx_knowledge_base_tenant_scope", table_name="knowledge_base")
    op.drop_table("knowledge_base")
