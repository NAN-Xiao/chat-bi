"""迁移脚本：045_modify_terminolog

迁移版本 ID： 45e7e52bf2b8
上一版本： 455b8ce69e80
创建时间： 2025-09-25 14:49:24.521795
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = '45e7e52bf2b8'
down_revision = '455b8ce69e80'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/045_modify_terminolog.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('terminology', sa.Column('specific_ds', sa.Boolean(), nullable=True))
    op.add_column('terminology', sa.Column('datasource_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/045_modify_terminolog.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_column('terminology', 'datasource_ids')
    op.drop_column('terminology', 'specific_ds')
    # ### Alembic 命令结束 ###
