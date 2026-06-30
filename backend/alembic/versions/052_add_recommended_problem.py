"""空迁移说明

迁移版本 ID： e408f8766753
上一版本： cb12c4238120
创建时间： 2025-11-24 17:34:04.436927
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = 'e408f8766753'
down_revision = 'cb12c4238120'
branch_labels = None
depends_on = None


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/052_add_recommended_problem.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.create_table('ds_recommended_problem',
                    sa.Column('id', sa.BIGINT(),
                              sa.Identity(always=True, start=1, increment=1, minvalue=1, maxvalue=9999999999,
                                          cycle=False, cache=1), autoincrement=True, nullable=False),
                    sa.Column('datasource_id', sa.BIGINT(), autoincrement=False, nullable=True),
                    sa.Column('question', sa.TEXT(), autoincrement=False, nullable=True),
                    sa.Column('remark', sa.TEXT(), autoincrement=False, nullable=True),
                    sa.Column('sort', sa.BIGINT(), autoincrement=False, nullable=True),
                    sa.Column('create_time', postgresql.TIMESTAMP(precision=6), autoincrement=False, nullable=True),
                    sa.Column('create_by', sa.BIGINT(), autoincrement=False, nullable=True),
                    sa.PrimaryKeyConstraint('id', name=op.f('ds_recommended_problem_pkey'))
                    )
    op.add_column('core_datasource', sa.Column('recommended_config', sa.BigInteger(),default=0, nullable=True))

def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/052_add_recommended_problem.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_table('ds_recommended_problem')
    op.drop_column('core_datasource', 'recommended_config')

