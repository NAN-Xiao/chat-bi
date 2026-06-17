"""081_add_custom_prompt_visibility_scope

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-06-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1f2a3b4c5d6'
down_revision = 'd0e1f2a3b4c5'
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

    if not _has_column('custom_prompt', 'visibility_scope'):
        op.add_column(
            'custom_prompt',
            sa.Column('visibility_scope', sa.String(length=32), nullable=True),
        )

    op.execute(
        """
        UPDATE custom_prompt AS cp
        SET visibility_scope = CASE
            WHEN cp.create_by IS NULL THEN 'ADMIN_PUBLIC'
            WHEN EXISTS (
                SELECT 1
                FROM sys_user AS u
                WHERE u.id = cp.create_by
                  AND u.system_role IN ('system_admin', 'collab_admin')
            ) THEN 'ADMIN_PUBLIC'
            ELSE 'USER_PRIVATE'
        END
        WHERE cp.visibility_scope IS NULL
           OR cp.visibility_scope NOT IN ('ADMIN_PUBLIC', 'USER_PRIVATE')
        """
    )

    op.alter_column(
        'custom_prompt',
        'visibility_scope',
        existing_type=sa.String(length=32),
        nullable=False,
        server_default='ADMIN_PUBLIC',
    )


def downgrade():
    if _has_table('custom_prompt') and _has_column('custom_prompt', 'visibility_scope'):
        op.drop_column('custom_prompt', 'visibility_scope')
