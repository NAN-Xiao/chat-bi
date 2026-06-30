"""迁移脚本：131_normalize_platform_generic_prompts

迁移版本 ID： d4f7a9c2e1b3
上一版本： c7e9a2d4f6b8
创建时间： 2026-06-27 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "d4f7a9c2e1b3"
down_revision = "c7e9a2d4f6b8"
branch_labels = None
depends_on = None


def _bind():
    """
    是什么：_bind 是 backend/alembic/versions/131_normalize_platform_generic_prompts.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：更新数据库迁移相关状态、配置或持久化数据，并保持后续流程可继续使用。
    """
    return op.get_bind()


def _inspector():
    """
    是什么：_inspector 是 backend/alembic/versions/131_normalize_platform_generic_prompts.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _inspector 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是 backend/alembic/versions/131_normalize_platform_generic_prompts.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in _inspector().get_table_names()


def _has_columns(table_name: str, column_names: tuple[str, ...]) -> bool:
    """
    是什么：_has_columns 是 backend/alembic/versions/131_normalize_platform_generic_prompts.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_columns 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_table(table_name):
        return False
    existing = {column["name"] for column in _inspector().get_columns(table_name)}
    return set(column_names).issubset(existing)


def upgrade() -> None:
    """
    是什么：upgrade 是 backend/alembic/versions/131_normalize_platform_generic_prompts.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    if not _has_columns(
        "custom_prompt",
        ("tenant_id", "visibility_scope", "specific_ds", "datasource_ids"),
    ):
        return

    empty_datasource_ids = "'[]'::jsonb" if _bind().dialect.name == "postgresql" else "'[]'"
    op.execute(
        f"""
        UPDATE custom_prompt
        SET tenant_id = 1,
            specific_ds = false,
            datasource_ids = {empty_datasource_ids}
        WHERE visibility_scope = 'PLATFORM_PUBLIC'
        """
    )


def downgrade() -> None:
    """
    是什么：downgrade 是 backend/alembic/versions/131_normalize_platform_generic_prompts.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    pass
