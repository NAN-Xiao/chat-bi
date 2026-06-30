"""迁移脚本：075_dashboard_share_store

迁移版本 ID： e5f6a7b8c9d0
上一版本： d4e5f6a7b8c9
创建时间： 2026-06-15 00:00:00.000000
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
    是什么：_has_table 是 backend/alembic/versions/075_dashboard_share_store.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是 backend/alembic/versions/075_dashboard_share_store.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_index 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/075_dashboard_share_store.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
    是什么：downgrade 是 backend/alembic/versions/075_dashboard_share_store.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if _has_index('core_dashboard_share', 'idx_core_dashboard_share_type'):
        op.drop_index('idx_core_dashboard_share_type', table_name='core_dashboard_share')
    if _has_index('core_dashboard_share', 'idx_core_dashboard_share_datasource'):
        op.drop_index('idx_core_dashboard_share_datasource', table_name='core_dashboard_share')
    if _has_table('core_dashboard_share'):
        op.drop_table('core_dashboard_share')
