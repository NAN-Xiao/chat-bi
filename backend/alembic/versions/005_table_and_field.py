"""迁移脚本：005_table_and_field

迁移版本 ID： 0a6f11be9be4
上一版本： 8fe654655905
创建时间： 2025-05-15 10:20:25.686576
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# Alembic 使用的迁移版本标识。
revision = '0a6f11be9be4'
down_revision = '8fe654655905'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/005_table_and_field.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.create_table('core_field',
    sa.Column('id', sa.Integer(), sa.Identity(always=True), nullable=False),
    sa.Column('ds_id', sa.BigInteger(), nullable=True),
    sa.Column('table_id', sa.BigInteger(), nullable=True),
    sa.Column('checked', sa.Boolean(), nullable=False),
    sa.Column('field_name', sa.Text(), nullable=True),
    sa.Column('field_type', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True),
    sa.Column('field_comment', sa.Text(), nullable=True),
    sa.Column('custom_comment', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('core_table',
    sa.Column('id', sa.Integer(), sa.Identity(always=True), nullable=False),
    sa.Column('ds_id', sa.BigInteger(), nullable=True),
    sa.Column('checked', sa.Boolean(), nullable=False),
    sa.Column('table_name', sa.Text(), nullable=True),
    sa.Column('table_comment', sa.Text(), nullable=True),
    sa.Column('custom_comment', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/005_table_and_field.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_table('core_table')
    op.drop_table('core_field')
    # ### Alembic 命令结束 ###
