"""空迁移说明

迁移版本 ID： db1a95567cbb
上一版本： fb2e8dd19158
创建时间： 2025-12-30 12:29:14.290394
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
    是什么：upgrade 是 backend/alembic/versions/059_chat_log_resource.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
    是什么：downgrade 是 backend/alembic/versions/059_chat_log_resource.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_table('sys_logs_resource')
    # ### Alembic 命令结束 ###
