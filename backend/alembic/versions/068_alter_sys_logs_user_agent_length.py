"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
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
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.alter_column('sys_logs', 'user_agent',
                    existing_type=sa.VARCHAR(length=255),
                    type_=sa.VARCHAR(length=500),
                    existing_nullable=True)


def downgrade():
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.alter_column('sys_logs', 'user_agent',
                    existing_type=sa.VARCHAR(length=500),
                    type_=sa.VARCHAR(length=255),
                    existing_nullable=True)
