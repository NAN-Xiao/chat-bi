"""约束工作空间内推荐看板名称唯一。"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "144dashboardname"
down_revision = "143trackingcollectside"
branch_labels = None
depends_on = None


INDEX_NAME = "uq_core_dashboard_recommended_name"

DUPLICATE_RECOMMENDED_NAMES_SQL = sa.text(
    """
    SELECT tenant_id,
           lower(btrim(name)) AS normalized_name,
           count(*) AS duplicate_count
    FROM core_dashboard
    WHERE COALESCE(delete_flag, 0) = 0
      AND COALESCE(status, 1) NOT IN (2, 3)
      AND node_type = 'leaf'
      AND COALESCE(is_default, 0) = 1
      AND name IS NOT NULL
    GROUP BY tenant_id, lower(btrim(name))
    HAVING count(*) > 1
    LIMIT 1
    """
)

CREATE_UNIQUE_INDEX_SQL = sa.text(
    f"""
    CREATE UNIQUE INDEX {INDEX_NAME}
    ON core_dashboard (tenant_id, lower(btrim(name)))
    WHERE COALESCE(delete_flag, 0) = 0
      AND COALESCE(status, 1) NOT IN (2, 3)
      AND node_type = 'leaf'
      AND COALESCE(is_default, 0) = 1
    """
)


def _has_index(inspector: sa.Inspector) -> bool:
    return any(index.get("name") == INDEX_NAME for index in inspector.get_indexes("core_dashboard"))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "core_dashboard" not in inspector.get_table_names() or _has_index(inspector):
        return

    duplicate = bind.execute(DUPLICATE_RECOMMENDED_NAMES_SQL).first()
    if duplicate is not None:
        tenant_id, normalized_name, duplicate_count = duplicate
        raise RuntimeError(
            "推荐看板名称唯一索引创建失败："
            f"tenant_id={tenant_id}, name={normalized_name!r}, count={duplicate_count}"
        )
    op.execute(CREATE_UNIQUE_INDEX_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "core_dashboard" in inspector.get_table_names() and _has_index(inspector):
        op.drop_index(INDEX_NAME, table_name="core_dashboard")
