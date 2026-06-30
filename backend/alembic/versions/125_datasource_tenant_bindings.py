"""迁移脚本：125_datasource_tenant_bindings

迁移版本 ID： 8e3f5a7b9c01
上一版本： 6c9d2e4f8a10
创建时间： 2026-06-24 00:00:00.000000
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
    是什么：_bind 是 backend/alembic/versions/125_datasource_tenant_bindings.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：更新数据库迁移相关状态、配置或持久化数据，并保持后续流程可继续使用。
    """
    return op.get_bind()


def _inspector():
    """
    是什么：_inspector 是 backend/alembic/versions/125_datasource_tenant_bindings.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _inspector 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/125_datasource_tenant_bindings.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in _inspector().get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是 backend/alembic/versions/125_datasource_tenant_bindings.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_index 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _has_unique_constraint(table_name: str, constraint_name: str) -> bool:
    """
    是什么：_has_unique_constraint 是 backend/alembic/versions/125_datasource_tenant_bindings.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_unique_constraint 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return any(item["name"] == constraint_name for item in _inspector().get_unique_constraints(table_name))


def upgrade() -> None:
    """
    是什么：upgrade 是 backend/alembic/versions/125_datasource_tenant_bindings.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
    是什么：downgrade 是 backend/alembic/versions/125_datasource_tenant_bindings.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
