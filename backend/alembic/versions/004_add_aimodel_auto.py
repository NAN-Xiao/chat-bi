"""迁移脚本：004_add_aimodel_auto

迁移版本 ID： 8fe654655905
上一版本： d116056121c3
创建时间： 2025-05-07 15:51:34.768842
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = '8fe654655905'
down_revision = 'd116056121c3'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/004_add_aimodel_auto.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.create_table('ai_model',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('type', sa.Integer(), nullable=False),
    sa.Column('api_key', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    sa.Column('endpoint', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('max_context_window', sa.Integer(), nullable=False),
    sa.Column('temperature', sa.Float(), nullable=False),
    sa.Column('status', sa.Boolean(), nullable=False),
    sa.Column('description', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    sa.Column('create_time', sa.BigInteger(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_model_id'), 'ai_model', ['id'], unique=False)
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/004_add_aimodel_auto.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_index(op.f('ix_ai_model_id'), table_name='ai_model')
    op.drop_table('ai_model')
    # ### Alembic 命令结束 ###
