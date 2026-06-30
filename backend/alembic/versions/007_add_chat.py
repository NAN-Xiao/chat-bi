"""迁移脚本：006_add_chat

迁移版本 ID： ff653d5df198
上一版本： 0a6f11be9be4
创建时间： 2025-05-21 15:44:29.763091
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = 'ff653d5df198'
down_revision = 'e6276ddab06e'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/007_add_chat.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.create_table('chat',
    sa.Column('id', sa.Integer(), sa.Identity(always=True), nullable=False),
    sa.Column('create_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('create_by', sa.BigInteger(), nullable=True),
    sa.Column('brief', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
    sa.Column('chat_type', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
    sa.Column('datasource', sa.Integer(), nullable=False),
    sa.Column('engine_type', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
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


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/007_add_chat.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_table('chat_record')
    op.drop_table('chat')
    # ### Alembic 命令结束 ###
