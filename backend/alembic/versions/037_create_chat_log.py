"""迁移脚本：035_create_chat_log

迁移版本 ID： 68a06302cf70
上一版本： 29559ee607af
创建时间： 2025-08-18 16:02:43.353110
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = '68a06302cf70'
down_revision = '646e7ca28e0e'
branch_labels = None
depends_on = None


sql='''
CREATE OR REPLACE FUNCTION safe_jsonb_cast(text) RETURNS jsonb AS
$$
BEGIN
    RETURN $1::jsonb;
EXCEPTION
    WHEN others THEN
        RETURN to_json($1::text)::jsonb;
END;
$$ LANGUAGE plpgsql;

INSERT INTO chat_log(type, operate, pid, ai_modal_id, messages, start_time, finish_time, token_usage, reasoning_content)
SELECT '0',
       '0',
       id,
       ai_modal_id,
       safe_jsonb_cast(full_sql_message),
       create_time,
       finish_time,
       safe_jsonb_cast(token_sql),
       safe_jsonb_cast(sql_answer)->>'reasoning_content'
FROM chat_record
WHERE full_sql_message IS NOT NULL;
INSERT INTO chat_log(type, operate, pid, ai_modal_id, messages, start_time, finish_time, token_usage, reasoning_content)
SELECT '0',
       '1',
       id,
       ai_modal_id,
       safe_jsonb_cast(full_chart_message),
       create_time,
       finish_time,
       safe_jsonb_cast(token_chart),
       safe_jsonb_cast(chart_answer)->>'reasoning_content'
FROM chat_record
WHERE full_chart_message IS NOT NULL;
INSERT INTO chat_log(type, operate, pid, ai_modal_id, messages, start_time, finish_time, token_usage, reasoning_content)
SELECT '0',
       '2',
       id,
       ai_modal_id,
       safe_jsonb_cast(full_analysis_message),
       create_time,
       finish_time,
       safe_jsonb_cast(token_analysis),
       safe_jsonb_cast(analysis)->>'reasoning_content'
FROM chat_record
WHERE full_analysis_message IS NOT NULL;
INSERT INTO chat_log(type, operate, pid, ai_modal_id, messages, start_time, finish_time, token_usage, reasoning_content)
SELECT '0',
       '3',
       id,
       ai_modal_id,
       safe_jsonb_cast(full_predict_message),
       create_time,
       finish_time,
       safe_jsonb_cast(token_predict),
       safe_jsonb_cast(predict)->>'reasoning_content'
FROM chat_record
WHERE full_predict_message IS NOT NULL;
INSERT INTO chat_log(type, operate, pid, ai_modal_id, messages, start_time, finish_time, token_usage, reasoning_content)
SELECT '0',
       '4',
       id,
       ai_modal_id,
       safe_jsonb_cast(full_recommended_question_message),
       create_time,
       finish_time,
       safe_jsonb_cast(token_recommended_question),
       safe_jsonb_cast(recommended_question_answer)->>'reasoning_content'
FROM chat_record
WHERE full_recommended_question_message IS NOT NULL;
INSERT INTO chat_log(type, operate, pid, ai_modal_id, messages, start_time, finish_time, token_usage, reasoning_content)
SELECT '0',
       '6',
       id,
       ai_modal_id,
       safe_jsonb_cast(full_select_datasource_message),
       create_time,
       finish_time,
       safe_jsonb_cast(token_select_datasource_question),
       safe_jsonb_cast(datasource_select_answer)->>'reasoning_content'
FROM chat_record
WHERE full_select_datasource_message IS NOT NULL;

'''

def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/037_create_chat_log.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.create_table('chat_log',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('type', sa.Enum('0', name='typeenum', native_enum=False, length=3), nullable=True),
    sa.Column('operate', sa.Enum('0', '1', '2', '3', '4', '5', '6', name='operationenum', native_enum=False, length=3), nullable=True),
    sa.Column('pid', sa.BigInteger(), nullable=True),
    sa.Column('ai_modal_id', sa.BigInteger(), nullable=True),
    sa.Column('base_modal', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    sa.Column('messages', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('reasoning_content', sa.Text(), nullable=True),
    sa.Column('start_time', sa.DateTime(), nullable=True),
    sa.Column('finish_time', sa.DateTime(), nullable=True),
    sa.Column('token_usage', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )

    op.execute(sql)
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###

    """
    是什么：downgrade 是 backend/alembic/versions/037_create_chat_log.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_table('chat_log')
    # ### Alembic 命令结束 ###
