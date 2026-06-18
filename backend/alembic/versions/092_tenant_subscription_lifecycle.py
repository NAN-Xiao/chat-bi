"""092_tenant_subscription_lifecycle

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-06-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def upgrade():
    if not _has_table("sys_tenant"):
        return

    _add_column_if_missing(
        "sys_tenant",
        sa.Column("subscription_status", sa.String(length=32), nullable=False, server_default="active"),
    )
    _add_column_if_missing(
        "sys_tenant",
        sa.Column("billing_mode", sa.String(length=32), nullable=False, server_default="manual"),
    )
    _add_column_if_missing("sys_tenant", sa.Column("trial_end_time", sa.BigInteger(), nullable=True))
    _add_column_if_missing("sys_tenant", sa.Column("current_period_end_time", sa.BigInteger(), nullable=True))
    _add_column_if_missing("sys_tenant", sa.Column("contract_no", sa.String(length=128), nullable=True))
    _add_column_if_missing("sys_tenant", sa.Column("billing_contact", sa.String(length=128), nullable=True))
    _add_column_if_missing("sys_tenant", sa.Column("billing_email", sa.String(length=128), nullable=True))
    _add_column_if_missing("sys_tenant", sa.Column("subscription_note", sa.Text(), nullable=True))

    if not _has_index("sys_tenant", "idx_sys_tenant_subscription_status"):
        op.create_index("idx_sys_tenant_subscription_status", "sys_tenant", ["subscription_status"])


def downgrade():
    if not _has_table("sys_tenant"):
        return
    if _has_index("sys_tenant", "idx_sys_tenant_subscription_status"):
        op.drop_index("idx_sys_tenant_subscription_status", table_name="sys_tenant")
    for column_name in (
        "subscription_note",
        "billing_email",
        "billing_contact",
        "contract_no",
        "current_period_end_time",
        "trial_end_time",
        "billing_mode",
        "subscription_status",
    ):
        if _has_column("sys_tenant", column_name):
            op.drop_column("sys_tenant", column_name)
