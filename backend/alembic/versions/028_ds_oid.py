"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
import sqlalchemy as sa
from alembic import op

# Alembic 使用的迁移版本标识。
revision = 'e96b16d3daab'
down_revision = 'b049c9f8ca5b'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.add_column('core_datasource', sa.Column('oid', sa.BigInteger(), nullable=True))
    op.execute('update core_datasource set oid = 1')
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.drop_column('core_datasource', 'oid')
    # ### Alembic 命令结束 ###
