"""迁移脚本：047_table_embedding

迁移版本 ID： c1b794a961ce
上一版本： 8855aea2dd61
创建时间： 2025-10-09 11:32:10.578313
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = 'c1b794a961ce'
down_revision = '8855aea2dd61'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/047_table_embedding.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('core_table', sa.Column('embedding', sa.Text(), nullable=True))
    op.add_column('core_datasource', sa.Column('embedding', sa.Text(), nullable=True))
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/047_table_embedding.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_column('core_table', 'embedding')
    op.drop_column('core_datasource', 'embedding')
    # ### Alembic 命令结束 ###
