"""迁移脚本：050_modify_ddl.py

迁移版本 ID： 2785e54dc1c4
上一版本： b58a71ca6ae3
创建时间： 2025-11-06 13:43:50.820328
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = '2785e54dc1c4'
down_revision = 'b58a71ca6ae3'
branch_labels = None
depends_on = None

sql='''
UPDATE data_training SET enabled = true;
UPDATE terminology SET enabled = true;
'''

def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/050_modify_ddl_py.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('data_training', sa.Column('enabled', sa.Boolean(), nullable=True))
    op.add_column('terminology', sa.Column('enabled', sa.Boolean(), nullable=True))

    op.execute(sql)
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/050_modify_ddl_py.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_column('terminology', 'enabled')
    op.drop_column('data_training', 'enabled')
    # ### Alembic 命令结束 ###
