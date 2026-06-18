"""095_promote_default_semantic_to_platform

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-06-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None

DEFAULT_TENANT_ID = 1


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_real_tenants() -> bool:
    if not _has_table("sys_tenant"):
        return False
    result = op.get_bind().execute(
        sa.text("SELECT 1 FROM sys_tenant WHERE id <> :default_tenant_id LIMIT 1"),
        {"default_tenant_id": DEFAULT_TENANT_ID},
    )
    return result.first() is not None


def _promote_default_semantic_records() -> None:
    if _has_real_tenants():
        return

    if _has_table("terminology") and _has_column("terminology", "scope"):
        op.execute(
            sa.text(
                """
                UPDATE terminology
                SET scope = 'PLATFORM',
                    tenant_id = :default_tenant_id,
                    specific_ds = FALSE,
                    datasource_ids = '[]'::jsonb
                WHERE tenant_id = :default_tenant_id
                  AND COALESCE(scope, 'TENANT') = 'TENANT'
                """
            ).bindparams(default_tenant_id=DEFAULT_TENANT_ID)
        )

    if _has_table("data_training") and _has_column("data_training", "scope"):
        op.execute(
            sa.text(
                """
                UPDATE data_training
                SET scope = 'PLATFORM',
                    tenant_id = :default_tenant_id,
                    datasource = NULL,
                    advanced_application = NULL
                WHERE tenant_id = :default_tenant_id
                  AND COALESCE(scope, 'TENANT') = 'TENANT'
                """
            ).bindparams(default_tenant_id=DEFAULT_TENANT_ID)
        )


def upgrade():
    _promote_default_semantic_records()


def downgrade():
    # This data migration is intentionally irreversible: after platform semantic
    # records are maintained by platform admins, demoting them would hide data.
    pass
