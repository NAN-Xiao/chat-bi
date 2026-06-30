"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "8e3f5a7b9c01"
down_revision = "6c9d2e4f8a10"
branch_labels = None
depends_on = None

DEFAULT_TENANT_ID = 1


def _bind():
    """
    是什么：_bind 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移相关的信息改成最新状态，并保存这些变化。
    """
    return op.get_bind()


def _inspector():
    """
    是什么：_inspector 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return table_name in _inspector().get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _has_unique_constraint(table_name: str, constraint_name: str) -> bool:
    """
    是什么：_has_unique_constraint 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not _has_table(table_name):
        return False
    return any(item["name"] == constraint_name for item in _inspector().get_unique_constraints(table_name))


def upgrade() -> None:
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    if not _has_table("core_datasource_tenant_binding"):
        op.create_table(
            "core_datasource_tenant_binding",
            sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("datasource_id", sa.BigInteger(), nullable=False),
            sa.Column("create_by", sa.BigInteger(), nullable=True),
            sa.Column("create_time", sa.DateTime(timezone=False), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", name="uq_core_datasource_tenant_binding_tenant"),
            sa.UniqueConstraint("tenant_id", "datasource_id", name="uq_core_datasource_tenant_binding_pair"),
        )

    if not _has_index("core_datasource_tenant_binding", "idx_core_datasource_tenant_binding_datasource"):
        op.create_index(
            "idx_core_datasource_tenant_binding_datasource",
            "core_datasource_tenant_binding",
            ["datasource_id"],
        )

    if _has_table("core_datasource"):
        op.execute(
            f"""
            INSERT INTO core_datasource_tenant_binding (tenant_id, datasource_id, create_by, create_time)
            SELECT tenant_id, MIN(id) AS datasource_id, NULL, CURRENT_TIMESTAMP
            FROM core_datasource
            WHERE tenant_id IS NOT NULL
              AND tenant_id <> {DEFAULT_TENANT_ID}
              AND NOT EXISTS (
                  SELECT 1
                  FROM core_datasource_tenant_binding existing
                  WHERE existing.tenant_id = core_datasource.tenant_id
              )
            GROUP BY tenant_id
            """
        )


def downgrade() -> None:
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    if not _has_table("core_datasource_tenant_binding"):
        return
    if _has_table("core_datasource"):
        op.execute(
            f"""
            UPDATE core_datasource
            SET tenant_id = {DEFAULT_TENANT_ID}
            WHERE tenant_id IS NOT NULL
              AND tenant_id <> {DEFAULT_TENANT_ID}
            """
        )
        op.execute(
            """
            UPDATE core_datasource
            SET tenant_id = binding.tenant_id
            FROM core_datasource_tenant_binding binding
            WHERE core_datasource.id = binding.datasource_id
            """
        )
    if _has_index("core_datasource_tenant_binding", "idx_core_datasource_tenant_binding_datasource"):
        op.drop_index(
            "idx_core_datasource_tenant_binding_datasource",
            table_name="core_datasource_tenant_binding",
        )
    op.drop_table("core_datasource_tenant_binding")
