"""迁移脚本：074_user_system_roles

迁移版本 ID： d4e5f6a7b8c9
上一版本： c3d4e5f6a7b8
创建时间： 2026-06-14 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# Alembic 使用的迁移版本标识。
revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/074_user_system_roles.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/074_user_system_roles.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/074_user_system_roles.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_column('sys_user', 'system_role'):
        op.add_column(
            'sys_user',
            sa.Column('system_role', sa.String(length=32), nullable=False, server_default='viewer'),
        )
    op.execute("UPDATE sys_user SET system_role = 'viewer' WHERE system_role IS NULL OR system_role = ''")
    op.execute("UPDATE sys_user SET system_role = 'system_admin' WHERE account = 'admin'")


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/074_user_system_roles.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if _has_column('sys_user', 'system_role'):
        op.drop_column('sys_user', 'system_role')
