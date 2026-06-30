"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = 'b049c9f8ca5b'
down_revision = '4c6d18a18bd4'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.add_column('ds_permission', sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True))
    op.alter_column('ds_permission', 'auth_target_type',
               existing_type=sa.VARCHAR(length=128),
               nullable=True)
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.alter_column('ds_permission', 'auth_target_type',
               existing_type=sa.VARCHAR(length=128),
               nullable=False)
    op.drop_column('ds_permission', 'name')
    # ### Alembic 命令结束 ###
