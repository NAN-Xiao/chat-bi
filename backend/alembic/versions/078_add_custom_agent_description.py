"""078_add_custom_agent_description

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade():
    if not _has_table('custom_prompt') or _has_column('custom_prompt', 'description'):
        return

    op.add_column('custom_prompt', sa.Column('description', sa.Text(), nullable=True))


def downgrade():
    if not _has_table('custom_prompt') or not _has_column('custom_prompt', 'description'):
        return

    op.drop_column('custom_prompt', 'description')
