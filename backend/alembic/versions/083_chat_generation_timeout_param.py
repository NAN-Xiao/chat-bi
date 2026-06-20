"""083_chat_generation_timeout_param

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-06-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3b4c5d6e7f8'
down_revision = 'f2a3b4c5d6e7'
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
        SELECT next_id, 'chat.generation_total_timeout_seconds', '300', 'str', 1
        FROM (SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM sys_arg) AS ids
        WHERE NOT EXISTS (
            SELECT 1 FROM sys_arg WHERE pkey = 'chat.generation_total_timeout_seconds'
        )
        """
    )


def downgrade():
    if not _has_table('sys_arg'):
        return

    op.execute(
        """
        DELETE FROM sys_arg
        WHERE pkey = 'chat.generation_total_timeout_seconds'
        """
    )
