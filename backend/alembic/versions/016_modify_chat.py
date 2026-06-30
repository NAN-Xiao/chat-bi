"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = '031148da1d81'
down_revision = '02d84523a979'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.alter_column('chat', 'datasource',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.add_column('chat_record', sa.Column('ai_modal_id', sa.Integer(), nullable=True))
    op.add_column('chat_record', sa.Column('first_chat', sa.Boolean(), nullable=True))
    op.add_column('chat_record', sa.Column('recommended_question_answer', sa.Text(), nullable=True))
    op.add_column('chat_record', sa.Column('recommended_question', sa.Text(), nullable=True))
    op.add_column('chat_record', sa.Column('datasource_select_answer', sa.Text(), nullable=True))
    op.add_column('chat_record', sa.Column('token_sql', sa.Integer(), nullable=True))
    op.add_column('chat_record', sa.Column('token_chart', sa.Integer(), nullable=True))
    op.add_column('chat_record', sa.Column('token_analysis', sa.Integer(), nullable=True))
    op.add_column('chat_record', sa.Column('token_predict', sa.Integer(), nullable=True))
    op.add_column('chat_record', sa.Column('full_recommended_question_message', sa.Text(), nullable=True))
    op.add_column('chat_record', sa.Column('token_recommended_question', sa.Integer(), nullable=True))
    op.add_column('chat_record', sa.Column('full_select_datasource_message', sa.Text(), nullable=True))
    op.add_column('chat_record', sa.Column('token_select_datasource_question', sa.Integer(), nullable=True))
    op.alter_column('chat_record', 'chat_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('chat_record', 'datasource',
               existing_type=sa.INTEGER(),
               nullable=True)
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.alter_column('chat_record', 'datasource',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('chat_record', 'chat_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.drop_column('chat_record', 'token_select_datasource_question')
    op.drop_column('chat_record', 'full_select_datasource_message')
    op.drop_column('chat_record', 'token_recommended_question')
    op.drop_column('chat_record', 'full_recommended_question_message')
    op.drop_column('chat_record', 'token_predict')
    op.drop_column('chat_record', 'token_analysis')
    op.drop_column('chat_record', 'token_chart')
    op.drop_column('chat_record', 'token_sql')
    op.drop_column('chat_record', 'datasource_select_answer')
    op.drop_column('chat_record', 'recommended_question')
    op.drop_column('chat_record', 'recommended_question_answer')
    op.drop_column('chat_record', 'first_chat')
    op.drop_column('chat_record', 'ai_modal_id')
    op.alter_column('chat', 'datasource',
               existing_type=sa.INTEGER(),
               nullable=False)
    # ### Alembic 命令结束 ###
