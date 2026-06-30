"""迁移脚本：046_add_custom_prompt

迁移版本 ID： 8855aea2dd61
上一版本： 45e7e52bf2b8
创建时间： 2025-09-28 13:57:01.509249
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = '8855aea2dd61'
down_revision = '45e7e52bf2b8'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/046_add_custom_prompt.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.create_table('custom_prompt',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('oid', sa.BigInteger(), nullable=True),
    sa.Column('type', sa.Enum('GENERATE_SQL', 'ANALYSIS', 'PREDICT_DATA', name='customprompttypeenum', native_enum=False, length=20), nullable=True),
    sa.Column('create_time', sa.DateTime(), nullable=True),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    sa.Column('prompt', sa.Text(), nullable=True),
    sa.Column('specific_ds', sa.Boolean(), nullable=True),
    sa.Column('datasource_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/046_add_custom_prompt.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_table('custom_prompt')
    # ### Alembic 命令结束 ###
