"""094_platform_semantic_foundation_scope

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-06-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _add_scope_column(table_name: str, index_name: str) -> None:
    if not _has_table(table_name):
        return
    if not _has_column(table_name, "scope"):
        op.add_column(
            table_name,
            sa.Column("scope", sa.String(length=32), nullable=False, server_default="TENANT"),
        )
    else:
        op.execute(
            f"""
            UPDATE {table_name}
            SET scope = 'TENANT'
            WHERE scope IS NULL OR scope NOT IN ('TENANT', 'PLATFORM')
            """
        )
        op.alter_column(
            table_name,
            "scope",
            existing_type=sa.String(length=32),
            nullable=False,
            server_default="TENANT",
        )
    if not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, ["scope"])


def upgrade():
    _add_scope_column("terminology", "idx_terminology_scope")
    _add_scope_column("data_training", "idx_data_training_scope")


def downgrade():
    for table_name, index_name in (
        ("data_training", "idx_data_training_scope"),
        ("terminology", "idx_terminology_scope"),
    ):
        if not _has_table(table_name):
            continue
        if _has_index(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
        if _has_column(table_name, "scope"):
            op.drop_column(table_name, "scope")
