"""099_system_variable_tenant_scope

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-06-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
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
    table_name = "system_variable"
    column_name = "tenant_id"
    if not _has_table(table_name):
        return
    if not _has_column(table_name, column_name):
        op.add_column(
            table_name,
            sa.Column(
                column_name,
                sa.BigInteger(),
                nullable=False,
                server_default=str(DEFAULT_TENANT_ID),
            ),
        )
    op.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET tenant_id = :tenant_id
            WHERE tenant_id IS NULL
            """
        ).bindparams(tenant_id=DEFAULT_TENANT_ID)
    )
    if not _has_index(table_name, "idx_system_variable_tenant_id"):
        op.create_index("idx_system_variable_tenant_id", table_name, ["tenant_id"])


def downgrade():
    table_name = "system_variable"
    column_name = "tenant_id"
    if not _has_table(table_name):
        return
    if _has_index(table_name, "idx_system_variable_tenant_id"):
        op.drop_index("idx_system_variable_tenant_id", table_name=table_name)
    if _has_column(table_name, column_name):
        op.drop_column(table_name, column_name)
