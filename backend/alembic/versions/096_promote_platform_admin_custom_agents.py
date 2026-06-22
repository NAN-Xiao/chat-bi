"""096_promote_platform_admin_custom_agents

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-06-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None

DEFAULT_TENANT_ID = 1


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade():
    if not (_has_table("custom_prompt") and _has_table("sys_user")):
        return
    required_columns = {
        "custom_prompt": ("tenant_id", "create_by", "visibility_scope", "specific_ds", "datasource_ids"),
        "sys_user": ("id", "system_role"),
    }
    for table_name, column_names in required_columns.items():
        for column_name in column_names:
            if not _has_column(table_name, column_name):
                return

    op.execute(
        sa.text(
            """
            UPDATE custom_prompt AS cp
            SET visibility_scope = 'PLATFORM_PUBLIC',
                tenant_id = :default_tenant_id,
                specific_ds = FALSE,
                datasource_ids = '[]'::jsonb
            FROM sys_user AS u
            WHERE u.id = cp.create_by
              AND u.system_role = 'system_admin'
              AND cp.visibility_scope = 'ADMIN_PUBLIC'
            """
        ).bindparams(default_tenant_id=DEFAULT_TENANT_ID)
    )


def downgrade():
    # Data promotion is intentionally irreversible: demoting SaaS Agents
    # would hide them again from SaaS admin management surfaces.
    pass
