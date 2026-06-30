"""迁移脚本：096_promote_platform_admin_custom_agents

迁移版本 ID： f7a8b9c0d1e2
上一版本： e6f7a8b9c0d1
创建时间： 2026-06-19 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None

DEFAULT_TENANT_ID = 1


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/096_promote_platform_admin_custom_agents.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/096_promote_platform_admin_custom_agents.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/096_promote_platform_admin_custom_agents.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not (_has_table("custom_prompt") and _has_table("sys_user")):
        return
    required_columns = {
        "custom_prompt": ("tenant_id", "create_by", "visibility_scope", "specific_ds", "datasource_ids"),
        "sys_user": ("id", "system_role"),
    }
    for table_name, column_names in required_columns.items():
        for column_name in column_names:
            if not _has_column(table_name, column_name):
                return

    op.execute(
        sa.text(
            """
            UPDATE custom_prompt AS cp
            SET visibility_scope = 'PLATFORM_PUBLIC',
                tenant_id = :default_tenant_id,
                specific_ds = FALSE,
                datasource_ids = '[]'::jsonb
            FROM sys_user AS u
            WHERE u.id = cp.create_by
              AND u.system_role = 'system_admin'
              AND cp.visibility_scope = 'ADMIN_PUBLIC'
            """
        ).bindparams(default_tenant_id=DEFAULT_TENANT_ID)
    )


def downgrade():
    # 数据提升有意设计为不可逆：如果降级 SaaS 助手，
    # 会再次让它们从 SaaS 管理端不可见。
    """
    是什么：downgrade 是 backend/alembic/versions/096_promote_platform_admin_custom_agents.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    pass
