"""迁移脚本：049_user_platform_ddl

迁移版本 ID： b58a71ca6ae3
上一版本： 073bf544b373
创建时间： 2025-11-04 12:31:56.481582
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes

# Alembic 使用的迁移版本标识。
revision = 'b58a71ca6ae3'
down_revision = '073bf544b373'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/049_user_platform_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.create_table('sys_user_platform',
    sa.Column('uid', sa.BigInteger(), nullable=False),
    sa.Column('origin', sa.Integer(), server_default='0', nullable=False),
    sa.Column('platform_uid', sa.String(255), nullable=False),
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sys_user_platform_id'), 'sys_user_platform', ['id'], unique=False)

    op.add_column('sys_user', sa.Column('origin', sa.Integer(), server_default='0', nullable=False))

    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###

    """
    是什么：downgrade 是 backend/alembic/versions/049_user_platform_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_column('sys_user', 'origin')

    op.drop_index(op.f('ix_sys_user_platform_id'), table_name='sys_user_platform')
    op.drop_table('sys_user_platform')
    # ### Alembic 命令结束 ###
