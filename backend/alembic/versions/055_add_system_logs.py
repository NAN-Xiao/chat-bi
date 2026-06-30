"""空迁移说明

迁移版本 ID： 3d4bd2d673dc
上一版本： 24e961f6326b
创建时间： 2025-12-19 13:30:54.743171
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
    是什么：upgrade 是 backend/alembic/versions/055_add_system_logs.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
    是什么：downgrade 是 backend/alembic/versions/055_add_system_logs.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_table('sys_logs')
