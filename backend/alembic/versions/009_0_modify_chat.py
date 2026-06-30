"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = '1f077c30e476'
down_revision = '35d925df4568'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.drop_table('chat_record')
    op.create_table('chat_record',
    sa.Column('id', sa.Integer(), sa.Identity(always=True), nullable=False),
    sa.Column('chat_id', sa.Integer(), nullable=True),
    sa.Column('create_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finish_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('create_by', sa.BigInteger(), nullable=True),
    sa.Column('datasource', sa.Integer(), nullable=False),
    sa.Column('engine_type', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('question', sa.Text(), nullable=True),
    sa.Column('sql_answer', sa.Text(), nullable=True),
    sa.Column('sql', sa.Text(), nullable=True),
    sa.Column('sql_exec_result', sa.Text(), nullable=True),
    sa.Column('data', sa.Text(), nullable=True),
    sa.Column('chart_answer', sa.Text(), nullable=True),
    sa.Column('chart', sa.Text(), nullable=True),
    sa.Column('full_sql_message', sa.Text(), nullable=True),
    sa.Column('full_chart_message', sa.Text(), nullable=True),
    sa.Column('finish', sa.Boolean(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('run_time', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.drop_table('chat_record')
    op.create_table('chat_record',
    sa.Column('id', sa.Integer(), sa.Identity(always=True), nullable=False),
    sa.Column('chat_id', sa.Integer(), nullable=True),
    sa.Column('create_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('create_by', sa.BigInteger(), nullable=True),
    sa.Column('datasource', sa.Integer(), nullable=False),
    sa.Column('engine_type', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('question', sa.Text(), nullable=True),
    sa.Column('full_question', sa.Text(), nullable=True),
    sa.Column('answer', sa.Text(), nullable=True),
    sa.Column('run_time', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id')
                    )
    # ### Alembic 命令结束 ###
