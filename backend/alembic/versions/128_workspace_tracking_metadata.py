"""迁移脚本：128_workspace_tracking_metadata

迁移版本 ID： a5f2d8c9e7b1
上一版本： e7c9f1a3b5d6
创建时间： 2026-06-26 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a5f2d8c9e7b1"
down_revision = "e7c9f1a3b5d6"
branch_labels = None
depends_on = None


def _bind():
    """
    是什么：_bind 是 backend/alembic/versions/128_workspace_tracking_metadata.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：更新数据库迁移相关状态、配置或持久化数据，并保持后续流程可继续使用。
    """
    return op.get_bind()


def _inspector():
    """
    是什么：_inspector 是 backend/alembic/versions/128_workspace_tracking_metadata.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _inspector 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/128_workspace_tracking_metadata.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in _inspector().get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是 backend/alembic/versions/128_workspace_tracking_metadata.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_index 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def upgrade() -> None:
    """
    是什么：upgrade 是 backend/alembic/versions/128_workspace_tracking_metadata.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table("sys_tenant_tracking_config"):
        op.create_table(
            "sys_tenant_tracking_config",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("default_event_table", sa.String(length=255), nullable=True),
            sa.Column("default_subject_field", sa.String(length=255), nullable=True),
            sa.Column("default_event_name_field", sa.String(length=255), nullable=True),
            sa.Column("default_event_time_field", sa.String(length=255), nullable=True),
            sa.Column("field_role_mappings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("event_name_mappings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("sql_rules", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("create_by", sa.BigInteger(), nullable=True),
            sa.Column("update_by", sa.BigInteger(), nullable=True),
            sa.Column("create_time", sa.BigInteger(), nullable=False),
            sa.Column("update_time", sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", name="uq_sys_tenant_tracking_config_tenant_id"),
        )
    if not _has_index("sys_tenant_tracking_config", "idx_sys_tenant_tracking_config_tenant_id"):
        op.create_index(
            "idx_sys_tenant_tracking_config_tenant_id",
            "sys_tenant_tracking_config",
            ["tenant_id"],
        )

    if not _has_table("sys_tenant_tracking_table"):
        op.create_table(
            "sys_tenant_tracking_table",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("table_name", sa.String(length=255), nullable=False),
            sa.Column("table_comment", sa.Text(), nullable=True),
            sa.Column("table_role", sa.String(length=64), nullable=True),
            sa.Column("aliases", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("ai_notes", sa.Text(), nullable=True),
            sa.Column("create_by", sa.BigInteger(), nullable=True),
            sa.Column("update_by", sa.BigInteger(), nullable=True),
            sa.Column("create_time", sa.BigInteger(), nullable=False),
            sa.Column("update_time", sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "table_name", name="uq_sys_tenant_tracking_table_name"),
        )
    if not _has_index("sys_tenant_tracking_table", "idx_sys_tenant_tracking_table_tenant_id"):
        op.create_index(
            "idx_sys_tenant_tracking_table_tenant_id",
            "sys_tenant_tracking_table",
            ["tenant_id"],
        )

    if not _has_table("sys_tenant_tracking_field"):
        op.create_table(
            "sys_tenant_tracking_field",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("table_name", sa.String(length=255), nullable=False),
            sa.Column("field_name", sa.String(length=255), nullable=False),
            sa.Column("field_comment", sa.Text(), nullable=True),
            sa.Column("field_role", sa.String(length=64), nullable=True),
            sa.Column("semantic_type", sa.String(length=64), nullable=True),
            sa.Column("aliases", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("value_mappings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("expression", sa.Text(), nullable=True),
            sa.Column("required", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("example_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("ai_notes", sa.Text(), nullable=True),
            sa.Column("create_by", sa.BigInteger(), nullable=True),
            sa.Column("update_by", sa.BigInteger(), nullable=True),
            sa.Column("create_time", sa.BigInteger(), nullable=False),
            sa.Column("update_time", sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id",
                "table_name",
                "field_name",
                name="uq_sys_tenant_tracking_field_name",
            ),
        )
    if not _has_index("sys_tenant_tracking_field", "idx_sys_tenant_tracking_field_tenant_id"):
        op.create_index(
            "idx_sys_tenant_tracking_field_tenant_id",
            "sys_tenant_tracking_field",
            ["tenant_id"],
        )
    if not _has_index("sys_tenant_tracking_field", "idx_sys_tenant_tracking_field_table"):
        op.create_index(
            "idx_sys_tenant_tracking_field_table",
            "sys_tenant_tracking_field",
            ["tenant_id", "table_name"],
        )


def downgrade() -> None:
    """
    是什么：downgrade 是 backend/alembic/versions/128_workspace_tracking_metadata.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if _has_index("sys_tenant_tracking_field", "idx_sys_tenant_tracking_field_table"):
        op.drop_index("idx_sys_tenant_tracking_field_table", table_name="sys_tenant_tracking_field")
    if _has_index("sys_tenant_tracking_field", "idx_sys_tenant_tracking_field_tenant_id"):
        op.drop_index("idx_sys_tenant_tracking_field_tenant_id", table_name="sys_tenant_tracking_field")
    if _has_table("sys_tenant_tracking_field"):
        op.drop_table("sys_tenant_tracking_field")

    if _has_index("sys_tenant_tracking_table", "idx_sys_tenant_tracking_table_tenant_id"):
        op.drop_index("idx_sys_tenant_tracking_table_tenant_id", table_name="sys_tenant_tracking_table")
    if _has_table("sys_tenant_tracking_table"):
        op.drop_table("sys_tenant_tracking_table")

    if _has_index("sys_tenant_tracking_config", "idx_sys_tenant_tracking_config_tenant_id"):
        op.drop_index("idx_sys_tenant_tracking_config_tenant_id", table_name="sys_tenant_tracking_config")
    if _has_table("sys_tenant_tracking_config"):
        op.drop_table("sys_tenant_tracking_config")
