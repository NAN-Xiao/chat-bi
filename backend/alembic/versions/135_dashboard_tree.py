"""
脚本说明：为看板的“我的”和“推荐”视图增加独立树结构存储。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def _bind():
    """
    是什么：_bind 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    """
    return op.get_bind()


def _inspector():
    """
    是什么：_inspector 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    """
    return sa.inspect(_bind())


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


def _has_unique_constraint(table_name: str, constraint_name: str) -> bool:
    """
    是什么：_has_unique_constraint 检查唯一约束是否存在。
    """
    if not _has_table(table_name):
        return False
    return any(
        constraint["name"] == constraint_name
        for constraint in _inspector().get_unique_constraints(table_name)
    )


def _create_dashboard_tree_table() -> None:
    """
    是什么：_create_dashboard_tree_table 创建看板树表和索引。
    """
    if not _has_table("core_dashboard_tree"):
        op.create_table(
            "core_dashboard_tree",
            sa.Column("id", sa.String(length=50), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default="1"),
            sa.Column("scope", sa.String(length=32), nullable=False),
            sa.Column("dashboard_id", sa.String(length=50), nullable=False),
            sa.Column("parent_id", sa.String(length=50), nullable=False, server_default="root"),
            sa.Column("sort", sa.Integer(), nullable=True),
            sa.Column("create_time", sa.BigInteger(), nullable=True),
            sa.Column("create_by", sa.String(length=255), nullable=True),
            sa.Column("update_time", sa.BigInteger(), nullable=True),
            sa.Column("update_by", sa.String(length=255), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id",
                "scope",
                "dashboard_id",
                name="uq_core_dashboard_tree_scope_dashboard",
            ),
        )
    elif not _has_unique_constraint("core_dashboard_tree", "uq_core_dashboard_tree_scope_dashboard"):
        op.create_unique_constraint(
            "uq_core_dashboard_tree_scope_dashboard",
            "core_dashboard_tree",
            ["tenant_id", "scope", "dashboard_id"],
        )

    if not _has_index("core_dashboard_tree", "idx_core_dashboard_tree_tenant_scope"):
        op.create_index(
            "idx_core_dashboard_tree_tenant_scope",
            "core_dashboard_tree",
            ["tenant_id", "scope"],
            unique=False,
        )
    if not _has_index("core_dashboard_tree", "idx_core_dashboard_tree_dashboard"):
        op.create_index(
            "idx_core_dashboard_tree_dashboard",
            "core_dashboard_tree",
            ["dashboard_id"],
            unique=False,
        )


def _seed_dashboard_tree() -> None:
    """
    是什么：_seed_dashboard_tree 用旧看板字段初始化两棵树。
    """
    if not _has_table("core_dashboard"):
        return
    bind = _bind()
    bind.execute(sa.text(
        """
        WITH RECURSIVE my_nodes AS (
            SELECT id, tenant_id, pid, sort, create_time, create_by, update_time, update_by
            FROM core_dashboard
            WHERE COALESCE(delete_flag, 0) = 0
              AND COALESCE(status, 1) NOT IN (2)
              AND (COALESCE(is_default, 0) = 0 OR node_type = 'leaf')
            UNION
            SELECT parent.id, parent.tenant_id, parent.pid, parent.sort,
                   parent.create_time, parent.create_by, parent.update_time, parent.update_by
            FROM core_dashboard parent
            JOIN my_nodes child
              ON child.tenant_id = parent.tenant_id
             AND NULLIF(child.pid, '') = parent.id
            WHERE COALESCE(parent.delete_flag, 0) = 0
              AND COALESCE(parent.status, 1) NOT IN (2)
              AND parent.node_type = 'folder'
        )
        INSERT INTO core_dashboard_tree (
            id, tenant_id, scope, dashboard_id, parent_id, sort,
            create_time, create_by, update_time, update_by
        )
        SELECT
            md5(CAST(tenant_id AS TEXT) || ':my:' || id),
            tenant_id,
            'my',
            id,
            COALESCE(NULLIF(pid, ''), 'root'),
            COALESCE(sort, 0),
            create_time,
            create_by,
            update_time,
            update_by
        FROM my_nodes
        ON CONFLICT (tenant_id, scope, dashboard_id) DO NOTHING
        """
    ))
    bind.execute(sa.text(
        """
        WITH RECURSIVE default_nodes AS (
            SELECT id, tenant_id, pid, sort, create_time, create_by, update_time, update_by
            FROM core_dashboard
            WHERE COALESCE(delete_flag, 0) = 0
              AND COALESCE(status, 1) NOT IN (2)
              AND COALESCE(is_default, 0) = 1
            UNION
            SELECT parent.id, parent.tenant_id, parent.pid, parent.sort,
                   parent.create_time, parent.create_by, parent.update_time, parent.update_by
            FROM core_dashboard parent
            JOIN default_nodes child
              ON child.tenant_id = parent.tenant_id
             AND NULLIF(child.pid, '') = parent.id
            WHERE COALESCE(parent.delete_flag, 0) = 0
              AND COALESCE(parent.status, 1) NOT IN (2)
              AND parent.node_type = 'folder'
        )
        INSERT INTO core_dashboard_tree (
            id, tenant_id, scope, dashboard_id, parent_id, sort,
            create_time, create_by, update_time, update_by
        )
        SELECT
            md5(CAST(tenant_id AS TEXT) || ':default:' || id),
            tenant_id,
            'default',
            id,
            COALESCE(NULLIF(pid, ''), 'root'),
            COALESCE(sort, 0),
            create_time,
            create_by,
            update_time,
            update_by
        FROM default_nodes
        ON CONFLICT (tenant_id, scope, dashboard_id) DO NOTHING
        """
    ))


def upgrade() -> None:
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    """
    _create_dashboard_tree_table()
    _seed_dashboard_tree()


def downgrade() -> None:
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    """
    if not _has_table("core_dashboard_tree"):
        return
    if _has_index("core_dashboard_tree", "idx_core_dashboard_tree_dashboard"):
        op.drop_index("idx_core_dashboard_tree_dashboard", table_name="core_dashboard_tree")
    if _has_index("core_dashboard_tree", "idx_core_dashboard_tree_tenant_scope"):
        op.drop_index("idx_core_dashboard_tree_tenant_scope", table_name="core_dashboard_tree")
    op.drop_table("core_dashboard_tree")
