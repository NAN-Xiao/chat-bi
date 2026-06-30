"""迁移脚本：068_alter_sys_logs_user_agent_length

迁移版本 ID： a1b2c3d4e5f6
上一版本： e51127e9aa4a
创建时间： 2026-06-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# Alembic 使用的迁移版本标识。
revision = 'a1b2c3d4e5f6'
down_revision = 'e51127e9aa4a'
branch_labels = None
depends_on = None


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/068_alter_sys_logs_user_agent_length.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.alter_column('sys_logs', 'user_agent',
                    existing_type=sa.VARCHAR(length=255),
                    type_=sa.VARCHAR(length=500),
                    existing_nullable=True)


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/068_alter_sys_logs_user_agent_length.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.alter_column('sys_logs', 'user_agent',
                    existing_type=sa.VARCHAR(length=500),
                    type_=sa.VARCHAR(length=255),
                    existing_nullable=True)
