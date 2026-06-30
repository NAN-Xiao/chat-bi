"""迁移脚本：011_license_ddl

迁移版本 ID： a3af70d43e98
上一版本： 8dc3b1bdbfef
创建时间： 2025-06-18 16:09:33.896600
"""
from alembic import op
import sqlalchemy as sa


# Alembic 使用的迁移版本标识。
revision = 'a3af70d43e98'
down_revision = '941e2355a94d'
branch_labels = None
depends_on = None


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/012_license_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.create_table(
        'license',
        sa.Column('id', sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column('license_key', sa.Text(), default="", nullable=False),
        sa.Column('license_payload', sa.Text(), default="", nullable=False),
        sa.Column('create_time', sa.BigInteger(), default=0, nullable=False),
        sa.Column('update_time', sa.BigInteger(), default=0, nullable=False)
    )
    op.create_index(op.f('ix_license_id'), 'license', ['id'], unique=False)


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/012_license_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_table('license')
    op.drop_index(op.f('ix_license_id'), table_name='license')
