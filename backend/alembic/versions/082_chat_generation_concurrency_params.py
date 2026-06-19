"""082_chat_generation_concurrency_params

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2a3b4c5d6e7'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _has_table('sys_arg'):
        return

    op.execute(
        """
        INSERT INTO sys_arg (id, pkey, pval, ptype, sort_no)
        SELECT next_id, 'chat.generation_concurrency_limit_enabled', 'true', 'str', 1
        FROM (SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM sys_arg) AS ids
        WHERE NOT EXISTS (
            SELECT 1 FROM sys_arg WHERE pkey = 'chat.generation_concurrency_limit_enabled'
        )
        """
    )
    op.execute(
        """
        INSERT INTO sys_arg (id, pkey, pval, ptype, sort_no)
        SELECT next_id, 'chat.max_concurrent_generations_per_user', '1', 'str', 1
        FROM (SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM sys_arg) AS ids
        WHERE NOT EXISTS (
            SELECT 1 FROM sys_arg WHERE pkey = 'chat.max_concurrent_generations_per_user'
        )
        """
    )


def downgrade():
    if not _has_table('sys_arg'):
        return

    op.execute(
        """
        DELETE FROM sys_arg
        WHERE pkey IN (
            'chat.generation_concurrency_limit_enabled',
            'chat.max_concurrent_generations_per_user'
        )
        """
    )
