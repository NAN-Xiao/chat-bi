"""079_add_custom_prompt_model_owner

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade():
    if not _has_table('custom_prompt'):
        return

    if not _has_column('custom_prompt', 'ai_model_id'):
        op.add_column('custom_prompt', sa.Column('ai_model_id', sa.BigInteger(), nullable=True))

    if not _has_column('custom_prompt', 'create_by'):
        op.add_column('custom_prompt', sa.Column('create_by', sa.BigInteger(), nullable=True))
        op.execute(
            """
            UPDATE custom_prompt
            SET create_by = (
                SELECT id
                FROM sys_user
                ORDER BY
                    CASE WHEN system_role = 'system_admin' THEN 0 ELSE 1 END,
                    create_time,
                    id
                LIMIT 1
            )
            WHERE create_by IS NULL
            """
        )


def downgrade():
    if not _has_table('custom_prompt'):
        return

    if _has_column('custom_prompt', 'create_by'):
        op.drop_column('custom_prompt', 'create_by')
    if _has_column('custom_prompt', 'ai_model_id'):
        op.drop_column('custom_prompt', 'ai_model_id')
