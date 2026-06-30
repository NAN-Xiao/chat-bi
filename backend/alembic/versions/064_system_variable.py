"""迁移脚本：062_system_variable

迁移版本 ID： ed947895d470
上一版本： 547df942eb90
创建时间： 2026-01-26 10:16:59.877303
"""
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy import String, BigInteger, DateTime
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import table, column

# Alembic 使用的迁移版本标识。
revision = 'ed947895d470'
down_revision = 'c8751179a8de'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/064_system_variable.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.create_table('system_variable',
                    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
                    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
                    sa.Column('var_type', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
                    sa.Column('type', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
                    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
                    sa.Column('create_time', sa.DateTime(), nullable=True),
                    sa.Column('create_by', sa.BigInteger(), nullable=True),
                    sa.PrimaryKeyConstraint('id')
                    )

    variable_table = table(
        "system_variable",
        column("id", BigInteger),
        column("name", String),
        column("var_type", String),
        column("type", String),
        column("value", JSONB),
        column("create_time", DateTime),
        column("create_by", BigInteger),
    )

    op.bulk_insert(
        variable_table,
        [
            {
                "name": "i18n_variable.name",
                "var_type": "text",
                "type": "system",
                "value": ["name"],
                "create_time": None,
                "create_by": None
            },
            {
                "name": "i18n_variable.account",
                "var_type": "text",
                "type": "system",
                "value": ["account"],
                "create_time": None,
                "create_by": None
            },
            {
                "name": "i18n_variable.email",
                "var_type": "text",
                "type": "system",
                "value": ["email"],
                "create_time": None,
                "create_by": None
            }
        ]
    )
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/064_system_variable.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_table('system_variable')
    # ### Alembic 命令结束 ###
