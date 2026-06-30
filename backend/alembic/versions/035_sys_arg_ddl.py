"""迁移脚本：035_sys_arg_ddl

迁移版本 ID： 29559ee607af
上一版本： e8b470d2b150
创建时间： 2025-08-15 11:43:26.175792
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
    是什么：upgrade 是 backend/alembic/versions/035_sys_arg_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
    是什么：downgrade 是 backend/alembic/versions/035_sys_arg_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_index(op.f('ix_sys_arg_id'), table_name='sys_arg')
    op.drop_table('sys_arg')
