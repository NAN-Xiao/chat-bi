"""迁移脚本：080_add_custom_prompt_activation_scope

迁移版本 ID： d0e1f2a3b4c5
上一版本： c9d0e1f2a3b4
创建时间： 2026-06-17 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# Alembic 使用的迁移版本标识。
revision = 'd0e1f2a3b4c5'
down_revision = 'c9d0e1f2a3b4'
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/080_add_custom_prompt_activation_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/080_add_custom_prompt_activation_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/080_add_custom_prompt_activation_scope.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if _has_table('custom_prompt'):
        if not _has_column('custom_prompt', 'target_scope'):
            op.add_column(
                'custom_prompt',
                sa.Column('target_scope', sa.String(length=32), nullable=True),
            )
            op.execute("UPDATE custom_prompt SET target_scope = 'SMART_QA' WHERE target_scope IS NULL")
            op.alter_column(
                'custom_prompt',
                'target_scope',
                existing_type=sa.String(length=32),
                nullable=False,
                server_default='SMART_QA',
            )

        if not _has_column('custom_prompt', 'active'):
            op.add_column(
                'custom_prompt',
                sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.false()),
            )
            op.execute("UPDATE custom_prompt SET active = false WHERE active IS NULL")

    if _has_table('chat_record') and not _has_column('chat_record', 'custom_prompt_id'):
        op.add_column('chat_record', sa.Column('custom_prompt_id', sa.BigInteger(), nullable=True))


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/080_add_custom_prompt_activation_scope.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if _has_table('chat_record') and _has_column('chat_record', 'custom_prompt_id'):
        op.drop_column('chat_record', 'custom_prompt_id')

    if _has_table('custom_prompt'):
        if _has_column('custom_prompt', 'active'):
            op.drop_column('custom_prompt', 'active')
        if _has_column('custom_prompt', 'target_scope'):
            op.drop_column('custom_prompt', 'target_scope')
