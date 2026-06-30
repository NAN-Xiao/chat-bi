"""迁移脚本：100_align_semantic_records_with_datasource_tenants

迁移版本 ID： ea20f04c9a11
上一版本： 099_system_variable_tenant_scope
创建时间： 2026-06-20 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "ea20f04c9a11"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/100_align_semantic_records_with_datasource_tenants.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/100_align_semantic_records_with_datasource_tenants.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/100_align_semantic_records_with_datasource_tenants.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if _has_table("data_training") and _has_table("core_datasource"):
        required_columns = all(
            _has_column("data_training", column)
            for column in ("tenant_id", "scope", "datasource")
        )
        if required_columns and _has_column("core_datasource", "tenant_id"):
            op.execute(
                """
                UPDATE data_training AS dt
                SET tenant_id = cd.tenant_id,
                    scope = 'TENANT'
                FROM core_datasource AS cd
                WHERE dt.datasource = cd.id
                  AND COALESCE(dt.scope, 'TENANT') = 'TENANT'
                  AND dt.tenant_id IS DISTINCT FROM cd.tenant_id
                """
            )

    if _has_table("terminology") and _has_table("core_datasource"):
        required_columns = all(
            _has_column("terminology", column)
            for column in ("tenant_id", "scope", "pid", "specific_ds", "datasource_ids")
        )
        if required_columns and _has_column("core_datasource", "tenant_id"):
            op.execute(
                """
                WITH single_ds_parent AS (
                    SELECT t.id,
                           cd.tenant_id
                    FROM terminology AS t
                    JOIN core_datasource AS cd
                      ON cd.id = (t.datasource_ids->>0)::bigint
                    WHERE t.pid IS NULL
                      AND COALESCE(t.scope, 'TENANT') = 'TENANT'
                      AND t.specific_ds = TRUE
                      AND jsonb_typeof(t.datasource_ids) = 'array'
                      AND jsonb_array_length(t.datasource_ids) = 1
                      AND t.tenant_id IS DISTINCT FROM cd.tenant_id
                )
                UPDATE terminology AS parent
                SET tenant_id = single_ds_parent.tenant_id,
                    scope = 'TENANT'
                FROM single_ds_parent
                WHERE parent.id = single_ds_parent.id
                """
            )
            op.execute(
                """
                WITH parent_scope AS (
                    SELECT id, tenant_id, scope, specific_ds, datasource_ids
                    FROM terminology
                    WHERE pid IS NULL
                      AND COALESCE(scope, 'TENANT') = 'TENANT'
                )
                UPDATE terminology AS child
                SET tenant_id = parent_scope.tenant_id,
                    scope = parent_scope.scope,
                    specific_ds = parent_scope.specific_ds,
                    datasource_ids = parent_scope.datasource_ids
                FROM parent_scope
                WHERE child.pid = parent_scope.id
                  AND (
                      child.tenant_id IS DISTINCT FROM parent_scope.tenant_id
                      OR child.scope IS DISTINCT FROM parent_scope.scope
                      OR child.specific_ds IS DISTINCT FROM parent_scope.specific_ds
                      OR child.datasource_ids IS DISTINCT FROM parent_scope.datasource_ids
                  )
                """
            )


def downgrade():
    """
    是什么：downgrade 是 backend/alembic/versions/100_align_semantic_records_with_datasource_tenants.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    pass
