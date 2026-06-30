"""空迁移说明

迁移版本 ID： 5755c0b95839
上一版本： e408f8766753
创建时间： 2025-12-02 13:46:06.905576
"""
from alembic import op
import sqlalchemy as sa

revision = '5755c0b95839'
down_revision = 'e408f8766753'
branch_labels = None
depends_on = None


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/053_update_chat.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('chat', sa.Column('brief_generate', sa.Boolean(), nullable=True))
    op.execute("UPDATE chat SET brief_generate = true WHERE brief_generate IS NULL")
    with op.batch_alter_table('chat') as batch_op:
        batch_op.alter_column('brief_generate',
                             server_default=sa.text('false'),
                             nullable=False)
    # ### Alembic 命令结束 ###


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/053_update_chat.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_column('chat', 'brief_generate')
    # ### Alembic 命令结束 ###