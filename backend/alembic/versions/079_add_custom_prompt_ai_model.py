"""迁移脚本：079_add_custom_prompt_model_owner

迁移版本 ID： c9d0e1f2a3b4
上一版本： b8c9d0e1f2a3
创建时间： 2026-06-17 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# Alembic 使用的迁移版本标识。
revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/079_add_custom_prompt_ai_model.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/079_add_custom_prompt_ai_model.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/079_add_custom_prompt_ai_model.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table('custom_prompt'):
        return

    if not _has_column('custom_prompt', 'ai_model_id'):
        op.add_column('custom_prompt', sa.Column('ai_model_id', sa.BigInteger(), nullable=True))

    if not _has_column('custom_prompt', 'create_by'):
        op.add_column('custom_prompt', sa.Column('create_by', sa.BigInteger(), nullable=True))
        op.execute(
            """
            UPDATE custom_prompt
            SET create_by = (
                SELECT id
                FROM sys_user
                ORDER BY
                    CASE WHEN system_role = 'system_admin' THEN 0 ELSE 1 END,
                    create_time,
                    id
                LIMIT 1
            )
            WHERE create_by IS NULL
            """
        )


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/079_add_custom_prompt_ai_model.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table('custom_prompt'):
        return

    if _has_column('custom_prompt', 'create_by'):
        op.drop_column('custom_prompt', 'create_by')
    if _has_column('custom_prompt', 'ai_model_id'):
        op.drop_column('custom_prompt', 'ai_model_id')
