"""083_core_datasource_tenant_scope

Revision ID: f3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-06-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "f3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None

DEFAULT_TENANT_ID = 1


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    if not _has_table("core_datasource"):
        return

    if not _has_column("core_datasource", "tenant_id"):
        op.add_column(
            "core_datasource",
            sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default=str(DEFAULT_TENANT_ID)),
        )
    else:
        op.execute(
            f"""
            UPDATE core_datasource
            SET tenant_id = {DEFAULT_TENANT_ID}
            WHERE tenant_id IS NULL
            """
        )

    if not _has_index("core_datasource", "idx_core_datasource_tenant_id"):
        op.create_index("idx_core_datasource_tenant_id", "core_datasource", ["tenant_id"])


def downgrade():
    if not _has_table("core_datasource"):
        return
    if _has_index("core_datasource", "idx_core_datasource_tenant_id"):
        op.drop_index("idx_core_datasource_tenant_id", table_name="core_datasource")
    if _has_column("core_datasource", "tenant_id"):
        op.drop_column("core_datasource", "tenant_id")
