"""移除事件映射中的采集端字段。"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "143trackingcollectside"
down_revision = "142trackinggroups"
branch_labels = None
depends_on = None


CLEAN_EVENT_MAPPINGS_SQL = sa.text(
    """
    UPDATE sys_tenant_tracking_config AS config
    SET event_name_mappings = (
        SELECT COALESCE(
            jsonb_agg(
                CASE
                    WHEN jsonb_typeof(item) = 'object'
                    THEN item - 'collect_side' - 'collectSide'
                    ELSE item
                END
                ORDER BY item_order
            ),
            '[]'::jsonb
        ) AS event_name_mappings
        FROM jsonb_array_elements(config.event_name_mappings)
            WITH ORDINALITY AS mapping(item, item_order)
    )
    WHERE jsonb_typeof(config.event_name_mappings) = 'array'
      AND config.event_name_mappings::text ~ '"collect_side"|"collectSide"'
    """
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "sys_tenant_tracking_config" not in inspector.get_table_names():
        return
    op.execute(CLEAN_EVENT_MAPPINGS_SQL)


def downgrade() -> None:
    pass
