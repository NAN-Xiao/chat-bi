"""071_remove_workspace_scope

Revision ID: d9e0f1a2b3c4
Revises: b7c1f2d3e4a5
Create Date: 2026-06-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd9e0f1a2b3c4'
down_revision = 'b7c1f2d3e4a5'
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_view(view_name: str) -> bool:
    return view_name in sa.inspect(op.get_bind()).get_view_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    if _has_column(table_name, column_name):
        op.drop_column(table_name, column_name)


def _drop_table_if_exists(table_name: str) -> None:
    if _has_table(table_name):
        op.drop_table(table_name)


def _drop_view_if_exists(view_name: str) -> None:
    if _has_view(view_name):
        op.execute(f"DROP VIEW {view_name}")


def _drop_relation_if_exists(relation_name: str) -> None:
    _drop_view_if_exists(relation_name)
    _drop_table_if_exists(relation_name)


def upgrade():
    _drop_relation_if_exists('sys_workspace')
    _drop_table_if_exists('sys_user_ws')
    _drop_table_if_exists('ai_model_workspace_mapping')

    _drop_column_if_exists('sys_user', 'oid')
    _drop_column_if_exists('core_datasource', 'oid')
    _drop_column_if_exists('core_datasource_user', 'oid')
    _drop_column_if_exists('sys_assistant', 'oid')
    _drop_column_if_exists('terminology', 'oid')
    _drop_column_if_exists('data_training', 'oid')
    _drop_column_if_exists('chat', 'oid')
    _drop_column_if_exists('sys_logs', 'oid')
    _drop_column_if_exists('core_dashboard', 'workspace_id')
    _drop_column_if_exists('custom_prompt', 'oid')
    _drop_column_if_exists('ds_rules', 'oid')


def downgrade():
    _drop_relation_if_exists('sys_workspace')

    if not _has_column('sys_user', 'oid'):
        op.add_column('sys_user', sa.Column('oid', sa.BigInteger(), nullable=True))
        op.execute("UPDATE sys_user SET oid = 1 WHERE oid IS NULL")
        op.alter_column('sys_user', 'oid', existing_type=sa.BigInteger(), nullable=False, server_default='1')

    if not _has_column('core_datasource', 'oid'):
        op.add_column('core_datasource', sa.Column('oid', sa.BigInteger(), nullable=True))
        op.execute("UPDATE core_datasource SET oid = 1 WHERE oid IS NULL")

    if not _has_column('core_datasource_user', 'oid'):
        op.add_column('core_datasource_user', sa.Column('oid', sa.BigInteger(), nullable=True))
        op.execute("UPDATE core_datasource_user SET oid = 1 WHERE oid IS NULL")

    for table_name in ('sys_assistant', 'terminology', 'data_training', 'chat'):
        if not _has_column(table_name, 'oid'):
            op.add_column(table_name, sa.Column('oid', sa.BigInteger(), nullable=True))
            op.execute(f"UPDATE {table_name} SET oid = 1 WHERE oid IS NULL")

    if not _has_column('sys_logs', 'oid'):
        op.add_column('sys_logs', sa.Column('oid', sa.BigInteger(), nullable=True))

    if not _has_column('core_dashboard', 'workspace_id'):
        op.add_column('core_dashboard', sa.Column('workspace_id', sa.String(length=50), nullable=True))

    if not _has_column('custom_prompt', 'oid'):
        op.add_column('custom_prompt', sa.Column('oid', sa.BigInteger(), nullable=True))
        op.execute("UPDATE custom_prompt SET oid = 1 WHERE oid IS NULL")

    if not _has_column('ds_rules', 'oid'):
        op.add_column('ds_rules', sa.Column('oid', sa.BigInteger(), nullable=True))
        op.execute("UPDATE ds_rules SET oid = 1 WHERE oid IS NULL")
        op.alter_column('ds_rules', 'oid', existing_type=sa.BigInteger(), nullable=False, server_default='1')

    if not _has_table('sys_workspace'):
        op.create_table(
            'sys_workspace',
            sa.Column('id', sa.BigInteger(), primary_key=True, nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('create_time', sa.BigInteger(), default=0, nullable=False),
        )
        op.bulk_insert(
            sa.table(
                'sys_workspace',
                sa.column('id', sa.BigInteger()),
                sa.column('name', sa.String()),
                sa.column('create_time', sa.BigInteger()),
            ),
            [{'id': 1, 'name': 'i18n_default_workspace', 'create_time': 1672531199000}],
        )

    if not _has_table('sys_user_ws'):
        op.create_table(
            'sys_user_ws',
            sa.Column('id', sa.BigInteger(), primary_key=True, nullable=False),
            sa.Column('uid', sa.BigInteger(), nullable=False),
            sa.Column('oid', sa.BigInteger(), nullable=False),
            sa.Column('weight', sa.Integer(), nullable=False, server_default='0'),
        )

    if not _has_table('ai_model_workspace_mapping'):
        op.create_table(
            'ai_model_workspace_mapping',
            sa.Column('id', sa.BigInteger(), primary_key=True, nullable=False),
            sa.Column('ai_model_id', sa.BigInteger(), nullable=True),
            sa.Column('workspace_id', sa.BigInteger(), nullable=True),
        )
