"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""


# Alembic 使用的迁移版本标识。
revision = '5348b743b05f'
down_revision = None
branch_labels = None
depends_on = None


from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.sql import table, column
from sqlalchemy import String, Integer, BigInteger
def upgrade():
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.create_table(
        'sys_user',
        sa.Column('id', sa.BIGINT, primary_key=True),
        sa.Column('account', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('password', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255)),
        sa.Column('oid', sa.BIGINT, nullable=False),
        sa.Column('status', sa.Integer, nullable=False),
        sa.Column('create_time', sa.BIGINT, nullable=False),
    )

    accounts_table = table(
        "sys_user",
        column("id", BigInteger),
        column("account", String),
        column("name", String),
        column("password", String),
        column("email", String),
        column("oid", BigInteger),
        column("status", Integer),
        column("create_time", BigInteger),
    )

    op.bulk_insert(
        accounts_table,
        [
            {
                "id": 1,
                "account": "admin",
                "name": "Administrator",
                "password": "8f32d1e371702c1b1b7346f4b07a701d",
                "email": "admin@example.com",
                "oid": 1,
                "status": 1,
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
    op.drop_table('sys_user')
