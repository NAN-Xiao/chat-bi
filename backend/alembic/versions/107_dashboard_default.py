"""迁移脚本：107_dashboard_default

迁移版本 ID： c86d2f9a31b4
上一版本： a75d8e3c91bf
创建时间： 2026-06-22 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c86d2f9a31b4"
down_revision = "a75d8e3c91bf"
branch_labels = None
depends_on = None


def _bind():
    """
    是什么：_bind 是 backend/alembic/versions/107_dashboard_default.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：更新数据库迁移相关状态、配置或持久化数据，并保持后续流程可继续使用。
    """
    return op.get_bind()


def _inspector():
    """
    是什么：_inspector 是 backend/alembic/versions/107_dashboard_default.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _inspector 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/107_dashboard_default.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/107_dashboard_default.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是 backend/alembic/versions/107_dashboard_default.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_index 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/107_dashboard_default.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table("core_dashboard"):
        return

    if not _has_column("core_dashboard", "is_default"):
        op.add_column(
            "core_dashboard",
            sa.Column("is_default", sa.SmallInteger(), nullable=False, server_default="0"),
        )

    if not _has_index("core_dashboard", "idx_core_dashboard_default_tenant"):
        op.create_index(
            "idx_core_dashboard_default_tenant",
            "core_dashboard",
            ["tenant_id", "is_default"],
            unique=False,
        )


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/107_dashboard_default.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table("core_dashboard"):
        return

    if _has_index("core_dashboard", "idx_core_dashboard_default_tenant"):
        op.drop_index("idx_core_dashboard_default_tenant", table_name="core_dashboard")
    if _has_column("core_dashboard", "is_default"):
        op.drop_column("core_dashboard", "is_default")
