"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
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
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    pass
