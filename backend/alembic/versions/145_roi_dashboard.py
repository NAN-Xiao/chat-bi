"""新增 ROI 专用看板数据表。"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "145roidashboard"
down_revision = "144dashboardname"
branch_labels = None
depends_on = None

TABLE_NAMES = (
    "core_roi_workspace_config",
    "core_roi_dashboard",
    "core_roi_dashboard_chart",
)
ROI_LAYOUT_SPANS = ("full", "half", "third")


def upgrade() -> None:
    op.create_table(
        "core_roi_workspace_config",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("datasource_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("create_by", sa.BigInteger(), nullable=True),
        sa.Column("update_by", sa.BigInteger(), nullable=True),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.Column(
            "deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_core_roi_workspace_config_active_tenant",
        "core_roi_workspace_config",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("deleted = false"),
    )
    op.create_index(
        "idx_core_roi_workspace_config_tenant_id",
        "core_roi_workspace_config",
        ["tenant_id"],
    )

    op.create_table(
        "core_roi_dashboard",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("sort", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("create_by", sa.BigInteger(), nullable=True),
        sa.Column("update_by", sa.BigInteger(), nullable=True),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.Column(
            "deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_core_roi_dashboard_tenant_id", "core_roi_dashboard", ["tenant_id"]
    )
    op.create_index(
        "idx_core_roi_dashboard_tenant_status_sort",
        "core_roi_dashboard",
        ["tenant_id", "status", "sort"],
    )

    op.create_table(
        "core_roi_dashboard_chart",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("roi_dashboard_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("sql", sa.Text(), nullable=False),
        sa.Column("chart_type", sa.String(length=64), nullable=False),
        sa.Column(
            "chart_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "layout_span",
            sa.String(length=16),
            server_default=sa.text("'full'"),
            nullable=False,
        ),
        sa.Column("sort", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("create_by", sa.BigInteger(), nullable=True),
        sa.Column("update_by", sa.BigInteger(), nullable=True),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.Column(
            "deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.CheckConstraint(
            "layout_span IN ('full','half','third')",
            name="ck_core_roi_chart_layout_span",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_core_roi_dashboard_chart_tenant_id",
        "core_roi_dashboard_chart",
        ["tenant_id"],
    )
    op.create_index(
        "idx_core_roi_dashboard_chart_tenant_dashboard_status_sort",
        "core_roi_dashboard_chart",
        ["tenant_id", "roi_dashboard_id", "status", "sort"],
    )


def downgrade() -> None:
    op.drop_table("core_roi_dashboard_chart")
    op.drop_table("core_roi_dashboard")
    op.drop_table("core_roi_workspace_config")
