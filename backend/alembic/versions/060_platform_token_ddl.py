"""迁移脚本：060_platform_token_ddl

迁移版本 ID： b40e41c67db3
上一版本： db1a95567cbb
创建时间： 2026-01-04 15:50:31.550287
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = 'b40e41c67db3'
down_revision = 'db1a95567cbb'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/060_platform_token_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.create_table('sys_platform_token',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('token', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('create_time', sa.BigInteger(), nullable=False),
    sa.Column('exp_time', sa.BigInteger(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sys_platform_token_id'), 'sys_platform_token', ['id'], unique=False)
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/060_platform_token_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_index(op.f('ix_sys_platform_token_id'), table_name='sys_platform_token')
    op.drop_table('sys_platform_token')
    # ### Alembic 命令结束 ###
