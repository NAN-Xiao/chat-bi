"""084_remove_legacy_chat_name_param

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-06-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4c5d6e7f8a9'
down_revision = 'a3b4c5d6e7f8'
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _has_table('sys_arg'):
        return

    conn = op.get_bind()
    old_key = "chat." + "sql" + "bot_name"
    new_key = "chat.zhishu_name"
    has_new = conn.execute(
        sa.text("SELECT 1 FROM sys_arg WHERE pkey = :new_key LIMIT 1"),
        {"new_key": new_key},
    ).first()

    if has_new:
        conn.execute(
            sa.text("DELETE FROM sys_arg WHERE pkey = :old_key"),
            {"old_key": old_key},
        )
        return

    conn.execute(
        sa.text("UPDATE sys_arg SET pkey = :new_key WHERE pkey = :old_key"),
        {"new_key": new_key, "old_key": old_key},
    )


def downgrade():
    return
