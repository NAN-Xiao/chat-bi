"""迁移脚本：024_modify_chat_record

迁移版本 ID： 806bc67ff45f
上一版本： f535d09946f6
创建时间： 2025-07-11 18:09:52.417628
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = '806bc67ff45f'
down_revision = 'f535d09946f6'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：upgrade 是 backend/alembic/versions/024_modify_chat_record.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('chat_record', sa.Column('analysis_record_id', sa.BigInteger(), nullable=True))
    op.add_column('chat_record', sa.Column('predict_record_id', sa.BigInteger(), nullable=True))
    op.drop_column('chat_record', 'run_time')
    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是 backend/alembic/versions/024_modify_chat_record.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('chat_record', sa.Column('run_time', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=False))
    op.drop_column('chat_record', 'predict_record_id')
    op.drop_column('chat_record', 'analysis_record_id')
    # ### Alembic 命令结束 ###
