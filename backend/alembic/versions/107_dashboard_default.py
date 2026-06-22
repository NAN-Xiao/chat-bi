"""107_dashboard_default

Revision ID: c86d2f9a31b4
Revises: a75d8e3c91bf
Create Date: 2026-06-22 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c86d2f9a31b4"
down_revision = "a75d8e3c91bf"
branch_labels = None
depends_on = None


def _bind():
    return op.get_bind()


def _inspector():
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def upgrade():
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
    if not _has_table("core_dashboard"):
        return

    if _has_index("core_dashboard", "idx_core_dashboard_default_tenant"):
        op.drop_index("idx_core_dashboard_default_tenant", table_name="core_dashboard")
    if _has_column("core_dashboard", "is_default"):
        op.drop_column("core_dashboard", "is_default")
