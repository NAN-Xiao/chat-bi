"""084_semantic_layer_tenant_scope

Revision ID: f4c5d6e7f8a9
Revises: f3b4c5d6e7f8
Create Date: 2026-06-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "f4c5d6e7f8a9"
down_revision = "f3b4c5d6e7f8"
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


def _add_tenant_column(table_name: str, index_name: str) -> None:
    if not _has_table(table_name):
        return
    if not _has_column(table_name, "tenant_id"):
        op.add_column(
            table_name,
            sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default=str(DEFAULT_TENANT_ID)),
        )
    else:
        op.execute(
            f"""
            UPDATE {table_name}
            SET tenant_id = {DEFAULT_TENANT_ID}
            WHERE tenant_id IS NULL
            """
        )
    if not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, ["tenant_id"])


def upgrade():
    _add_tenant_column("terminology", "idx_terminology_tenant_id")
    _add_tenant_column("data_training", "idx_data_training_tenant_id")
    _add_tenant_column("custom_prompt", "idx_custom_prompt_tenant_id")


def downgrade():
    for table_name, index_name in (
        ("custom_prompt", "idx_custom_prompt_tenant_id"),
        ("data_training", "idx_data_training_tenant_id"),
        ("terminology", "idx_terminology_tenant_id"),
    ):
        if not _has_table(table_name):
            continue
        if _has_index(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
        if _has_column(table_name, "tenant_id"):
            op.drop_column(table_name, "tenant_id")
