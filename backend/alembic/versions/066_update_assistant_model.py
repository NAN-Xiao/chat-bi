"""迁移脚本：066_update_assistant_model

迁移版本 ID： 8adc3a4919be
上一版本： 8ff90df7871d
创建时间： 2026-04-28 15:55:42.757276
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = '8adc3a4919be'
down_revision = '8ff90df7871d'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/066_update_assistant_model.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('sys_assistant', sa.Column('enable_custom_model', sa.Boolean(), nullable=True))
    op.add_column('sys_assistant', sa.Column('custom_model', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True))
    # ### Alembic 命令结束 ###


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/066_update_assistant_model.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_column('sys_assistant', 'custom_model')
    op.drop_column('sys_assistant', 'enable_custom_model')
    # ### Alembic 命令结束 ###
