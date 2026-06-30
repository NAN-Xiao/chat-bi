"""迁移脚本：028_ds_oid

迁移版本 ID： e96b16d3daab
上一版本： b049c9f8ca5b
创建时间： 2025-07-17 14:40:48.522033
"""
import sqlalchemy as sa
from alembic import op

# Alembic 使用的迁移版本标识。
revision = 'e96b16d3daab'
down_revision = 'b049c9f8ca5b'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/028_ds_oid.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('core_datasource', sa.Column('oid', sa.BigInteger(), nullable=True))
    op.execute('update core_datasource set oid = 1')
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/028_ds_oid.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_column('core_datasource', 'oid')
    # ### Alembic 命令结束 ###
