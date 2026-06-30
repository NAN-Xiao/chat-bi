"""迁移脚本：016_modify_chat

迁移版本 ID： 031148da1d81
上一版本： 02d84523a979
创建时间： 2025-06-26 17:00:07.054531
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
    是什么：upgrade 是 backend/alembic/versions/016_modify_chat.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
    是什么：downgrade 是 backend/alembic/versions/016_modify_chat.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
