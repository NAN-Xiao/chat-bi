"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa

revision = '5755c0b95839'
down_revision = 'e408f8766753'
branch_labels = None
depends_on = None


def upgrade():
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
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
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.drop_column('chat', 'brief_generate')
    # ### Alembic 命令结束 ###