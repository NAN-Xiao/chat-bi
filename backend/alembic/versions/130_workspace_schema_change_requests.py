"""130_workspace_schema_change_requests

Revision ID: c7e9a2d4f6b8
Revises: b6a4d2f8c9e3
Create Date: 2026-06-26 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c7e9a2d4f6b8"
down_revision = "b6a4d2f8c9e3"
branch_labels = None
depends_on = None


def _bind():
    return op.get_bind()


def _inspector():
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def upgrade() -> None:
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
