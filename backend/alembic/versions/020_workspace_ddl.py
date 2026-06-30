"""迁移脚本：020_workspace_ddl

迁移版本 ID： a6b44114c17f
上一版本： dcaecd481715
创建时间： 2025-07-06 18:03:36.143060
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
    是什么：upgrade 是 backend/alembic/versions/020_workspace_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
    是什么：downgrade 是 backend/alembic/versions/020_workspace_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_index(op.f('ix_sys_workspace_id'), table_name='sys_workspace')
    op.drop_table('sys_workspace')

