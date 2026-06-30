"""迁移脚本：039_create_terminology

迁移版本 ID： 25cbc85766fd
上一版本： fc23c4f3e755
创建时间： 2025-08-25 11:38:32.990973
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = '25cbc85766fd'
down_revision = 'fc23c4f3e755'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/039_create_terminology.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.create_table('terminology',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('pid', sa.BigInteger(), nullable=True),
    sa.Column('create_time', sa.DateTime(), nullable=True),
    sa.Column('word', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('embedding', VECTOR(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )

    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/039_create_terminology.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_table('terminology')
    # ### Alembic 命令结束 ###
