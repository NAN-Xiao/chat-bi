"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa


revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
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
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _add_scope_column(table_name: str, index_name: str) -> None:
    """
    是什么：_add_scope_column 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存数据库迁移需要的东西，让后续流程能继续往下走。
    """
    if not _has_table(table_name):
        return
    if not _has_column(table_name, "scope"):
        op.add_column(
            table_name,
            sa.Column("scope", sa.String(length=32), nullable=False, server_default="TENANT"),
        )
    else:
        op.execute(
            f"""
            UPDATE {table_name}
            SET scope = 'TENANT'
            WHERE scope IS NULL OR scope NOT IN ('TENANT', 'PLATFORM')
            """
        )
        op.alter_column(
            table_name,
            "scope",
            existing_type=sa.String(length=32),
            nullable=False,
            server_default="TENANT",
        )
    if not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, ["scope"])


def upgrade():
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    _add_scope_column("terminology", "idx_terminology_scope")
    _add_scope_column("data_training", "idx_data_training_scope")


def downgrade():
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    for table_name, index_name in (
        ("data_training", "idx_data_training_scope"),
        ("terminology", "idx_terminology_scope"),
    ):
        if not _has_table(table_name):
            continue
        if _has_index(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
        if _has_column(table_name, "scope"):
            op.drop_column(table_name, "scope")
