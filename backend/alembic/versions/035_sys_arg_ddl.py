"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# Alembic 使用的迁移版本标识。
revision = '29559ee607af'
down_revision = 'e8b470d2b150'
branch_labels = None
depends_on = None


def upgrade():
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.create_table(
        'sys_arg',
        sa.Column('id', sa.BigInteger(), primary_key=True, nullable=False, comment='ID'),
        sa.Column('pkey', sa.String(255), nullable=False, comment='pkey'),
        sa.Column('pval', sa.String(255), nullable=True, comment='pval'),
        sa.Column('ptype', sa.String(255), nullable=False, server_default='str', comment='str or file'),
        sa.Column('sort_no', sa.Integer(), nullable=False, server_default='1', comment='sort_no')
    )
    op.create_index(op.f('ix_sys_arg_id'), 'sys_arg', ['id'], unique=False)


def downgrade():
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.drop_index(op.f('ix_sys_arg_id'), table_name='sys_arg')
    op.drop_table('sys_arg')
