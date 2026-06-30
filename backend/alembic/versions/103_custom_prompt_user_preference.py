"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa


revision = "d31c7b9a4e02"
down_revision = "ac22d4e6f810"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    if _has_table("custom_prompt_user_preference"):
        return
    op.create_table(
        "custom_prompt_user_preference",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("custom_prompt_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("update_time", sa.DateTime(timezone=False), nullable=True),
        sa.UniqueConstraint(
            "custom_prompt_id",
            "user_id",
            name="uq_custom_prompt_user_preference_prompt_user",
        ),
    )
    op.create_index(
        "idx_custom_prompt_user_preference_user",
        "custom_prompt_user_preference",
        ["user_id"],
    )
    op.create_index(
        "idx_custom_prompt_user_preference_prompt",
        "custom_prompt_user_preference",
        ["custom_prompt_id"],
    )


def downgrade() -> None:
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    if not _has_table("custom_prompt_user_preference"):
        return
    op.drop_index("idx_custom_prompt_user_preference_prompt", table_name="custom_prompt_user_preference")
    op.drop_index("idx_custom_prompt_user_preference_user", table_name="custom_prompt_user_preference")
    op.drop_table("custom_prompt_user_preference")
