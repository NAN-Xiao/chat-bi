"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa


# Alembic 使用的迁移版本标识。
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not _has_table(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    if not _has_table('core_dashboard_share'):
        op.create_table(
            'core_dashboard_share',
            sa.Column('id', sa.String(length=50), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=True),
            sa.Column('datasource', sa.BigInteger(), nullable=True),
            sa.Column('share_type', sa.String(length=32), nullable=False),
            sa.Column('source_dashboard_id', sa.String(length=50), nullable=True),
            sa.Column('source_view_id', sa.String(length=50), nullable=True),
            sa.Column('component_data', sa.Text(), nullable=True),
            sa.Column('canvas_style_data', sa.Text(), nullable=True),
            sa.Column('canvas_view_info', sa.Text(), nullable=True),
            sa.Column('create_time', sa.BigInteger(), nullable=True),
            sa.Column('create_by', sa.String(length=255), nullable=True),
            sa.Column('update_time', sa.BigInteger(), nullable=True),
            sa.Column('update_by', sa.String(length=255), nullable=True),
            sa.Column('delete_flag', sa.SmallInteger(), nullable=True),
            sa.Column('delete_time', sa.BigInteger(), nullable=True),
            sa.Column('delete_by', sa.String(length=255), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
    if not _has_index('core_dashboard_share', 'idx_core_dashboard_share_datasource'):
        op.create_index(
            'idx_core_dashboard_share_datasource',
            'core_dashboard_share',
            ['datasource'],
            unique=False,
        )
    if not _has_index('core_dashboard_share', 'idx_core_dashboard_share_type'):
        op.create_index(
            'idx_core_dashboard_share_type',
            'core_dashboard_share',
            ['share_type'],
            unique=False,
        )


def downgrade():
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    if _has_index('core_dashboard_share', 'idx_core_dashboard_share_type'):
        op.drop_index('idx_core_dashboard_share_type', table_name='core_dashboard_share')
    if _has_index('core_dashboard_share', 'idx_core_dashboard_share_datasource'):
        op.drop_index('idx_core_dashboard_share_datasource', table_name='core_dashboard_share')
    if _has_table('core_dashboard_share'):
        op.drop_table('core_dashboard_share')
