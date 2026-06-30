"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = '804b08ac329d'
down_revision = '1f077c30e476'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.create_table('core_dashboard',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('pid', sa.String(length=50), nullable=True),
    sa.Column('workspace_id', sa.String(length=50), nullable=True),
    sa.Column('org_id', sa.String(length=50), nullable=True),
    sa.Column('level', sa.Integer(), nullable=True),
    sa.Column('node_type', sa.String(length=255), nullable=True),
    sa.Column('type', sa.String(length=50), nullable=True),
    sa.Column('canvas_style_data', sa.Text(), nullable=True),
    sa.Column('component_data', sa.Text(), nullable=True),
    sa.Column('mobile_layout', sa.SmallInteger(), nullable=True),
    sa.Column('status', sa.Integer(), nullable=True),
    sa.Column('self_watermark_status', sa.Integer(), nullable=True),
    sa.Column('sort', sa.Integer(), nullable=True),
    sa.Column('create_time', sa.BigInteger(), nullable=True),
    sa.Column('create_by', sa.String(length=255), nullable=True),
    sa.Column('update_time', sa.BigInteger(), nullable=True),
    sa.Column('update_by', sa.String(length=255), nullable=True),
    sa.Column('remark', sa.String(length=255), nullable=True),
    sa.Column('source', sa.String(length=255), nullable=True),
    sa.Column('delete_flag', sa.SmallInteger(), nullable=True),
    sa.Column('delete_time', sa.BigInteger(), nullable=True),
    sa.Column('delete_by', sa.String(length=255), nullable=True),
    sa.Column('version', sa.Integer(), nullable=True),
    sa.Column('content_id', sa.String(length=50), nullable=True),
    sa.Column('check_version', sa.String(length=50), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    # ### Alembic 命令结束 ###


def downgrade():
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.drop_table('core_dashboard')
    # ### Alembic 命令结束 ###
