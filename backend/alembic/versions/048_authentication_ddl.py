"""迁移脚本：048_authentication_ddl

迁移版本 ID： 073bf544b373
上一版本： c1b794a961ce
创建时间： 2025-10-30 14:11:29.786938
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes

# Alembic 使用的迁移版本标识。
revision = '073bf544b373'
down_revision = 'c1b794a961ce'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/048_authentication_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.create_table('sys_authentication',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('name', sa.String(255), nullable=False),
    sa.Column('type', sa.Integer(), nullable=False),
    sa.Column('config', sa.Text(), nullable=True),
    sa.Column('enable', sa.Boolean(), nullable=False),
    sa.Column('valid', sa.Boolean(), nullable=False),
    sa.Column('create_time', sa.BigInteger(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sys_authentication_id'), 'sys_authentication', ['id'], unique=False)

    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/048_authentication_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_index(op.f('ix_sys_authentication_id'), table_name='sys_authentication')
    op.drop_table('sys_authentication')
    # ### Alembic 命令结束 ###
