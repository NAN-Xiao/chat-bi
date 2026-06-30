"""迁移脚本：010_modify_chat

迁移版本 ID： bfa10ce83d73
上一版本： 8dc3b1bdbfef
创建时间： 2025-06-18 14:16:39.230619
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = 'bfa10ce83d73'
down_revision = 'a3af70d43e98'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/013_modify_chat.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('chat_record', sa.Column('analysis', sa.Text(), nullable=True))
    op.add_column('chat_record', sa.Column('predict', sa.Text(), nullable=True))
    op.add_column('chat_record', sa.Column('full_analysis_message', sa.Text(), nullable=True))
    op.add_column('chat_record', sa.Column('full_predict_message', sa.Text(), nullable=True))
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/013_modify_chat.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_column('chat_record', 'full_predict_message')
    op.drop_column('chat_record', 'full_analysis_message')
    op.drop_column('chat_record', 'predict')
    op.drop_column('chat_record', 'analysis')
    # ### Alembic 命令结束 ###
