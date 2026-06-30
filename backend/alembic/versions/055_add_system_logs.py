"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = '3d4bd2d673dc'
down_revision = '24e961f6326b'
branch_labels = None
depends_on = None


def upgrade():
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.create_table('sys_logs',
                    sa.Column('id', sa.BIGINT(), autoincrement=True, nullable=False),
                    sa.Column('operation_type', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
                    sa.Column('operation_detail', sa.TEXT(), autoincrement=False, nullable=True),
                    sa.Column('user_id', sa.BIGINT(), autoincrement=False, nullable=True),
                    sa.Column('operation_status', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
                    sa.Column('oid', sa.BIGINT(), autoincrement=False, nullable=True),
                    sa.Column('ip_address', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
                    sa.Column('user_agent', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
                    sa.Column('execution_time', sa.BIGINT(), autoincrement=False, nullable=True),
                    sa.Column('error_message', sa.TEXT(), autoincrement=False, nullable=True),
                    sa.Column('create_time', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
                    sa.Column('module', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
                    sa.Column('remark', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
                    sa.Column('resource_id',sa.TEXT(), autoincrement=False, nullable=True),
                    sa.Column('request_method', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
                    sa.Column('request_path', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
                    sa.PrimaryKeyConstraint('id', name=op.f('sys_logs_pkey'))
                    )


def downgrade():
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.drop_table('sys_logs')
