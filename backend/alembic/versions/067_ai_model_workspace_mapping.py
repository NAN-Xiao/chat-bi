"""迁移脚本：067_ai_model_workspace_mapping

迁移版本 ID： e51127e9aa4a
上一版本： 8adc3a4919be
创建时间： 2026-06-01 14:14:23.112843
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = 'e51127e9aa4a'
down_revision = '8adc3a4919be'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/067_ai_model_workspace_mapping.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.create_table('ai_model_workspace_mapping',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('ai_model_id', sa.BigInteger(), nullable=True),
    sa.Column('workspace_id', sa.BigInteger(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/067_ai_model_workspace_mapping.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_table('ai_model_workspace_mapping')
    # ### Alembic 命令结束 ###
