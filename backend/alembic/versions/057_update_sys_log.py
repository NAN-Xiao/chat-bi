"""空迁移说明

迁移版本 ID： c431a0bf478b
上一版本： d9a5589fc00b
创建时间： 2025-12-25 12:50:59.790439
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = 'c431a0bf478b'
down_revision = 'd9a5589fc00b'
branch_labels = None
depends_on = None


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/057_update_sys_log.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('sys_logs', sa.Column('user_name', sa.VARCHAR(length=255), autoincrement=False, nullable=True))
    op.add_column('sys_logs', sa.Column('resource_name', sa.TEXT(), autoincrement=False, nullable=True))

def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/057_update_sys_log.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_column('sys_logs', 'user_name')
    op.drop_column('sys_logs', 'resource_name')

