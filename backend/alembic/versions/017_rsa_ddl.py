"""迁移脚本：017_rsa_ddl

迁移版本 ID： a0ba8268868d
上一版本： 031148da1d81
创建时间： 2025-06-27 15:05:38.676825
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# Alembic 使用的迁移版本标识。
revision = 'a0ba8268868d'
down_revision = '031148da1d81'
branch_labels = None
depends_on = None


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/017_rsa_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.create_table(
        'rsa',
        sa.Column('id', sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column('private_key', sa.Text(), default="", nullable=False),
        sa.Column('public_key', sa.Text(), default="", nullable=False),
        sa.Column('salt', sa.Text(), default="", nullable=False),
        sa.Column('create_time', sa.BigInteger(), default=0, nullable=False),
        sa.Column('update_time', sa.BigInteger(), default=0, nullable=False)
    )
    op.create_index(op.f('ix_rsa_id'), 'rsa', ['id'], unique=False)


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/017_rsa_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_table('rsa')
    op.drop_index(op.f('ix_rsa_id'), table_name='rsa')
