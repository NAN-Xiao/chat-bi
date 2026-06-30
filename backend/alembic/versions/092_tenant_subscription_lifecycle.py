"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa


revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return column_name in {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    """
    是什么：_add_column_if_missing 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存数据库迁移需要的东西，让后续流程能继续往下走。
    """
    if not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def upgrade():
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    if not _has_table("sys_tenant"):
        return

    _add_column_if_missing(
        "sys_tenant",
        sa.Column("subscription_status", sa.String(length=32), nullable=False, server_default="active"),
    )
    _add_column_if_missing(
        "sys_tenant",
        sa.Column("billing_mode", sa.String(length=32), nullable=False, server_default="manual"),
    )
    _add_column_if_missing("sys_tenant", sa.Column("trial_end_time", sa.BigInteger(), nullable=True))
    _add_column_if_missing("sys_tenant", sa.Column("current_period_end_time", sa.BigInteger(), nullable=True))
    _add_column_if_missing("sys_tenant", sa.Column("contract_no", sa.String(length=128), nullable=True))
    _add_column_if_missing("sys_tenant", sa.Column("billing_contact", sa.String(length=128), nullable=True))
    _add_column_if_missing("sys_tenant", sa.Column("billing_email", sa.String(length=128), nullable=True))
    _add_column_if_missing("sys_tenant", sa.Column("subscription_note", sa.Text(), nullable=True))

    if not _has_index("sys_tenant", "idx_sys_tenant_subscription_status"):
        op.create_index("idx_sys_tenant_subscription_status", "sys_tenant", ["subscription_status"])


def downgrade():
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    if not _has_table("sys_tenant"):
        return
    if _has_index("sys_tenant", "idx_sys_tenant_subscription_status"):
        op.drop_index("idx_sys_tenant_subscription_status", table_name="sys_tenant")
    for column_name in (
        "subscription_note",
        "billing_email",
        "billing_contact",
        "contract_no",
        "current_period_end_time",
        "trial_end_time",
        "billing_mode",
        "subscription_status",
    ):
        if _has_column("sys_tenant", column_name):
            op.drop_column("sys_tenant", column_name)
