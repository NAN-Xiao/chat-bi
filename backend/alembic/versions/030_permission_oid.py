"""迁移脚本：030_permission_oid

迁移版本 ID： c1d7ac00b3a8
上一版本： 77d4c39ec22f
创建时间： 2025-07-21 11:49:43.115524
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = 'c1d7ac00b3a8'
down_revision = '77d4c39ec22f'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/030_permission_oid.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('ds_rules', sa.Column('oid', sa.BigInteger(), nullable=True))
    op.alter_column('ds_permission', 'id',
                    existing_type=sa.INTEGER(),
                    type_=sa.BigInteger(),
                    existing_nullable=False,
                    autoincrement=True)
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/030_permission_oid.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.alter_column('ds_permission', 'id',
                    existing_type=sa.BigInteger(),
                    type_=sa.INTEGER(),
                    existing_nullable=False,
                    autoincrement=True)
    op.drop_column('ds_rules', 'oid')
    # ### Alembic 命令结束 ###
