"""迁移脚本：040_modify_ai_model

迁移版本 ID： 0fc14c2cfe41
上一版本： 25cbc85766fd
创建时间： 2025-08-26 23:30:50.192799
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
    是什么：upgrade 是 backend/alembic/versions/040_modify_ai_model.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
    是什么：downgrade 是 backend/alembic/versions/040_modify_ai_model.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
