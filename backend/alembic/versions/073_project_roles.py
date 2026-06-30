"""迁移脚本：073_project_roles

迁移版本 ID： c3d4e5f6a7b8
上一版本： f2a4b6c8d0e1
创建时间： 2026-06-14 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# Alembic 使用的迁移版本标识。
revision = 'c3d4e5f6a7b8'
down_revision = 'f2a4b6c8d0e1'
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/073_project_roles.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/073_project_roles.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/073_project_roles.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_column('core_datasource_user', 'role'):
        op.add_column(
            'core_datasource_user',
            sa.Column('role', sa.String(length=32), nullable=False, server_default='viewer'),
        )
    op.execute("UPDATE core_datasource_user SET role = 'viewer' WHERE role IS NULL OR role = ''")


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/073_project_roles.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if _has_column('core_datasource_user', 'role'):
        op.drop_column('core_datasource_user', 'role')
