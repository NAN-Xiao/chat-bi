"""103_custom_prompt_user_preference

Revision ID: d31c7b9a4e02
Revises: ac22d4e6f810
Create Date: 2026-06-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "d31c7b9a4e02"
down_revision = "ac22d4e6f810"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table("custom_prompt_user_preference"):
        return
    op.create_table(
        "custom_prompt_user_preference",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("custom_prompt_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("update_time", sa.DateTime(timezone=False), nullable=True),
        sa.UniqueConstraint(
            "custom_prompt_id",
            "user_id",
            name="uq_custom_prompt_user_preference_prompt_user",
        ),
    )
    op.create_index(
        "idx_custom_prompt_user_preference_user",
        "custom_prompt_user_preference",
        ["user_id"],
    )
    op.create_index(
        "idx_custom_prompt_user_preference_prompt",
        "custom_prompt_user_preference",
        ["custom_prompt_id"],
    )


def downgrade() -> None:
    if not _has_table("custom_prompt_user_preference"):
        return
    op.drop_index("idx_custom_prompt_user_preference_prompt", table_name="custom_prompt_user_preference")
    op.drop_index("idx_custom_prompt_user_preference_user", table_name="custom_prompt_user_preference")
    op.drop_table("custom_prompt_user_preference")
