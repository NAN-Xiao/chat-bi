"""空迁移说明

迁移版本 ID： fb2e8dd19158
上一版本： c431a0bf478b
创建时间： 2025-12-29 17:18:49.072320
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = 'fb2e8dd19158'
down_revision = 'c431a0bf478b'
branch_labels = None
depends_on = None


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/058_update_chat.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('chat', sa.Column('recommended_question_answer', sa.TEXT(), nullable=True))
    op.add_column('chat', sa.Column('recommended_question', sa.TEXT(), nullable=True))
    op.add_column('chat', sa.Column('recommended_generate', sa.Boolean(),  nullable=True))
    # ### Alembic 命令结束 ###


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/058_update_chat.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_column('chat', 'recommended_question_answer')
    op.drop_column('chat', 'recommended_question')
    op.drop_column('chat', 'recommended_generate')
    # ### Alembic 命令结束 ###
