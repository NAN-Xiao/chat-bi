"""迁移脚本：062_update_chat_log_dll

迁移版本 ID： c9ab05247503
上一版本： 547df942eb90
创建时间： 2026-01-27 14:20:35.069255
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = 'c9ab05247503'
down_revision = '547df942eb90'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/062_update_chat_log_dll.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('chat_log', sa.Column('local_operation', sa.Boolean(), nullable=True))
    sql = '''
    UPDATE chat_log SET local_operation = false
    '''
    op.execute(sql)
    op.alter_column('chat_log', 'local_operation',
                    existing_type=sa.BOOLEAN(),
                    nullable=False)
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/062_update_chat_log_dll.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_column('chat_log', 'local_operation')
    # ### Alembic 命令结束 ###
