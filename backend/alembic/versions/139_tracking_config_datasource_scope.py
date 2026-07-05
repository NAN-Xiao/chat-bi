"""
脚本说明：给工作空间数据字典增加当前绑定数据源边界。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "139trackingdsscope"
down_revision = "138trackingjson"
branch_labels = None
depends_on = None


TRACKING_TABLES = (
    "sys_tenant_tracking_config",
    "sys_tenant_tracking_table",
    "sys_tenant_tracking_field",
)


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _has_unique_constraint(table_name: str, constraint_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(item["name"] == constraint_name for item in _inspector().get_unique_constraints(table_name))


def _drop_constraint_if_exists(table_name: str, constraint_name: str) -> None:
    if _has_unique_constraint(table_name, constraint_name):
        op.drop_constraint(constraint_name, table_name, type_="unique")


def _add_datasource_columns() -> None:
    for table_name in TRACKING_TABLES:
        if _has_table(table_name) and not _has_column(table_name, "datasource_id"):
            op.add_column(table_name, sa.Column("datasource_id", sa.BigInteger(), nullable=True))


def _backfill_datasource_scope() -> None:
    if not all(_has_table(table_name) for table_name in TRACKING_TABLES):
        return
    if not all(_has_column(table_name, "datasource_id") for table_name in TRACKING_TABLES):
        return

    if _has_table("core_datasource_tenant_binding"):
        for table_name in TRACKING_TABLES:
            op.execute(
                sa.text(
                    f"""
                    UPDATE {table_name} AS tracking
                    SET datasource_id = binding.datasource_id
                    FROM core_datasource_tenant_binding AS binding
                    WHERE tracking.tenant_id = binding.tenant_id
                      AND tracking.datasource_id IS NULL
                    """
                )
            )

    if _has_table("core_datasource") and _has_column("core_datasource", "tenant_id"):
        for table_name in TRACKING_TABLES:
            op.execute(
                sa.text(
                    f"""
                    UPDATE {table_name} AS tracking
                    SET datasource_id = src.datasource_id
                    FROM (
                        SELECT tenant_id, MIN(id) AS datasource_id
                        FROM core_datasource
                        WHERE tenant_id IS NOT NULL
                        GROUP BY tenant_id
                    ) AS src
                    WHERE tracking.tenant_id = src.tenant_id
                      AND tracking.datasource_id IS NULL
                    """
                )
            )


def _replace_constraints() -> None:
    if _has_table("sys_tenant_tracking_config"):
        _drop_constraint_if_exists("sys_tenant_tracking_config", "uq_sys_tenant_tracking_config_tenant_id")
        if not _has_unique_constraint("sys_tenant_tracking_config", "uq_sys_tenant_tracking_config_tenant_datasource"):
            op.create_unique_constraint(
                "uq_sys_tenant_tracking_config_tenant_datasource",
                "sys_tenant_tracking_config",
                ["tenant_id", "datasource_id"],
            )
        if not _has_index("sys_tenant_tracking_config", "idx_sys_tenant_tracking_config_datasource"):
            op.create_index(
                "idx_sys_tenant_tracking_config_datasource",
                "sys_tenant_tracking_config",
                ["tenant_id", "datasource_id"],
            )

    if _has_table("sys_tenant_tracking_table"):
        _drop_constraint_if_exists("sys_tenant_tracking_table", "uq_sys_tenant_tracking_table_name")
        if not _has_unique_constraint("sys_tenant_tracking_table", "uq_sys_tenant_tracking_table_name"):
            op.create_unique_constraint(
                "uq_sys_tenant_tracking_table_name",
                "sys_tenant_tracking_table",
                ["tenant_id", "datasource_id", "table_name"],
            )
        if not _has_index("sys_tenant_tracking_table", "idx_sys_tenant_tracking_table_datasource"):
            op.create_index(
                "idx_sys_tenant_tracking_table_datasource",
                "sys_tenant_tracking_table",
                ["tenant_id", "datasource_id"],
            )

    if _has_table("sys_tenant_tracking_field"):
        _drop_constraint_if_exists("sys_tenant_tracking_field", "uq_sys_tenant_tracking_field_name")
        if not _has_unique_constraint("sys_tenant_tracking_field", "uq_sys_tenant_tracking_field_name"):
            op.create_unique_constraint(
                "uq_sys_tenant_tracking_field_name",
                "sys_tenant_tracking_field",
                ["tenant_id", "datasource_id", "table_name", "field_name"],
            )
        if not _has_index("sys_tenant_tracking_field", "idx_sys_tenant_tracking_field_datasource"):
            op.create_index(
                "idx_sys_tenant_tracking_field_datasource",
                "sys_tenant_tracking_field",
                ["tenant_id", "datasource_id"],
            )


def upgrade() -> None:
    _add_datasource_columns()
    _backfill_datasource_scope()
    _replace_constraints()


def downgrade() -> None:
    if _has_table("sys_tenant_tracking_field"):
        if _has_index("sys_tenant_tracking_field", "idx_sys_tenant_tracking_field_datasource"):
            op.drop_index("idx_sys_tenant_tracking_field_datasource", table_name="sys_tenant_tracking_field")
        _drop_constraint_if_exists("sys_tenant_tracking_field", "uq_sys_tenant_tracking_field_name")
        op.create_unique_constraint(
            "uq_sys_tenant_tracking_field_name",
            "sys_tenant_tracking_field",
            ["tenant_id", "table_name", "field_name"],
        )

    if _has_table("sys_tenant_tracking_table"):
        if _has_index("sys_tenant_tracking_table", "idx_sys_tenant_tracking_table_datasource"):
            op.drop_index("idx_sys_tenant_tracking_table_datasource", table_name="sys_tenant_tracking_table")
        _drop_constraint_if_exists("sys_tenant_tracking_table", "uq_sys_tenant_tracking_table_name")
        op.create_unique_constraint(
            "uq_sys_tenant_tracking_table_name",
            "sys_tenant_tracking_table",
            ["tenant_id", "table_name"],
        )

    if _has_table("sys_tenant_tracking_config"):
        if _has_index("sys_tenant_tracking_config", "idx_sys_tenant_tracking_config_datasource"):
            op.drop_index("idx_sys_tenant_tracking_config_datasource", table_name="sys_tenant_tracking_config")
        _drop_constraint_if_exists("sys_tenant_tracking_config", "uq_sys_tenant_tracking_config_tenant_datasource")
        op.create_unique_constraint(
            "uq_sys_tenant_tracking_config_tenant_id",
            "sys_tenant_tracking_config",
            ["tenant_id"],
        )

    for table_name in reversed(TRACKING_TABLES):
        if _has_table(table_name) and _has_column(table_name, "datasource_id"):
            op.drop_column(table_name, "datasource_id")
