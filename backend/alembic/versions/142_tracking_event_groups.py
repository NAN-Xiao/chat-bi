"""新增工作空间事件分组表。"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "142trackinggroups"
down_revision = "141trackingextra"
branch_labels = None
depends_on = None


TABLE_NAME = "sys_tenant_tracking_event_group"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def upgrade() -> None:
    if _has_table(TABLE_NAME):
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("datasource_id", sa.BigInteger(), nullable=False),
        sa.Column("group_key", sa.String(length=128), nullable=False),
        sa.Column("group_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("event_names", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sort_order", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("create_by", sa.BigInteger(), nullable=True),
        sa.Column("update_by", sa.BigInteger(), nullable=True),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "datasource_id",
            "group_key",
            name="uq_sys_tenant_tracking_event_group_key",
        ),
    )
    op.create_index(
        "idx_sys_tenant_tracking_event_group_datasource",
        TABLE_NAME,
        ["tenant_id", "datasource_id"],
        unique=False,
    )


def downgrade() -> None:
    if _has_table(TABLE_NAME):
        op.drop_table(TABLE_NAME)
