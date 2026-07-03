"""
脚本说明：为工作空间字典字段增加显式 JSON 来源字段和路径。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "138trackingjson"
down_revision = "137schemadisplay"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def upgrade() -> None:
    if _has_table("sys_tenant_tracking_field") and not _has_column("sys_tenant_tracking_field", "source_field"):
        op.add_column("sys_tenant_tracking_field", sa.Column("source_field", sa.String(length=255), nullable=True))
    if _has_table("sys_tenant_tracking_field") and not _has_column("sys_tenant_tracking_field", "json_path"):
        op.add_column("sys_tenant_tracking_field", sa.Column("json_path", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    if _has_table("sys_tenant_tracking_field") and _has_column("sys_tenant_tracking_field", "json_path"):
        op.drop_column("sys_tenant_tracking_field", "json_path")
    if _has_table("sys_tenant_tracking_field") and _has_column("sys_tenant_tracking_field", "source_field"):
        op.drop_column("sys_tenant_tracking_field", "source_field")
