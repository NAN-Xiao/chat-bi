"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
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
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
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
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.drop_table('terminology')
    # ### Alembic 命令结束 ###
