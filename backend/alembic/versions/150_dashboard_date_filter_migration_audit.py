"""增加看板日期筛选 V2 迁移审计表。"""

import sqlalchemy as sa

from alembic import op


revision = "150dashboarddatefilteraudit"
down_revision = "149dashboardexecutiondatasource"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "core_dashboard_date_filter_migration_audit",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("batch_id", sa.String(length=100), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("dashboard_id", sa.String(length=50), nullable=False),
        sa.Column("chart_ids", sa.Text(), nullable=False),
        sa.Column("classification_json", sa.Text(), nullable=False),
        sa.Column("original_canvas", sa.Text(), nullable=False),
        sa.Column("original_canvas_sha256", sa.String(length=64), nullable=False),
        sa.Column("migrated_canvas", sa.Text(), nullable=False),
        sa.Column("migrated_canvas_sha256", sa.String(length=64), nullable=False),
        sa.Column("verification_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="applied"),
        sa.Column("created_time", sa.BigInteger(), nullable=False),
        sa.Column("rolled_back_time", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "dashboard_id", name="uq_dashboard_date_filter_migration_batch_dashboard"),
    )
    op.create_index(
        "idx_dashboard_date_filter_migration_tenant_dashboard",
        "core_dashboard_date_filter_migration_audit",
        ["tenant_id", "dashboard_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_dashboard_date_filter_migration_tenant_dashboard", table_name="core_dashboard_date_filter_migration_audit")
    op.drop_table("core_dashboard_date_filter_migration_audit")
