"""迁移脚本：108_user_account_name_unique

迁移版本 ID： f30c9a2e8b71
上一版本： c86d2f9a31b4
创建时间： 2026-06-22 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f30c9a2e8b71"
down_revision = "c86d2f9a31b4"
branch_labels = None
depends_on = None


VIRTUAL_ACCOUNTS = (
    "codex_11_member_01",
    "codex_11_member_02",
    "codex_11_member_03",
    "codex_approved_applicant",
    "codex_pending_applicant",
)


def _bind():
    """
    是什么：_bind 是 backend/alembic/versions/108_user_account_name_unique.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：更新数据库迁移相关状态、配置或持久化数据，并保持后续流程可继续使用。
    """
    return op.get_bind()


def _inspector():
    """
    是什么：_inspector 是 backend/alembic/versions/108_user_account_name_unique.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _inspector 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/108_user_account_name_unique.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是 backend/alembic/versions/108_user_account_name_unique.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _has_columns(table_name: str, column_names: tuple[str, ...]) -> bool:
    """
    是什么：_has_columns 是 backend/alembic/versions/108_user_account_name_unique.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_columns 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return all(_has_column(table_name, column_name) for column_name in column_names)


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 是 backend/alembic/versions/108_user_account_name_unique.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_index 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _delete_virtual_users() -> None:
    """
    是什么：_delete_virtual_users 是 backend/alembic/versions/108_user_account_name_unique.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：删除或清理数据库迁移相关数据、缓存或临时状态。
    """
    if not _has_columns("sys_user", ("id", "account")):
        return
    bind = _bind()
    accounts_param = sa.bindparam("accounts", expanding=True)
    user_ids = list(
        bind.execute(
            sa.text("SELECT id FROM sys_user WHERE account IN :accounts").bindparams(accounts_param),
            {"accounts": VIRTUAL_ACCOUNTS},
        ).scalars()
    )
    if not user_ids:
        return
    params = {"user_ids": [int(item) for item in user_ids]}
    ids_param = sa.bindparam("user_ids", expanding=True)

    for table_name, column_name in (
        ("core_datasource_user", "user_id"),
        ("custom_prompt_user_preference", "user_id"),
        ("sys_apikey", "uid"),
        ("sys_user_platform", "uid"),
        ("sys_tenant_user", "user_id"),
    ):
        if _has_columns(table_name, (column_name,)):
            bind.execute(
                sa.text(f"DELETE FROM {table_name} WHERE {column_name} IN :user_ids").bindparams(ids_param),
                params,
            )

    bind.execute(sa.text("DELETE FROM sys_user WHERE id IN :user_ids").bindparams(ids_param), params)


def _deduplicate_user_column(column_name: str, fallback_column: str) -> None:
    """
    是什么：_deduplicate_user_column 是 backend/alembic/versions/108_user_account_name_unique.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _deduplicate_user_column 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_columns("sys_user", ("id", column_name, fallback_column)):
        return
    _bind().execute(
        sa.text(
            f"""
            DO $$
            DECLARE
                rec RECORD;
                base_value TEXT;
                candidate TEXT;
                suffix INTEGER;
            BEGIN
                FOR rec IN
                    SELECT id, {column_name} AS duplicate_value, {fallback_column} AS fallback_value
                    FROM (
                        SELECT
                            id,
                            {column_name},
                            {fallback_column},
                            row_number() OVER (PARTITION BY {column_name} ORDER BY id) AS rn,
                            count(*) OVER (PARTITION BY {column_name}) AS duplicate_count
                        FROM sys_user
                        WHERE {column_name} IS NOT NULL AND btrim({column_name}) <> ''
                    ) AS duplicate_rows
                    WHERE duplicate_count > 1 AND rn > 1
                    ORDER BY id
                LOOP
                    base_value := left(
                        COALESCE(NULLIF(btrim(rec.fallback_value), ''), NULLIF(btrim(rec.duplicate_value), ''), 'user'),
                        240
                    );
                    candidate := base_value;
                    suffix := 1;
                    WHILE EXISTS (
                        SELECT 1 FROM sys_user WHERE {column_name} = candidate AND id <> rec.id
                    ) LOOP
                        suffix := suffix + 1;
                        candidate := left(base_value, GREATEST(1, 240 - length(suffix::text) - 1)) || '_' || suffix::text;
                    END LOOP;
                    EXECUTE format('UPDATE sys_user SET {column_name} = $1 WHERE id = $2') USING candidate, rec.id;
                END LOOP;
            END $$;
            """
        )
    )


def upgrade() -> None:
    """
    是什么：upgrade 是 backend/alembic/versions/108_user_account_name_unique.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table("sys_user"):
        return
    _delete_virtual_users()
    _deduplicate_user_column("account", "name")
    _deduplicate_user_column("name", "account")
    if _has_column("sys_user", "account") and not _has_index("sys_user", "uq_sys_user_account"):
        op.create_index("uq_sys_user_account", "sys_user", ["account"], unique=True)
    if _has_column("sys_user", "name") and not _has_index("sys_user", "uq_sys_user_name"):
        op.create_index("uq_sys_user_name", "sys_user", ["name"], unique=True)


def downgrade() -> None:
    """
    是什么：downgrade 是 backend/alembic/versions/108_user_account_name_unique.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table("sys_user"):
        return
    if _has_index("sys_user", "uq_sys_user_name"):
        op.drop_index("uq_sys_user_name", table_name="sys_user")
    if _has_index("sys_user", "uq_sys_user_account"):
        op.drop_index("uq_sys_user_account", table_name="sys_user")
