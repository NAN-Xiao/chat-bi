"""
脚本说明：为工作区表字段元数据增加展示名，供数据字典和图表配置使用。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "137schemadisplay"
down_revision = "136trialapps1"
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
    if _has_table("sys_tenant_schema_table") and not _has_column("sys_tenant_schema_table", "display_name"):
        op.add_column("sys_tenant_schema_table", sa.Column("display_name", sa.String(length=255), nullable=True))
    if _has_table("sys_tenant_schema_field") and not _has_column("sys_tenant_schema_field", "display_name"):
        op.add_column("sys_tenant_schema_field", sa.Column("display_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    if _has_table("sys_tenant_schema_field") and _has_column("sys_tenant_schema_field", "display_name"):
        op.drop_column("sys_tenant_schema_field", "display_name")
    if _has_table("sys_tenant_schema_table") and _has_column("sys_tenant_schema_table", "display_name"):
        op.drop_column("sys_tenant_schema_table", "display_name")
