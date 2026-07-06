"""
脚本说明：给工作空间数据字典字段增加更新方式和属性标签。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "140trackingfieldmeta"
down_revision = "139trackingdsscope"
branch_labels = None
depends_on = None


TABLE_NAME = "sys_tenant_tracking_field"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def upgrade() -> None:
    if not _has_table(TABLE_NAME):
        return
    if not _has_column(TABLE_NAME, "update_mode"):
        op.add_column(TABLE_NAME, sa.Column("update_mode", sa.String(length=64), nullable=True))
    if not _has_column(TABLE_NAME, "category"):
        op.add_column(TABLE_NAME, sa.Column("category", sa.String(length=255), nullable=True))


def downgrade() -> None:
    if not _has_table(TABLE_NAME):
        return
    if _has_column(TABLE_NAME, "category"):
        op.drop_column(TABLE_NAME, "category")
    if _has_column(TABLE_NAME, "update_mode"):
        op.drop_column(TABLE_NAME, "update_mode")

