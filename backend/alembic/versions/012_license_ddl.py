"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa


# Alembic 使用的迁移版本标识。
revision = 'a3af70d43e98'
down_revision = '941e2355a94d'
branch_labels = None
depends_on = None


def upgrade():
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.create_table(
        'license',
        sa.Column('id', sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column('license_key', sa.Text(), default="", nullable=False),
        sa.Column('license_payload', sa.Text(), default="", nullable=False),
        sa.Column('create_time', sa.BigInteger(), default=0, nullable=False),
        sa.Column('update_time', sa.BigInteger(), default=0, nullable=False)
    )
    op.create_index(op.f('ix_license_id'), 'license', ['id'], unique=False)


def downgrade():
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.drop_table('license')
    op.drop_index(op.f('ix_license_id'), table_name='license')
