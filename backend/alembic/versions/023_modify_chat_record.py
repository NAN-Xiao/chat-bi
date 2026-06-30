"""迁移脚本：023_modify_chat_record

迁移版本 ID： f535d09946f6
上一版本： e6b20ae73606
创建时间： 2025-07-11 15:36:18.473133
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = 'f535d09946f6'
down_revision = 'e6b20ae73606'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/023_modify_chat_record.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.alter_column('chat_record', 'token_sql',
               existing_type=sa.INTEGER(),
               type_=sqlmodel.sql.sqltypes.AutoString(length=256),
               existing_nullable=True)
    op.alter_column('chat_record', 'token_chart',
               existing_type=sa.INTEGER(),
               type_=sqlmodel.sql.sqltypes.AutoString(length=256),
               existing_nullable=True)
    op.alter_column('chat_record', 'token_analysis',
               existing_type=sa.INTEGER(),
               type_=sqlmodel.sql.sqltypes.AutoString(length=256),
               existing_nullable=True)
    op.alter_column('chat_record', 'token_predict',
               existing_type=sa.INTEGER(),
               type_=sqlmodel.sql.sqltypes.AutoString(length=256),
               existing_nullable=True)
    op.alter_column('chat_record', 'token_recommended_question',
               existing_type=sa.INTEGER(),
               type_=sqlmodel.sql.sqltypes.AutoString(length=256),
               existing_nullable=True)
    op.alter_column('chat_record', 'token_select_datasource_question',
               existing_type=sa.INTEGER(),
               type_=sqlmodel.sql.sqltypes.AutoString(length=256),
               existing_nullable=True)
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/023_modify_chat_record.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.alter_column('chat_record', 'token_select_datasource_question',
               existing_type=sqlmodel.sql.sqltypes.AutoString(length=256),
               type_=sa.INTEGER(),
               existing_nullable=True)
    op.alter_column('chat_record', 'token_recommended_question',
               existing_type=sqlmodel.sql.sqltypes.AutoString(length=256),
               type_=sa.INTEGER(),
               existing_nullable=True)
    op.alter_column('chat_record', 'token_predict',
               existing_type=sqlmodel.sql.sqltypes.AutoString(length=256),
               type_=sa.INTEGER(),
               existing_nullable=True)
    op.alter_column('chat_record', 'token_analysis',
               existing_type=sqlmodel.sql.sqltypes.AutoString(length=256),
               type_=sa.INTEGER(),
               existing_nullable=True)
    op.alter_column('chat_record', 'token_chart',
               existing_type=sqlmodel.sql.sqltypes.AutoString(length=256),
               type_=sa.INTEGER(),
               existing_nullable=True)
    op.alter_column('chat_record', 'token_sql',
               existing_type=sqlmodel.sql.sqltypes.AutoString(length=256),
               type_=sa.INTEGER(),
               existing_nullable=True)
    # ### Alembic 命令结束 ###
