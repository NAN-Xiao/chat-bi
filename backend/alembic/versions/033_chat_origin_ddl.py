"""迁移脚本：033_chat_origin_ddl

迁移版本 ID： 3cb5d6a54f2e
上一版本： 6549e47f9adc
创建时间： 2025-07-22 22:00:48.599729
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = '3cb5d6a54f2e'
down_revision = '6549e47f9adc'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/033_chat_origin_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('chat', sa.Column('origin', sa.Integer(), nullable=True, default=0))  # 0：默认，1：MCP，2：助手
    op.execute('UPDATE chat SET origin = 0 WHERE origin IS NULL')
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/033_chat_origin_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_column('chat', 'origin')
    # ### Alembic 命令结束 ###
