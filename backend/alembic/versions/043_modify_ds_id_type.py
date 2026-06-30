"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
import sqlalchemy as sa
from alembic import op

# Alembic 使用的迁移版本标识。
revision = 'dac062c1f7b1'
down_revision = 'a487d9c69341'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.alter_column('core_datasource', 'id',
                    existing_type=sa.INTEGER(),
                    type_=sa.BigInteger(),
                    existing_nullable=False,
                    autoincrement=True)
    op.alter_column('core_field', 'id',
                    existing_type=sa.INTEGER(),
                    type_=sa.BigInteger(),
                    existing_nullable=False,
                    autoincrement=True)
    op.alter_column('core_table', 'id',
                    existing_type=sa.INTEGER(),
                    type_=sa.BigInteger(),
                    existing_nullable=False,
                    autoincrement=True)
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.alter_column('core_table', 'id',
                    existing_type=sa.BigInteger(),
                    type_=sa.INTEGER(),
                    existing_nullable=False,
                    autoincrement=True)
    op.alter_column('core_field', 'id',
                    existing_type=sa.BigInteger(),
                    type_=sa.INTEGER(),
                    existing_nullable=False,
                    autoincrement=True)
    op.alter_column('core_datasource', 'id',
                    existing_type=sa.BigInteger(),
                    type_=sa.INTEGER(),
                    existing_nullable=False,
                    autoincrement=True)
    # ### Alembic 命令结束 ###
