"""迁移脚本：056_api_key_ddl

迁移版本 ID： d9a5589fc00b
上一版本： 3d4bd2d673dc
创建时间： 2025-12-23 13:41:26.705947
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
    是什么：upgrade 是 backend/alembic/versions/056_api_key_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
    是什么：downgrade 是 backend/alembic/versions/056_api_key_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_index(op.f('ix_sys_apikey_id'), table_name='sys_apikey')
    op.drop_table('sys_apikey')
    # ### Alembic 命令结束 ###
