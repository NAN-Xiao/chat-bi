"""迁移脚本：002_ddl_autogenerate

迁移版本 ID： 1c8bcc7e25c8
上一版本： 5348b743b05f
创建时间： 2025-04-25 17:47:18.795288
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# Alembic 使用的迁移版本标识。
revision = '1c8bcc7e25c8'
down_revision = '5348b743b05f'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/002_ddl_autogenerate.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.create_table('terms',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('term', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('definition', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('domain', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('create_time', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_terms_id'), 'terms', ['id'], unique=False)
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/002_ddl_autogenerate.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_index(op.f('ix_terms_id'), table_name='terms')
    op.drop_table('terms')
    # ### Alembic 命令结束 ###
