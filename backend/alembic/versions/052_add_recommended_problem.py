"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
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
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
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
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.drop_table('ds_recommended_problem')
    op.drop_column('core_datasource', 'recommended_config')

