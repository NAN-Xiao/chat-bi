"""迁移脚本：031_modify_chat_record

迁移版本 ID： bd2ed188b5bd
上一版本： c1d7ac00b3a8
创建时间： 2025-07-21 17:27:55.985821
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = 'bd2ed188b5bd'
down_revision = 'c1d7ac00b3a8'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/031_modify_chat_record.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.alter_column('chat_record', 'engine_type',
               existing_type=sa.VARCHAR(length=64),
               nullable=True)
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/031_modify_chat_record.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.alter_column('chat_record', 'engine_type',
               existing_type=sa.VARCHAR(length=64),
               nullable=False)
    # ### Alembic 命令结束 ###
