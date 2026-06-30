"""迁移脚本：106_sample_workspace_default_membership

迁移版本 ID： a75d8e3c91bf
上一版本： f64b1e9c2a75
创建时间： 2026-06-22 00:00:00.000000
"""
from __future__ import annotations

import time

from alembic import op
import sqlalchemy as sa


revision = "a75d8e3c91bf"
down_revision = "f64b1e9c2a75"
branch_labels = None
depends_on = None


SAMPLE_TENANT_CODE = "sample-workspace"
SAMPLE_TENANT_NAME = "示例工作空间"
SAMPLE_DATASOURCE_NAMES = ("SLG BI Mock",)


def _bind():
    """
    是什么：_bind 是 backend/alembic/versions/106_sample_workspace_default_membership.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：更新数据库迁移相关状态、配置或持久化数据，并保持后续流程可继续使用。
    """
    return op.get_bind()


def _inspector():
    """
    是什么：_inspector 是 backend/alembic/versions/106_sample_workspace_default_membership.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _inspector 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/106_sample_workspace_default_membership.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/106_sample_workspace_default_membership.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _has_columns(table_name: str, column_names: tuple[str, ...]) -> bool:
    """
    是什么：_has_columns 是 backend/alembic/versions/106_sample_workspace_default_membership.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_columns 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return all(_has_column(table_name, column_name) for column_name in column_names)


def _now_ms() -> int:
    """
    是什么：_now_ms 是 backend/alembic/versions/106_sample_workspace_default_membership.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _now_ms 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return int(time.time() * 1000)


def _next_id(table_name: str) -> int:
    """
    是什么：_next_id 是 backend/alembic/versions/106_sample_workspace_default_membership.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _next_id 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    value = _bind().execute(sa.text(f"SELECT COALESCE(MAX(id), 0) + 1 FROM {table_name}")).scalar()
    return int(value or 1)


def _ensure_sample_tenant() -> int | None:
    """
    是什么：_ensure_sample_tenant 是 backend/alembic/versions/106_sample_workspace_default_membership.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验数据库迁移相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    if not _has_columns("sys_tenant", ("id", "code", "name", "status", "plan", "create_time", "update_time")):
        return None

    bind = _bind()
    existing_id = bind.execute(
        sa.text("SELECT id FROM sys_tenant WHERE code = :code"),
        {"code": SAMPLE_TENANT_CODE},
    ).scalar()
    now = _now_ms()
    if existing_id is None:
        values = {
            "id": _next_id("sys_tenant"),
            "code": SAMPLE_TENANT_CODE,
            "name": SAMPLE_TENANT_NAME,
            "status": 1,
            "plan": "default",
            "create_time": now,
            "update_time": now,
        }
        optional_values = {
            "subscription_status": "active",
            "billing_mode": "manual",
        }
        for column_name, value in optional_values.items():
            if _has_column("sys_tenant", column_name):
                values[column_name] = value
        columns = ", ".join(values.keys())
        bind_names = ", ".join(f":{key}" for key in values.keys())
        bind.execute(sa.text(f"INSERT INTO sys_tenant ({columns}) VALUES ({bind_names})"), values)
        return int(values["id"])

    update_values = {"id": int(existing_id), "name": SAMPLE_TENANT_NAME, "update_time": now}
    assignments = ["name = :name", "status = 1", "plan = 'default'", "update_time = :update_time"]
    if _has_column("sys_tenant", "subscription_status"):
        assignments.append("subscription_status = 'active'")
    if _has_column("sys_tenant", "billing_mode"):
        assignments.append("billing_mode = 'manual'")
    bind.execute(
        sa.text(f"UPDATE sys_tenant SET {', '.join(assignments)} WHERE id = :id"),
        update_values,
    )
    return int(existing_id)


def _ensure_sample_memberships(sample_tenant_id: int) -> None:
    """
    是什么：_ensure_sample_memberships 是 backend/alembic/versions/106_sample_workspace_default_membership.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验数据库迁移相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    if not _has_columns("sys_tenant_user", ("id", "tenant_id", "user_id", "role", "is_primary", "status", "create_time")):
        return
    if not _has_columns("sys_user", ("id", "system_role")):
        return

    _bind().execute(
        sa.text(
            """
            WITH user_roles AS (
                SELECT
                    u.id AS user_id,
                    CASE
                        WHEN lower(COALESCE(u.system_role, '')) = 'system_admin' THEN 'owner'
                        WHEN lower(COALESCE(u.system_role, '')) = 'collab_admin' THEN 'admin'
                        ELSE 'member'
                    END AS workspace_role,
                    NOT EXISTS (
                        SELECT 1
                        FROM sys_tenant_user AS primary_membership
                        WHERE primary_membership.user_id = u.id
                          AND primary_membership.tenant_id <> :tenant_id
                          AND primary_membership.status = 1
                          AND primary_membership.is_primary = TRUE
                    ) AS should_be_primary
                FROM sys_user AS u
            ),
            next_id AS (
                SELECT COALESCE(MAX(id), 0) AS base_id FROM sys_tenant_user
            ),
            numbered AS (
                SELECT
                    next_id.base_id + row_number() OVER (ORDER BY user_roles.user_id) AS id,
                    user_roles.user_id,
                    user_roles.workspace_role,
                    user_roles.should_be_primary
                FROM user_roles, next_id
            )
            INSERT INTO sys_tenant_user (id, tenant_id, user_id, role, is_primary, status, create_time)
            SELECT id, :tenant_id, user_id, workspace_role, should_be_primary, 1, :now
            FROM numbered
            ON CONFLICT (tenant_id, user_id) DO UPDATE
            SET role = EXCLUDED.role,
                status = 1,
                is_primary = CASE
                    WHEN EXCLUDED.is_primary THEN TRUE
                    ELSE sys_tenant_user.is_primary
                END
            """
        ),
        {"tenant_id": int(sample_tenant_id), "now": _now_ms()},
    )


