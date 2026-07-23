"""将 ROI 看板归并为工作空间单例。"""

import sqlalchemy as sa

from alembic import op


revision = "148roisingleton"
down_revision = "147refreshsqlgroupingskill"
branch_labels = None
depends_on = None

ROI_DASHBOARD_NAME = "ROI 看板"
ACTIVE_UNIQUE_INDEX = "uq_core_roi_dashboard_active_tenant"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY tenant_id
                           ORDER BY sort, create_time, id
                       ) AS row_number
                FROM core_roi_dashboard
                WHERE deleted = false AND status = 1
            )
            UPDATE core_roi_dashboard AS dashboard
            SET name = 'ROI 看板', sort = 0
            FROM ranked
            WHERE dashboard.id = ranked.id AND ranked.row_number = 1
            """
        )
    )
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id,
                       tenant_id,
                       ROW_NUMBER() OVER (
                           PARTITION BY tenant_id
                           ORDER BY sort, create_time, id
                       ) AS dashboard_number
                FROM core_roi_dashboard
                WHERE deleted = false AND status = 1
            ),
            canonical AS (
                SELECT id AS canonical_id, tenant_id
                FROM ranked
                WHERE dashboard_number = 1
            ),
            ordered AS (
                SELECT c.id,
                       canonical.canonical_id,
                       ROW_NUMBER() OVER (
                           PARTITION BY d.tenant_id
                           ORDER BY d.sort, d.create_time, d.id,
                                    c.sort, c.create_time, c.id
                       ) - 1 AS new_sort
                FROM core_roi_dashboard_chart AS c
                JOIN core_roi_dashboard AS d ON d.id = c.roi_dashboard_id
                JOIN canonical ON canonical.tenant_id = d.tenant_id
                WHERE d.deleted = false
                  AND d.status = 1
                  AND c.deleted = false
                  AND c.status = 1
            )
            UPDATE core_roi_dashboard_chart AS c
            SET roi_dashboard_id = ordered.canonical_id,
                sort = ordered.new_sort
            FROM ordered
            WHERE c.id = ordered.id
            """
        )
    )
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id,
                       tenant_id,
                       ROW_NUMBER() OVER (
                           PARTITION BY tenant_id
                           ORDER BY sort, create_time, id
                       ) AS dashboard_number
                FROM core_roi_dashboard
                WHERE deleted = false AND status = 1
            ),
            canonical AS (
                SELECT id AS canonical_id, tenant_id
                FROM ranked
                WHERE dashboard_number = 1
            )
            UPDATE core_roi_dashboard_chart AS c
            SET roi_dashboard_id = canonical.canonical_id
            FROM core_roi_dashboard AS d
            JOIN canonical ON canonical.tenant_id = d.tenant_id
            WHERE c.roi_dashboard_id = d.id
              AND d.deleted = false
              AND d.status = 1
              AND c.roi_dashboard_id <> canonical.canonical_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY tenant_id
                           ORDER BY sort, create_time, id
                       ) AS dashboard_number
                FROM core_roi_dashboard
                WHERE deleted = false AND status = 1
            )
            UPDATE core_roi_dashboard AS dashboard
            SET deleted = true, status = 0
            FROM ranked
            WHERE dashboard.id = ranked.id AND ranked.dashboard_number > 1
            """
        )
    )
    op.create_index(
        ACTIVE_UNIQUE_INDEX,
        "core_roi_dashboard",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("deleted = false AND status = 1"),
    )


def downgrade() -> None:
    # 数据归并不可逆；降级只移除单例约束，不拆分已归并的图表。
    op.drop_index(ACTIVE_UNIQUE_INDEX, table_name="core_roi_dashboard")
