"""迁移脚本：026_row_column_permission

迁移版本 ID： 4c6d18a18bd4
上一版本： 863105882eba
创建时间： 2025-06-25 17:32:09.183257
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
    是什么：upgrade 是 backend/alembic/versions/026_row_column_permission.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
    是什么：downgrade 是 backend/alembic/versions/026_row_column_permission.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_table('ds_rules')
    op.drop_table('ds_permission')
    # ### Alembic 命令结束 ###
