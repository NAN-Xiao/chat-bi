"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# Alembic 使用的迁移版本标识。
revision = '440e9e41da3c'
down_revision = 'a6b44114c17f'
branch_labels = None
depends_on = None


def upgrade():
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.create_table(
        'sys_user_ws',
        sa.Column('id', sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column('uid', sa.BigInteger(), nullable=False),
        sa.Column('oid', sa.BigInteger(), nullable=False),
        sa.Column('weight', sa.Integer(), nullable=False)
    )
    op.create_index(op.f('ix_sys_user_ws_id'), 'sys_user_ws', ['id'], unique=False)


def downgrade():
    #op.drop_index(op.f('ix_sys_user_ws_id'), table_name='sys_user_ws')
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.drop_table('sys_user_ws')
