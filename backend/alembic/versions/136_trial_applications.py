"""
脚本说明：增加访客试用账号申请表，供管理员审核后创建可登录账号。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def _inspector():
    """
    是什么：_inspector 返回当前数据库结构检查器。
    """
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 检查表是否存在。
    """
    return table_name in _inspector().get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 检查索引是否存在。
    """
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def upgrade() -> None:
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    """
    if not _has_table("sys_trial_application"):
        op.create_table(
            "sys_trial_application",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("account", sa.String(length=100), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("email", sa.String(length=100), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("company", sa.String(length=255), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("reviewer_user_id", sa.BigInteger(), nullable=True),
            sa.Column("review_comment", sa.Text(), nullable=True),
            sa.Column("approved_user_id", sa.BigInteger(), nullable=True),
            sa.Column("create_time", sa.BigInteger(), nullable=False),
            sa.Column("update_time", sa.BigInteger(), nullable=False),
            sa.Column("review_time", sa.BigInteger(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _has_index("sys_trial_application", "idx_sys_trial_application_account"):
        op.create_index(
            "idx_sys_trial_application_account",
            "sys_trial_application",
            ["account"],
            unique=False,
        )
    if not _has_index("sys_trial_application", "idx_sys_trial_application_email"):
        op.create_index(
            "idx_sys_trial_application_email",
            "sys_trial_application",
            ["email"],
            unique=False,
        )
    if not _has_index("sys_trial_application", "idx_sys_trial_application_status"):
        op.create_index(
            "idx_sys_trial_application_status",
            "sys_trial_application",
            ["status"],
            unique=False,
        )


def downgrade() -> None:
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    """
    if not _has_table("sys_trial_application"):
        return
    if _has_index("sys_trial_application", "idx_sys_trial_application_status"):
        op.drop_index("idx_sys_trial_application_status", table_name="sys_trial_application")
    if _has_index("sys_trial_application", "idx_sys_trial_application_email"):
        op.drop_index("idx_sys_trial_application_email", table_name="sys_trial_application")
    if _has_index("sys_trial_application", "idx_sys_trial_application_account"):
        op.drop_index("idx_sys_trial_application_account", table_name="sys_trial_application")
    op.drop_table("sys_trial_application")
