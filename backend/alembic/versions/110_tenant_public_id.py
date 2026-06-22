"""110_tenant_public_id

Revision ID: b62f1a4d8c93
Revises: a7d8f0c9b2e1
Create Date: 2026-06-22 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b62f1a4d8c93"
down_revision = "a7d8f0c9b2e1"
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


def _has_unique_constraint(table_name: str, constraint_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        constraint["name"] == constraint_name
        for constraint in _inspector().get_unique_constraints(table_name)
    )


def upgrade() -> None:
    if not _has_table("sys_tenant"):
        return
    if not _has_column("sys_tenant", "public_id"):
        op.add_column("sys_tenant", sa.Column("public_id", sa.String(length=32), nullable=True))
    op.execute(
        """
        UPDATE sys_tenant
        SET public_id = 'WS'
            || upper(to_hex(id::bigint))
            || upper(substr(md5(id::text || ':' || coalesce(name, '') || ':' || coalesce(create_time::text, '')), 1, 4))
            || '2'
        WHERE public_id IS NULL OR btrim(public_id) = ''
        """
    )
    op.alter_column("sys_tenant", "public_id", existing_type=sa.String(length=32), nullable=False)
    if not _has_unique_constraint("sys_tenant", "uq_sys_tenant_public_id"):
        op.create_unique_constraint("uq_sys_tenant_public_id", "sys_tenant", ["public_id"])


def downgrade() -> None:
    if not _has_table("sys_tenant") or not _has_column("sys_tenant", "public_id"):
        return
    if _has_unique_constraint("sys_tenant", "uq_sys_tenant_public_id"):
        op.drop_constraint("uq_sys_tenant_public_id", "sys_tenant", type_="unique")
    op.drop_column("sys_tenant", "public_id")
