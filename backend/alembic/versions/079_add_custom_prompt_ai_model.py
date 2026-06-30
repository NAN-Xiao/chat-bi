"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
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
    是什么：_has_table 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade():
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
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
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    if not _has_table('custom_prompt'):
        return

    if _has_column('custom_prompt', 'create_by'):
        op.drop_column('custom_prompt', 'create_by')
    if _has_column('custom_prompt', 'ai_model_id'):
        op.drop_column('custom_prompt', 'ai_model_id')
