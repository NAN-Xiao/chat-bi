"""迁移脚本：036_modify_assistant

迁移版本 ID： 646e7ca28e0e
上一版本： 29559ee607af
创建时间： 2025-08-18 16:12:46.041413
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# Alembic 使用的迁移版本标识。
revision = '646e7ca28e0e'
down_revision = '29559ee607af'
branch_labels = None
depends_on = None


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/036_modify_assistant.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('sys_assistant', sa.Column('app_id', sa.String(255), nullable=True, comment='app_id'))
    op.add_column('sys_assistant', sa.Column('app_secret', sa.String(255), nullable=True, comment='app_secret'))


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/036_modify_assistant.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_column('sys_assistant', 'app_id')
    op.drop_column('sys_assistant', 'app_secret')
