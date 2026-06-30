"""迁移脚本：022_assistant_ddl

迁移版本 ID： e6b20ae73606
上一版本： 440e9e41da3c
创建时间： 2025-07-09 18:20:27.160183
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# Alembic 使用的迁移版本标识。
revision = 'e6b20ae73606'
down_revision = '440e9e41da3c'
branch_labels = None
depends_on = None


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/022_assistant_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.create_table(
        'sys_assistant',
        sa.Column('id', sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('domain', sa.String(255), nullable=False),
        sa.Column('type', sa.Integer(), nullable=False, default=0),
        sa.Column('configuration', sa.Text(), nullable=True),
        sa.Column('create_time', sa.BigInteger(), default=0, nullable=False)
    )
    op.create_index(op.f('ix_sys_assistant_id'), 'sys_assistant', ['id'], unique=False)


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/022_assistant_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_index(op.f('ix_sys_assistant_id'), table_name='sys_assistant')
    op.drop_table('sys_assistant')
