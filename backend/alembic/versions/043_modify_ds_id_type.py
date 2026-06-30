"""迁移脚本：043_modify_ds_id_type

迁移版本 ID： dac062c1f7b1
上一版本： a487d9c69341
创建时间： 2025-09-22 17:20:44.465735
"""
import sqlalchemy as sa
from alembic import op

# Alembic 使用的迁移版本标识。
revision = 'dac062c1f7b1'
down_revision = 'a487d9c69341'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/043_modify_ds_id_type.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.alter_column('core_datasource', 'id',
                    existing_type=sa.INTEGER(),
                    type_=sa.BigInteger(),
                    existing_nullable=False,
                    autoincrement=True)
    op.alter_column('core_field', 'id',
                    existing_type=sa.INTEGER(),
                    type_=sa.BigInteger(),
                    existing_nullable=False,
                    autoincrement=True)
    op.alter_column('core_table', 'id',
                    existing_type=sa.INTEGER(),
                    type_=sa.BigInteger(),
                    existing_nullable=False,
                    autoincrement=True)
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/043_modify_ds_id_type.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.alter_column('core_table', 'id',
                    existing_type=sa.BigInteger(),
                    type_=sa.INTEGER(),
                    existing_nullable=False,
                    autoincrement=True)
    op.alter_column('core_field', 'id',
                    existing_type=sa.BigInteger(),
                    type_=sa.INTEGER(),
                    existing_nullable=False,
                    autoincrement=True)
    op.alter_column('core_datasource', 'id',
                    existing_type=sa.BigInteger(),
                    type_=sa.INTEGER(),
                    existing_nullable=False,
                    autoincrement=True)
    # ### Alembic 命令结束 ###
