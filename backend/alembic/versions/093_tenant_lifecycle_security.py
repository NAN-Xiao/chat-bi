"""093_tenant_lifecycle_security

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-06-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    if not _has_table("sys_tenant_domain"):
        op.create_table(
            "sys_tenant_domain",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("domain", sa.String(length=255), nullable=False),
            sa.Column("auto_join_role", sa.String(length=32), nullable=False, server_default="member"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("requested_by_user_id", sa.BigInteger(), nullable=True),
            sa.Column("verified_by_user_id", sa.BigInteger(), nullable=True),
            sa.Column("create_time", sa.BigInteger(), nullable=False),
            sa.Column("update_time", sa.BigInteger(), nullable=False),
            sa.Column("verify_time", sa.BigInteger(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("domain", name="uq_sys_tenant_domain_domain"),
        )
    if not _has_index("sys_tenant_domain", "idx_sys_tenant_domain_tenant_id"):
        op.create_index("idx_sys_tenant_domain_tenant_id", "sys_tenant_domain", ["tenant_id"])
    if not _has_index("sys_tenant_domain", "idx_sys_tenant_domain_status"):
        op.create_index("idx_sys_tenant_domain_status", "sys_tenant_domain", ["status"])

    if not _has_table("sys_tenant_security_policy"):
        op.create_table(
            "sys_tenant_security_policy",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("sso_required", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("session_timeout_minutes", sa.BigInteger(), nullable=True),
            sa.Column("create_time", sa.BigInteger(), nullable=False),
            sa.Column("update_time", sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", name="uq_sys_tenant_security_policy_tenant_id"),
        )
    if not _has_index("sys_tenant_security_policy", "idx_sys_tenant_security_policy_tenant_id"):
        op.create_index("idx_sys_tenant_security_policy_tenant_id", "sys_tenant_security_policy", ["tenant_id"])

    if not _has_table("sys_tenant_data_request"):
        op.create_table(
            "sys_tenant_data_request",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("request_type", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("requested_by_user_id", sa.BigInteger(), nullable=False),
            sa.Column("reviewer_user_id", sa.BigInteger(), nullable=True),
            sa.Column("completed_by_user_id", sa.BigInteger(), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("review_comment", sa.Text(), nullable=True),
            sa.Column("export_manifest", sa.Text(), nullable=True),
            sa.Column("create_time", sa.BigInteger(), nullable=False),
            sa.Column("update_time", sa.BigInteger(), nullable=False),
            sa.Column("review_time", sa.BigInteger(), nullable=True),
            sa.Column("complete_time", sa.BigInteger(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _has_index("sys_tenant_data_request", "idx_sys_tenant_data_request_tenant_id"):
        op.create_index("idx_sys_tenant_data_request_tenant_id", "sys_tenant_data_request", ["tenant_id"])
    if not _has_index("sys_tenant_data_request", "idx_sys_tenant_data_request_status"):
        op.create_index("idx_sys_tenant_data_request_status", "sys_tenant_data_request", ["status"])
    if not _has_index("sys_tenant_data_request", "idx_sys_tenant_data_request_type"):
        op.create_index("idx_sys_tenant_data_request_type", "sys_tenant_data_request", ["request_type"])


def downgrade():
    for table_name, indexes in (
        (
            "sys_tenant_data_request",
            (
                "idx_sys_tenant_data_request_type",
                "idx_sys_tenant_data_request_status",
                "idx_sys_tenant_data_request_tenant_id",
            ),
        ),
        ("sys_tenant_security_policy", ("idx_sys_tenant_security_policy_tenant_id",)),
        (
            "sys_tenant_domain",
            (
                "idx_sys_tenant_domain_status",
                "idx_sys_tenant_domain_tenant_id",
            ),
        ),
    ):
        if not _has_table(table_name):
            continue
        for index_name in indexes:
            if _has_index(table_name, index_name):
                op.drop_index(index_name, table_name=table_name)
        op.drop_table(table_name)
