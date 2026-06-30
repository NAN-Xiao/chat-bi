"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa


revision = "fb31c2d4e5a6"
down_revision = "ea20f04c9a11"
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


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    table_name = "ds_rules"
    if not _has_table(table_name):
        return

    if not _has_column(table_name, "tenant_id"):
        op.add_column(
            table_name,
            sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default=str(DEFAULT_TENANT_ID)),
        )
    if not _has_column(table_name, "scope"):
        op.add_column(
            table_name,
            sa.Column("scope", sa.String(length=32), nullable=False, server_default="TENANT"),
        )

    if _has_table("ds_permission") and _has_table("core_datasource") and _has_column("core_datasource", "tenant_id"):
        op.execute(
            """
            WITH rule_datasource_tenant AS (
                SELECT r.id AS rule_id,
                       MIN(cd.tenant_id) AS tenant_id
                FROM ds_rules AS r
                JOIN ds_permission AS p
                  ON p.id = ANY(
                      SELECT jsonb_array_elements_text(COALESCE(NULLIF(r.permission_list, '')::jsonb, '[]'::jsonb))::bigint
                  )
                JOIN core_datasource AS cd
                  ON cd.id = p.ds_id
                GROUP BY r.id
            )
            UPDATE ds_rules AS r
            SET tenant_id = rule_datasource_tenant.tenant_id,
                scope = 'TENANT'
            FROM rule_datasource_tenant
            WHERE r.id = rule_datasource_tenant.rule_id
              AND rule_datasource_tenant.tenant_id IS NOT NULL
            """
        )

    op.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET tenant_id = :tenant_id
            WHERE tenant_id IS NULL
            """
        ).bindparams(tenant_id=DEFAULT_TENANT_ID)
    )
    op.execute(
        f"""
        UPDATE {table_name}
        SET scope = 'TENANT'
        WHERE scope IS NULL OR scope NOT IN ('TENANT', 'PLATFORM')
        """
    )

    if not _has_index(table_name, "idx_ds_rules_tenant_id"):
        op.create_index("idx_ds_rules_tenant_id", table_name, ["tenant_id"])
    if not _has_index(table_name, "idx_ds_rules_scope"):
        op.create_index("idx_ds_rules_scope", table_name, ["scope"])


def downgrade():
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    table_name = "ds_rules"
    if not _has_table(table_name):
        return
    if _has_index(table_name, "idx_ds_rules_scope"):
        op.drop_index("idx_ds_rules_scope", table_name=table_name)
    if _has_index(table_name, "idx_ds_rules_tenant_id"):
        op.drop_index("idx_ds_rules_tenant_id", table_name=table_name)
    if _has_column(table_name, "scope"):
        op.drop_column(table_name, "scope")
    if _has_column(table_name, "tenant_id"):
        op.drop_column(table_name, "tenant_id")
