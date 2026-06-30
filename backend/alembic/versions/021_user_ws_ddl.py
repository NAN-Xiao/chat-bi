"""迁移脚本：021_user_ws_ddl

迁移版本 ID： 440e9e41da3c
上一版本： a6b44114c17f
创建时间： 2025-07-07 17:21:46.858887
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
    是什么：upgrade 是 backend/alembic/versions/021_user_ws_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
    是什么：downgrade 是 backend/alembic/versions/021_user_ws_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_table('sys_user_ws')
