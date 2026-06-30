"""迁移脚本：130_workspace_schema_change_requests

迁移版本 ID： c7e9a2d4f6b8
上一版本： b6a4d2f8c9e3
创建时间： 2026-06-26 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c7e9a2d4f6b8"
down_revision = "b6a4d2f8c9e3"
branch_labels = None
depends_on = None


def _bind():
    """
    是什么：_bind 是 backend/alembic/versions/130_workspace_schema_change_requests.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：更新数据库迁移相关状态、配置或持久化数据，并保持后续流程可继续使用。
    """
    return op.get_bind()


def _inspector():
    """
    是什么：_inspector 是 backend/alembic/versions/130_workspace_schema_change_requests.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _inspector 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/130_workspace_schema_change_requests.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in _inspector().get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是 backend/alembic/versions/130_workspace_schema_change_requests.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_index 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def upgrade() -> None:
    """
    是什么：upgrade 是 backend/alembic/versions/130_workspace_schema_change_requests.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table("sys_tenant_schema_change_request"):
        op.create_table(
            "sys_tenant_schema_change_request",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("datasource_id", sa.BigInteger(), nullable=True),
            sa.Column("change_type", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("table_name", sa.String(length=255), nullable=False),
            sa.Column("payload", sa.Text(), nullable=True),
            sa.Column("requested_by_user_id", sa.BigInteger(), nullable=False),
            sa.Column("executed_by_user_id", sa.BigInteger(), nullable=True),
            sa.Column("request_comment", sa.Text(), nullable=True),
            sa.Column("execution_comment", sa.Text(), nullable=True),
            sa.Column("create_time", sa.BigInteger(), nullable=False),
            sa.Column("update_time", sa.BigInteger(), nullable=False),
            sa.Column("execute_time", sa.BigInteger(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    indexes = (
        ("idx_sys_tenant_schema_change_request_tenant_id", ["tenant_id"]),
        ("idx_sys_tenant_schema_change_request_datasource", ["datasource_id"]),
        ("idx_sys_tenant_schema_change_request_status", ["status"]),
        ("idx_sys_tenant_schema_change_request_table", ["tenant_id", "table_name"]),
    )
    for index_name, columns in indexes:
        if not _has_index("sys_tenant_schema_change_request", index_name):
            op.create_index(index_name, "sys_tenant_schema_change_request", columns)


def downgrade() -> None:
    """
    是什么：downgrade 是 backend/alembic/versions/130_workspace_schema_change_requests.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table("sys_tenant_schema_change_request"):
        return
    for index_name in (
        "idx_sys_tenant_schema_change_request_table",
        "idx_sys_tenant_schema_change_request_status",
        "idx_sys_tenant_schema_change_request_datasource",
        "idx_sys_tenant_schema_change_request_tenant_id",
    ):
        if _has_index("sys_tenant_schema_change_request", index_name):
            op.drop_index(index_name, table_name="sys_tenant_schema_change_request")
    op.drop_table("sys_tenant_schema_change_request")
