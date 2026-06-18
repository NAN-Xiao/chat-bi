"""082_multi_tenant_foundation

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None

DEFAULT_TENANT_ID = 1


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade():
    if not _has_table("sys_tenant"):
        op.create_table(
            "sys_tenant",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("status", sa.BigInteger(), nullable=False, server_default="1"),
            sa.Column("plan", sa.String(length=64), nullable=False, server_default="default"),
            sa.Column("create_time", sa.BigInteger(), nullable=False),
            sa.Column("update_time", sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code", name="uq_sys_tenant_code"),
        )
        op.create_index("idx_sys_tenant_status", "sys_tenant", ["status"])

    if not _has_table("sys_tenant_user"):
        op.create_table(
            "sys_tenant_user",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("role", sa.String(length=32), nullable=False, server_default="member"),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("status", sa.BigInteger(), nullable=False, server_default="1"),
            sa.Column("create_time", sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "user_id", name="uq_sys_tenant_user_tenant_user"),
        )
        op.create_index("idx_sys_tenant_user_tenant_id", "sys_tenant_user", ["tenant_id"])
        op.create_index("idx_sys_tenant_user_user_id", "sys_tenant_user", ["user_id"])

    op.execute(
        f"""
        INSERT INTO sys_tenant (id, code, name, status, plan, create_time, update_time)
        SELECT {DEFAULT_TENANT_ID}, 'default', '默认租户', 1, 'default', 0, 0
        WHERE NOT EXISTS (
            SELECT 1 FROM sys_tenant WHERE id = {DEFAULT_TENANT_ID} OR code = 'default'
        )
        """
    )

    if _has_table("sys_user"):
        role_expr = "'member'"
        if _has_column("sys_user", "system_role"):
            role_expr = "CASE WHEN u.system_role = 'system_admin' THEN 'owner' ELSE 'member' END"
        op.execute(
            f"""
            INSERT INTO sys_tenant_user (id, tenant_id, user_id, role, is_primary, status, create_time)
            SELECT u.id + 1000000000000, {DEFAULT_TENANT_ID}, u.id, {role_expr}, TRUE, 1, 0
            FROM sys_user AS u
            WHERE NOT EXISTS (
                SELECT 1
                FROM sys_tenant_user AS tu
                WHERE tu.tenant_id = {DEFAULT_TENANT_ID}
                  AND tu.user_id = u.id
            )
            """
        )


def downgrade():
    if _has_table("sys_tenant_user"):
        op.drop_index("idx_sys_tenant_user_user_id", table_name="sys_tenant_user")
        op.drop_index("idx_sys_tenant_user_tenant_id", table_name="sys_tenant_user")
        op.drop_table("sys_tenant_user")
    if _has_table("sys_tenant"):
        op.drop_index("idx_sys_tenant_status", table_name="sys_tenant")
        op.drop_table("sys_tenant")
