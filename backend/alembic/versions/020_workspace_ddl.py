"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa
from sqlmodel import BigInteger, String, column, table


# Alembic 使用的迁移版本标识。
revision = 'a6b44114c17f'
down_revision = 'dcaecd481715'
branch_labels = None
depends_on = None


def upgrade():
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.create_table(
        'sys_workspace',
        sa.Column('id', sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('create_time', sa.BigInteger(), default=0, nullable=False)
    )
    op.create_index(op.f('ix_sys_workspace_id'), 'sys_workspace', ['id'], unique=False)

    accounts_table = table(
        "sys_workspace",
        column("id", BigInteger),
        column("name", String),
        column("create_time", BigInteger),
    )

    op.bulk_insert(
        accounts_table,
        [
            {
                "id": 1,
                "name": "i18n_default_workspace",
                "create_time": 1672531199000
            }
        ]
    )

def downgrade():
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.drop_index(op.f('ix_sys_workspace_id'), table_name='sys_workspace')
    op.drop_table('sys_workspace')

