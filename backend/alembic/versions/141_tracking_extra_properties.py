"""
脚本说明：给工作空间数据字典表和字段增加 Excel 扩展属性存储。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "141trackingextra"
down_revision = "140trackingfieldmeta"
branch_labels = None
depends_on = None


TABLE_CONFIG = "sys_tenant_tracking_table"
FIELD_CONFIG = "sys_tenant_tracking_field"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def upgrade() -> None:
    if _has_table(TABLE_CONFIG) and not _has_column(TABLE_CONFIG, "extra_properties"):
        op.add_column(
            TABLE_CONFIG,
            sa.Column("extra_properties", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
    if _has_table(FIELD_CONFIG) and not _has_column(FIELD_CONFIG, "extra_properties"):
        op.add_column(
            FIELD_CONFIG,
            sa.Column("extra_properties", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )


def downgrade() -> None:
    if _has_table(FIELD_CONFIG) and _has_column(FIELD_CONFIG, "extra_properties"):
        op.drop_column(FIELD_CONFIG, "extra_properties")
    if _has_table(TABLE_CONFIG) and _has_column(TABLE_CONFIG, "extra_properties"):
        op.drop_column(TABLE_CONFIG, "extra_properties")
