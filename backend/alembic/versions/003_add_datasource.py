"""迁移脚本：003 add datasource

迁移版本 ID： d116056121c3
上一版本： 1c8bcc7e25c8
创建时间： 2025-05-06 15:13:06.058032
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# Alembic 使用的迁移版本标识。
revision = 'd116056121c3'
down_revision = '1c8bcc7e25c8'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/003_add_datasource.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.create_table('core_datasource',
    sa.Column('id', sa.Integer(), sa.Identity(always=True), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
    sa.Column('description', sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True),
    sa.Column('type', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('configuration', sa.Text(), nullable=True),
    sa.Column('create_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('create_by', sa.BigInteger(), nullable=True),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/003_add_datasource.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_table('core_datasource')
    # ### Alembic 命令结束 ###
