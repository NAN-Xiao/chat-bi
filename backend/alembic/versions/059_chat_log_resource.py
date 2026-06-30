"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = 'db1a95567cbb'
down_revision = 'fb2e8dd19158'
branch_labels = None
depends_on = None


def upgrade():
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.create_table('sys_logs_resource',
                    sa.Column('id', sa.BIGINT(),
                              sa.Identity(always=True, start=1, increment=1, minvalue=1, maxvalue=999999999999999,
                                          cycle=False, cache=1), autoincrement=True, nullable=False),
                    sa.Column('resource_id', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
                    sa.Column('module', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
                    sa.Column('resource_name', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
                    sa.Column('log_id', sa.BIGINT(), autoincrement=False, nullable=True),
                    sa.PrimaryKeyConstraint('id', name=op.f('sys_logs_resource_pkey'))
                    )
    # ### Alembic 命令结束 ###
def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.drop_table('sys_logs_resource')
    # ### Alembic 命令结束 ###
