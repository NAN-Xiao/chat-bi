"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# Alembic 使用的迁移版本标识。
revision = '0fc14c2cfe41'
down_revision = '25cbc85766fd'
branch_labels = None
depends_on = None


def upgrade():
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.alter_column(
        'ai_model',
        'api_key',
        type_=sa.Text(),
        existing_type=sa.String(length=255),
        existing_nullable=True
    )
    op.alter_column(
        'ai_model',
        'api_domain',
        type_=sa.Text(),
        existing_type=sa.String(length=255),
        existing_nullable=False
    )


def downgrade():
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.alter_column(
        'ai_model',
        'api_key',
        type_=sa.String(),
        existing_type=sa.Text(),
        existing_nullable=True
    )
    op.alter_column(
        'ai_model',
        'api_domain',
        type_=sa.String(),
        existing_type=sa.Text(),
        existing_nullable=False
    )
