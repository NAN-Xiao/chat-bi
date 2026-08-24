"""Enforce one active primary workspace per user."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "167primaryworkspaceunique"
down_revision = "166removelegacykbstate"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_sys_tenant_user_active_primary"

REPAIR_DUPLICATE_PRIMARY_SQL = """
WITH ranked_primary AS (
    SELECT
        membership.id,
        ROW_NUMBER() OVER (
            PARTITION BY membership.user_id
            ORDER BY
                CASE
                    WHEN COALESCE(tenant.status, 0) = 1 AND tenant.id <> 1 THEN 0
                    WHEN COALESCE(tenant.status, 0) = 1 THEN 1
                    ELSE 2
                END,
                LOWER(TRIM(COALESCE(tenant.name, ''))),
                membership.tenant_id,
                membership.id
        ) AS primary_rank
    FROM sys_tenant_user AS membership
    LEFT JOIN sys_tenant AS tenant ON tenant.id = membership.tenant_id
    WHERE membership.status = 1 AND membership.is_primary = true
)
UPDATE sys_tenant_user
SET is_primary = false
WHERE id IN (
    SELECT id
    FROM ranked_primary
    WHERE primary_rank > 1
)
"""

CREATE_UNIQUE_INDEX_SQL = f"""
CREATE UNIQUE INDEX {INDEX_NAME}
ON sys_tenant_user (user_id)
WHERE status = 1 AND is_primary = true
"""


def upgrade() -> None:
    op.execute(sa.text(REPAIR_DUPLICATE_PRIMARY_SQL))
    op.execute(sa.text(CREATE_UNIQUE_INDEX_SQL))


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="sys_tenant_user")
