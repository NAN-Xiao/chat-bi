"""迁移脚本：038_remove_chat_record_cloumns

迁移版本 ID： fc23c4f3e755
上一版本： 68a06302cf70
创建时间： 2025-08-21 14:34:59.149410
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = 'fc23c4f3e755'
down_revision = '68a06302cf70'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/038_remove_chat_record_cloumns.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_column('chat_record', 'token_predict')
    op.drop_column('chat_record', 'token_select_datasource_question')
    op.drop_column('chat_record', 'token_sql')
    op.drop_column('chat_record', 'full_analysis_message')
    op.drop_column('chat_record', 'full_recommended_question_message')
    op.drop_column('chat_record', 'token_chart')
    op.drop_column('chat_record', 'full_predict_message')
    op.drop_column('chat_record', 'full_chart_message')
    op.drop_column('chat_record', 'full_sql_message')
    op.drop_column('chat_record', 'full_select_datasource_message')
    op.drop_column('chat_record', 'token_recommended_question')
    op.drop_column('chat_record', 'token_analysis')
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/038_remove_chat_record_cloumns.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('chat_record', sa.Column('token_analysis', sa.VARCHAR(length=256), autoincrement=False, nullable=True))
    op.add_column('chat_record', sa.Column('token_recommended_question', sa.VARCHAR(length=256), autoincrement=False, nullable=True))
    op.add_column('chat_record', sa.Column('full_select_datasource_message', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('chat_record', sa.Column('full_sql_message', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('chat_record', sa.Column('full_chart_message', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('chat_record', sa.Column('full_predict_message', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('chat_record', sa.Column('token_chart', sa.VARCHAR(length=256), autoincrement=False, nullable=True))
    op.add_column('chat_record', sa.Column('full_recommended_question_message', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('chat_record', sa.Column('full_analysis_message', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('chat_record', sa.Column('token_sql', sa.VARCHAR(length=256), autoincrement=False, nullable=True))
    op.add_column('chat_record', sa.Column('token_select_datasource_question', sa.VARCHAR(length=256), autoincrement=False, nullable=True))
    op.add_column('chat_record', sa.Column('token_predict', sa.VARCHAR(length=256), autoincrement=False, nullable=True))
    # ### Alembic 命令结束 ###
