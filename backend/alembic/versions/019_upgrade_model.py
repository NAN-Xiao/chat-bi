"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = 'dcaecd481715'
down_revision = '863105882eba'
branch_labels = None
depends_on = None


def upgrade():
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.drop_index(op.f('ix_ai_model_id'), table_name='ai_model')
    op.drop_table('ai_model')
    # ### Alembic 自动生成的命令，请按需调整！###
    op.create_table('ai_model',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('api_key', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    sa.Column('api_domain', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('protocol', sa.Integer(), nullable=False),
    sa.Column('supplier', sa.Integer(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('model_type', sa.Integer(), nullable=False),
    sa.Column('base_model', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('default_model', sa.Boolean(), nullable=False),
    sa.Column('config', sa.Text(), nullable=False),
    sa.Column('status', sa.Integer(), nullable=False),
    sa.Column('create_time', sa.BigInteger(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_model_id'), 'ai_model', ['id'], unique=False)
    # ### Alembic 命令结束 ###

def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.drop_index(op.f('ix_ai_model_id'), table_name='ai_model')
    op.drop_table('ai_model')

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
