"""迁移脚本：129_workspace_schema_metadata

迁移版本 ID： b6a4d2f8c9e3
上一版本： a5f2d8c9e7b1
创建时间： 2026-06-26 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b6a4d2f8c9e3"
down_revision = "a5f2d8c9e7b1"
branch_labels = None
depends_on = None


def _bind():
    """
    是什么：_bind 是 backend/alembic/versions/129_workspace_schema_metadata.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：更新数据库迁移相关状态、配置或持久化数据，并保持后续流程可继续使用。
    """
    return op.get_bind()


def _inspector():
    """
    是什么：_inspector 是 backend/alembic/versions/129_workspace_schema_metadata.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _inspector 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/129_workspace_schema_metadata.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/129_workspace_schema_metadata.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是 backend/alembic/versions/129_workspace_schema_metadata.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_index 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _has_unique_constraint(table_name: str, constraint_name: str) -> bool:
    """
    是什么：_has_unique_constraint 是 backend/alembic/versions/129_workspace_schema_metadata.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_unique_constraint 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return any(item["name"] == constraint_name for item in _inspector().get_unique_constraints(table_name))


def _create_tables() -> None:
    """
    是什么：_create_tables 是 backend/alembic/versions/129_workspace_schema_metadata.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：创建、初始化或组装数据库迁移相关对象和数据，并返回或写入对应状态。
    """
    if not _has_table("sys_tenant_schema_table"):
        op.create_table(
            "sys_tenant_schema_table",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("table_name", sa.String(length=255), nullable=False),
            sa.Column("table_comment", sa.Text(), nullable=True),
            sa.Column("create_by", sa.BigInteger(), nullable=True),
            sa.Column("update_by", sa.BigInteger(), nullable=True),
            sa.Column("create_time", sa.BigInteger(), nullable=False),
            sa.Column("update_time", sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "table_name", name="uq_sys_tenant_schema_table_name"),
        )
    if not _has_index("sys_tenant_schema_table", "idx_sys_tenant_schema_table_tenant_id"):
        op.create_index(
            "idx_sys_tenant_schema_table_tenant_id",
            "sys_tenant_schema_table",
            ["tenant_id"],
        )

    if not _has_table("sys_tenant_schema_field"):
        op.create_table(
            "sys_tenant_schema_field",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("table_name", sa.String(length=255), nullable=False),
            sa.Column("field_name", sa.String(length=255), nullable=False),
            sa.Column("field_comment", sa.Text(), nullable=True),
            sa.Column("create_by", sa.BigInteger(), nullable=True),
            sa.Column("update_by", sa.BigInteger(), nullable=True),
            sa.Column("create_time", sa.BigInteger(), nullable=False),
            sa.Column("update_time", sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id",
                "table_name",
                "field_name",
                name="uq_sys_tenant_schema_field_name",
            ),
        )
    if not _has_index("sys_tenant_schema_field", "idx_sys_tenant_schema_field_tenant_id"):
        op.create_index(
            "idx_sys_tenant_schema_field_tenant_id",
            "sys_tenant_schema_field",
            ["tenant_id"],
        )
    if not _has_index("sys_tenant_schema_field", "idx_sys_tenant_schema_field_table"):
        op.create_index(
            "idx_sys_tenant_schema_field_table",
            "sys_tenant_schema_field",
            ["tenant_id", "table_name"],
        )


def _migrate_existing_comments() -> None:
    """
    是什么：_migrate_existing_comments 是 backend/alembic/versions/129_workspace_schema_metadata.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _migrate_existing_comments 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not all(
        _has_table(table)
        for table in (
            "core_datasource",
            "core_table",
            "core_field",
            "sys_tenant_schema_table",
            "sys_tenant_schema_field",
        )
    ):
        return
    if not all(
        _has_column("core_datasource", column)
        for column in ("id", "tenant_id")
    ):
        return
    if not all(
        _has_column("core_table", column)
        for column in ("id", "ds_id", "table_name", "custom_comment")
    ):
        return
    if not all(
        _has_column("core_field", column)
        for column in ("table_id", "field_name", "custom_comment")
    ):
        return

    op.execute(
        """
        INSERT INTO sys_tenant_schema_table (
            id,
            tenant_id,
            table_name,
            table_comment,
            create_time,
            update_time
        )
        SELECT
            2000000000000000000 + row_number() OVER (ORDER BY src.tenant_id, src.table_name) AS id,
            src.tenant_id,
            src.table_name,
            src.table_comment,
            0,
            0
        FROM (
            SELECT DISTINCT ON (ds.tenant_id, t.table_name)
                ds.tenant_id,
                t.table_name,
                NULLIF(BTRIM(t.custom_comment), '') AS table_comment
            FROM core_table AS t
            JOIN core_datasource AS ds ON ds.id = t.ds_id
            WHERE ds.tenant_id IS NOT NULL
              AND NULLIF(BTRIM(COALESCE(t.custom_comment, '')), '') IS NOT NULL
            ORDER BY ds.tenant_id, t.table_name, t.id
        ) AS src
        ON CONFLICT (tenant_id, table_name) DO UPDATE
            SET table_comment = EXCLUDED.table_comment,
                update_time = EXCLUDED.update_time
        """
    )

    op.execute(
        """
        INSERT INTO sys_tenant_schema_field (
            id,
            tenant_id,
            table_name,
            field_name,
            field_comment,
            create_time,
            update_time
        )
        SELECT
            3000000000000000000 + row_number() OVER (
                ORDER BY src.tenant_id, src.table_name, src.field_name
            ) AS id,
            src.tenant_id,
            src.table_name,
            src.field_name,
            src.field_comment,
            0,
            0
        FROM (
            SELECT DISTINCT ON (ds.tenant_id, t.table_name, f.field_name)
                ds.tenant_id,
                t.table_name,
                f.field_name,
                NULLIF(BTRIM(f.custom_comment), '') AS field_comment
            FROM core_field AS f
            JOIN core_table AS t ON t.id = f.table_id
            JOIN core_datasource AS ds ON ds.id = f.ds_id
            WHERE ds.tenant_id IS NOT NULL
              AND NULLIF(BTRIM(COALESCE(f.custom_comment, '')), '') IS NOT NULL
            ORDER BY ds.tenant_id, t.table_name, f.field_name, f.id
        ) AS src
        ON CONFLICT (tenant_id, table_name, field_name) DO UPDATE
            SET field_comment = EXCLUDED.field_comment,
                update_time = EXCLUDED.update_time
        """
    )


def upgrade() -> None:
    """
    是什么：upgrade 是 backend/alembic/versions/129_workspace_schema_metadata.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    _create_tables()
    _migrate_existing_comments()


def downgrade() -> None:
    """
    是什么：downgrade 是 backend/alembic/versions/129_workspace_schema_metadata.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if _has_index("sys_tenant_schema_field", "idx_sys_tenant_schema_field_table"):
        op.drop_index("idx_sys_tenant_schema_field_table", table_name="sys_tenant_schema_field")
    if _has_index("sys_tenant_schema_field", "idx_sys_tenant_schema_field_tenant_id"):
        op.drop_index("idx_sys_tenant_schema_field_tenant_id", table_name="sys_tenant_schema_field")
    if _has_table("sys_tenant_schema_field"):
        op.drop_table("sys_tenant_schema_field")

    if _has_index("sys_tenant_schema_table", "idx_sys_tenant_schema_table_tenant_id"):
        op.drop_index("idx_sys_tenant_schema_table_tenant_id", table_name="sys_tenant_schema_table")
    if _has_table("sys_tenant_schema_table"):
        op.drop_table("sys_tenant_schema_table")
