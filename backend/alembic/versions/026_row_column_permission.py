"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = '4c6d18a18bd4'
down_revision = '97dcdbedaaf3'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.create_table('ds_permission',
                    sa.Column('id', sa.Integer(), sa.Identity(always=True), nullable=False),
                    sa.Column('enable', sa.Boolean(), nullable=False),
                    sa.Column('auth_target_type', sa.String(128), nullable=False),
                    sa.Column('auth_target_id', sa.BigInteger(), nullable=True),
                    sa.Column('type', sa.String(64), nullable=False),
                    sa.Column('ds_id', sa.BigInteger(), nullable=True),
                    sa.Column('table_id', sa.BigInteger(), nullable=True),
                    sa.Column('expression_tree', sa.Text(), nullable=True),
                    sa.Column('permissions', sa.Text(), nullable=True),
                    sa.Column('white_list_user', sa.Text(), nullable=True),
                    sa.Column('create_time', sa.DateTime(), nullable=True),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_table('ds_rules',
                    sa.Column('id', sa.Integer(), sa.Identity(always=True), nullable=False),
                    sa.Column('enable', sa.Boolean(), nullable=False),
                    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
                    sa.Column('description', sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True),
                    sa.Column('permission_list', sa.Text(), nullable=True),
                    sa.Column('user_list', sa.Text(), nullable=True),
                    sa.Column('white_list_user', sa.Text(), nullable=True),
                    sa.Column('create_time', sa.DateTime(), nullable=True),
                    sa.PrimaryKeyConstraint('id')
                    )
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.drop_table('ds_rules')
    op.drop_table('ds_permission')
    # ### Alembic 命令结束 ###