def _sample_datasource_ids(sample_tenant_id: int) -> list[int]:
    """
    是什么：_sample_datasource_ids 是 backend/alembic/versions/106_sample_workspace_default_membership.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _sample_datasource_ids 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_columns("core_datasource", ("id", "tenant_id", "name")):
        return []
    bind = _bind()
    names_param = sa.bindparam("names", expanding=True)
    ids = list(
        bind.execute(
            sa.text("SELECT id FROM core_datasource WHERE name IN :names").bindparams(names_param),
            {"names": SAMPLE_DATASOURCE_NAMES},
        ).scalars()
    )
    if not ids:
        return []
    bind.execute(
        sa.text(
            """
            UPDATE core_datasource
            SET tenant_id = :tenant_id
            WHERE id IN :ids
              AND tenant_id IS DISTINCT FROM :tenant_id
            """
        ).bindparams(sa.bindparam("ids", expanding=True)),
        {"tenant_id": int(sample_tenant_id), "ids": ids},
    )
    return [int(item) for item in ids]


def _jsonb_contains_any_id_clause(column_name: str) -> str:
    """
    是什么：_jsonb_contains_any_id_clause 是 backend/alembic/versions/106_sample_workspace_default_membership.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _jsonb_contains_any_id_clause 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return f"""
        {column_name} IS NOT NULL
        AND jsonb_typeof({column_name}) = 'array'
        AND EXISTS (
            SELECT 1
            FROM jsonb_array_elements_text({column_name}) AS elem(value)
            WHERE elem.value ~ '^[0-9]+$'
              AND elem.value::bigint IN :datasource_ids
        )
    """


