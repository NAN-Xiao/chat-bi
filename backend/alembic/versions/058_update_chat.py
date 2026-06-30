"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
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
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.add_column('chat', sa.Column('recommended_question_answer', sa.TEXT(), nullable=True))
    op.add_column('chat', sa.Column('recommended_question', sa.TEXT(), nullable=True))
    op.add_column('chat', sa.Column('recommended_generate', sa.Boolean(),  nullable=True))
    # ### Alembic 命令结束 ###


def downgrade():
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.drop_column('chat', 'recommended_question_answer')
    op.drop_column('chat', 'recommended_question')
    op.drop_column('chat', 'recommended_generate')
    # ### Alembic 命令结束 ###
