"""迁移脚本：032_modify_assistant_ddl

迁移版本 ID： 6549e47f9adc
上一版本： bd2ed188b5bd
创建时间： 2025-07-22 12:23:16.646665
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# Alembic 使用的迁移版本标识。
revision = '6549e47f9adc'
down_revision = 'bd2ed188b5bd'
branch_labels = None
depends_on = None


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/032_modify_assistant_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('sys_assistant', sa.Column('description', sa.Text(), nullable=True))


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/032_modify_assistant_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_column('sys_assistant', 'description')
