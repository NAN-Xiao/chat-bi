"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa


revision = "d8e9f0a1b2c3"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade():
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    if not _has_table("sys_tenant_application"):
        op.create_table(
            "sys_tenant_application",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("applicant_user_id", sa.BigInteger(), nullable=False),
            sa.Column("invited_by_user_id", sa.BigInteger(), nullable=True),
            sa.Column("application_type", sa.String(length=32), nullable=False, server_default="create"),
            sa.Column("tenant_id", sa.BigInteger(), nullable=True),
            sa.Column("tenant_code", sa.String(length=64), nullable=False),
            sa.Column("tenant_name", sa.String(length=255), nullable=False),
            sa.Column("plan", sa.String(length=64), nullable=False, server_default="default"),
            sa.Column("requested_role", sa.String(length=32), nullable=False, server_default="owner"),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("reviewer_user_id", sa.BigInteger(), nullable=True),
            sa.Column("review_comment", sa.Text(), nullable=True),
            sa.Column("create_time", sa.BigInteger(), nullable=False),
            sa.Column("update_time", sa.BigInteger(), nullable=False),
            sa.Column("review_time", sa.BigInteger(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        if not _has_column("sys_tenant_application", "invited_by_user_id"):
            op.add_column(
                "sys_tenant_application",
                sa.Column("invited_by_user_id", sa.BigInteger(), nullable=True),
            )
        if not _has_column("sys_tenant_application", "application_type"):
            op.add_column(
                "sys_tenant_application",
                sa.Column("application_type", sa.String(length=32), nullable=False, server_default="create"),
            )
    if not _has_index("sys_tenant_application", "idx_sys_tenant_application_applicant"):
        op.create_index(
            "idx_sys_tenant_application_applicant",
            "sys_tenant_application",
            ["applicant_user_id"],
        )
    if not _has_index("sys_tenant_application", "idx_sys_tenant_application_inviter"):
        op.create_index(
            "idx_sys_tenant_application_inviter",
            "sys_tenant_application",
            ["invited_by_user_id"],
        )
    if not _has_index("sys_tenant_application", "idx_sys_tenant_application_status"):
        op.create_index(
            "idx_sys_tenant_application_status",
            "sys_tenant_application",
            ["status"],
        )
    if not _has_index("sys_tenant_application", "idx_sys_tenant_application_tenant_id"):
        op.create_index(
            "idx_sys_tenant_application_tenant_id",
            "sys_tenant_application",
            ["tenant_id"],
        )
    if not _has_index("sys_tenant_application", "idx_sys_tenant_application_type_status"):
        op.create_index(
            "idx_sys_tenant_application_type_status",
            "sys_tenant_application",
            ["application_type", "status"],
        )
    if not _has_index("sys_tenant_application", "idx_sys_tenant_application_tenant_code"):
        op.create_index(
            "idx_sys_tenant_application_tenant_code",
            "sys_tenant_application",
            ["tenant_code"],
        )


def downgrade():
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    if not _has_table("sys_tenant_application"):
        return
    if _has_index("sys_tenant_application", "idx_sys_tenant_application_tenant_code"):
        op.drop_index("idx_sys_tenant_application_tenant_code", table_name="sys_tenant_application")
    if _has_index("sys_tenant_application", "idx_sys_tenant_application_type_status"):
        op.drop_index("idx_sys_tenant_application_type_status", table_name="sys_tenant_application")
    if _has_index("sys_tenant_application", "idx_sys_tenant_application_tenant_id"):
        op.drop_index("idx_sys_tenant_application_tenant_id", table_name="sys_tenant_application")
    if _has_index("sys_tenant_application", "idx_sys_tenant_application_status"):
        op.drop_index("idx_sys_tenant_application_status", table_name="sys_tenant_application")
    if _has_index("sys_tenant_application", "idx_sys_tenant_application_inviter"):
        op.drop_index("idx_sys_tenant_application_inviter", table_name="sys_tenant_application")
    if _has_index("sys_tenant_application", "idx_sys_tenant_application_applicant"):
        op.drop_index("idx_sys_tenant_application_applicant", table_name="sys_tenant_application")
    op.drop_table("sys_tenant_application")
