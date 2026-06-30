"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = 'd9a5589fc00b'
down_revision = '3d4bd2d673dc'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.create_table('sys_apikey',
    sa.Column('access_key', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('secret_key', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('create_time', sa.BigInteger(), nullable=False),
    sa.Column('uid', sa.BigInteger(), nullable=False),
    sa.Column('status', sa.Boolean(), nullable=False),
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sys_apikey_id'), 'sys_apikey', ['id'], unique=False)
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.drop_index(op.f('ix_sys_apikey_id'), table_name='sys_apikey')
    op.drop_table('sys_apikey')
    # ### Alembic 命令结束 ###