def _align_semantic_records(sample_tenant_id: int, datasource_ids: list[int]) -> None:
    """
    是什么：_align_semantic_records 是 backend/alembic/versions/106_sample_workspace_default_membership.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _align_semantic_records 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not datasource_ids:
        return
    bind = _bind()
    ids_param = sa.bindparam("datasource_ids", expanding=True)
    params = {"tenant_id": int(sample_tenant_id), "datasource_ids": datasource_ids}

    if _has_columns("data_training", ("tenant_id", "scope", "datasource")):
        bind.execute(
            sa.text(
                """
                UPDATE data_training
                SET tenant_id = :tenant_id,
                    scope = 'TENANT'
                WHERE datasource IN :datasource_ids
                  AND COALESCE(scope, 'TENANT') = 'TENANT'
                  AND tenant_id IS DISTINCT FROM :tenant_id
                """
            ).bindparams(ids_param),
            params,
        )

    if _has_columns("terminology", ("id", "tenant_id", "scope", "pid", "specific_ds", "datasource_ids")):
        bind.execute(
            sa.text(
                f"""
                UPDATE terminology
                SET tenant_id = :tenant_id,
                    scope = 'TENANT'
                WHERE COALESCE(scope, 'TENANT') = 'TENANT'
                  AND ({_jsonb_contains_any_id_clause("datasource_ids")})
                  AND tenant_id IS DISTINCT FROM :tenant_id
                """
            ).bindparams(ids_param),
            params,
        )
        bind.execute(
            sa.text(
                """
                WITH parent_scope AS (
                    SELECT id, tenant_id, scope, specific_ds, datasource_ids
                    FROM terminology
                    WHERE pid IS NULL
                      AND tenant_id = :tenant_id
                      AND COALESCE(scope, 'TENANT') = 'TENANT'
                      AND datasource_ids IS NOT NULL
                      AND jsonb_typeof(datasource_ids) = 'array'
                      AND EXISTS (
                          SELECT 1
                          FROM jsonb_array_elements_text(datasource_ids) AS elem(value)
                          WHERE elem.value ~ '^[0-9]+$'
                            AND elem.value::bigint IN :datasource_ids
                      )
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
            ).bindparams(ids_param),
            params,
        )

    if _has_columns("custom_prompt", ("id", "tenant_id", "datasource_ids")):
        bind.execute(
            sa.text(
                f"""
                UPDATE custom_prompt
                SET tenant_id = :tenant_id
                WHERE ({_jsonb_contains_any_id_clause("datasource_ids")})
                  AND tenant_id IS DISTINCT FROM :tenant_id
                """
            ).bindparams(ids_param),
            params,
        )

    if _has_columns("custom_prompt_user_preference", ("tenant_id", "custom_prompt_id")) and _has_column(
        "custom_prompt", "id"
    ):
        bind.execute(
            sa.text(
                """
                UPDATE custom_prompt_user_preference AS pref
                SET tenant_id = :tenant_id
                FROM custom_prompt AS prompt
                WHERE pref.custom_prompt_id = prompt.id
                  AND prompt.tenant_id = :tenant_id
                  AND pref.tenant_id IS DISTINCT FROM :tenant_id
                """
            ),
            {"tenant_id": int(sample_tenant_id)},
        )

    if _has_columns("core_dashboard", ("tenant_id", "datasource")):
        bind.execute(
            sa.text(
                """
                UPDATE core_dashboard
                SET tenant_id = :tenant_id
                WHERE datasource IN :datasource_ids
                  AND tenant_id IS DISTINCT FROM :tenant_id
                """
            ).bindparams(ids_param),
            params,
        )


def upgrade() -> None:
    """
    是什么：upgrade 是 backend/alembic/versions/106_sample_workspace_default_membership.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    sample_tenant_id = _ensure_sample_tenant()
    if sample_tenant_id is None:
        return
    _ensure_sample_memberships(sample_tenant_id)
    datasource_ids = _sample_datasource_ids(sample_tenant_id)
    _align_semantic_records(sample_tenant_id, datasource_ids)


def downgrade() -> None:
    """
    是什么：downgrade 是 backend/alembic/versions/106_sample_workspace_default_membership.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    pass
