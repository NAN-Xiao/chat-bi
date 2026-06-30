"""迁移脚本：081_add_custom_prompt_visibility_scope

迁移版本 ID： e1f2a3b4c5d6
上一版本： d0e1f2a3b4c5
创建时间： 2026-06-17 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# Alembic 使用的迁移版本标识。
revision = 'e1f2a3b4c5d6'
down_revision = 'd0e1f2a3b4c5'
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/081_add_custom_prompt_visibility_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/081_add_custom_prompt_visibility_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/081_add_custom_prompt_visibility_scope.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table('custom_prompt'):
        return

    if not _has_column('custom_prompt', 'visibility_scope'):
        op.add_column(
            'custom_prompt',
            sa.Column('visibility_scope', sa.String(length=32), nullable=True),
        )

    op.execute(
        """
        UPDATE custom_prompt AS cp
        SET visibility_scope = CASE
            WHEN cp.create_by IS NULL THEN 'ADMIN_PUBLIC'
            WHEN EXISTS (
                SELECT 1
                FROM sys_user AS u
                WHERE u.id = cp.create_by
                  AND u.system_role IN ('system_admin', 'collab_admin')
            ) THEN 'ADMIN_PUBLIC'
            ELSE 'USER_PRIVATE'
        END
        WHERE cp.visibility_scope IS NULL
           OR cp.visibility_scope NOT IN ('ADMIN_PUBLIC', 'USER_PRIVATE')
        """
    )

    op.alter_column(
        'custom_prompt',
        'visibility_scope',
        existing_type=sa.String(length=32),
        nullable=False,
        server_default='ADMIN_PUBLIC',
    )


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/081_add_custom_prompt_visibility_scope.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if _has_table('custom_prompt') and _has_column('custom_prompt', 'visibility_scope'):
        op.drop_column('custom_prompt', 'visibility_scope')
