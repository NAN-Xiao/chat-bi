"""迁移脚本：027_modify_permission

迁移版本 ID： b049c9f8ca5b
上一版本： 4c6d18a18bd4
创建时间： 2025-07-16 09:59:23.345135
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = 'b049c9f8ca5b'
down_revision = '4c6d18a18bd4'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/027_modify_permission.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('ds_permission', sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True))
    op.alter_column('ds_permission', 'auth_target_type',
               existing_type=sa.VARCHAR(length=128),
               nullable=True)
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/027_modify_permission.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.alter_column('ds_permission', 'auth_target_type',
               existing_type=sa.VARCHAR(length=128),
               nullable=False)
    op.drop_column('ds_permission', 'name')
    # ### Alembic 命令结束 ###
