"""迁移脚本：041_add_terminology_oid

迁移版本 ID： c4c3c36b720d
上一版本： 0fc14c2cfe41
创建时间： 2025-08-28 16:41:33.977242
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = 'c4c3c36b720d'
down_revision = '0fc14c2cfe41'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###

    """
    是什么：upgrade 是 backend/alembic/versions/041_add_terminology_oid.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('terminology', sa.Column('oid', sa.BigInteger(), nullable=True))

    op.execute('update terminology set oid=1 where oid is null')
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/041_add_terminology_oid.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_column('terminology', 'oid')

    # ### Alembic 命令结束 ###
