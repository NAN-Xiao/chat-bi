"""迁移脚本：063_update_chat_log_dll

迁移版本 ID： c8751179a8de
上一版本： c9ab05247503
创建时间： 2026-01-29 14:41:21.022781
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = 'c8751179a8de'
down_revision = 'c9ab05247503'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/063_update_chat_log_dll.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('chat_log', sa.Column('error', sa.Boolean(), nullable=True))
    sql = '''
    UPDATE chat_log SET error = false
    '''
    op.execute(sql)
    op.alter_column('chat_log', 'error',
                    existing_type=sa.BOOLEAN(),
                    nullable=False)
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/063_update_chat_log_dll.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_column('chat_log', 'error')
    # ### Alembic 命令结束 ###
