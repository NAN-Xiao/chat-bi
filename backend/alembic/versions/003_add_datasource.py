"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# Alembic 使用的迁移版本标识。
revision = 'd116056121c3'
down_revision = '1c8bcc7e25c8'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.create_table('core_datasource',
    sa.Column('id', sa.Integer(), sa.Identity(always=True), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
    sa.Column('description', sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True),
    sa.Column('type', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('configuration', sa.Text(), nullable=True),
    sa.Column('create_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('create_by', sa.BigInteger(), nullable=True),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
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
    op.drop_table('core_datasource')
    # ### Alembic 命令结束 ###
