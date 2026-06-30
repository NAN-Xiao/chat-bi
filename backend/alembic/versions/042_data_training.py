"""迁移脚本：042_data_training

迁移版本 ID： a487d9c69341
上一版本： c4c3c36b720d
创建时间： 2025-09-15 15:41:43.332771
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql
import pgvector

# Alembic 使用的迁移版本标识。
revision = 'a487d9c69341'
down_revision = 'c4c3c36b720d'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/042_data_training.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.create_table('data_training',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('oid', sa.BigInteger(), nullable=True),
    sa.Column('datasource', sa.BigInteger(), nullable=True),
    sa.Column('create_time', sa.DateTime(), nullable=True),
    sa.Column('question', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )

    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###

    """
    是什么：downgrade 是 backend/alembic/versions/042_data_training.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_table('data_training')
    # ### Alembic 命令结束 ###
