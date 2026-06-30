"""迁移脚本：113_refresh_saas_skill_sql_examples

迁移版本 ID： e5a7c9d1f3b4
上一版本： d4f6a7b8c9e0
创建时间： 2026-06-22 00:00:00.000000
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op


revision = "e5a7c9d1f3b4"
down_revision = "d4f6a7b8c9e0"
branch_labels = None
depends_on = None


def _load_saas_skills_module():
    """
    是什么：_load_saas_skills_module 是 backend/alembic/versions/113_refresh_saas_skill_sql_examples.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询数据库迁移相关数据，整理后返回给调用方。
    """
    module_path = Path(__file__).with_name("112_expand_saas_data_skills.py")
    spec = importlib.util.spec_from_file_location("saas_skill_revision_112", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load SaaS skill revision from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.op = op
    return module


def upgrade() -> None:
    """
    是什么：upgrade 是 backend/alembic/versions/113_refresh_saas_skill_sql_examples.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    saas_skills = _load_saas_skills_module()
    saas_skills.op = op
    saas_skills._create_saas_20_skills()


def downgrade() -> None:
    # 上一个迁移版本已经创建了不含 SQL 模板的同名 SaaS 技能。
    # 降级时保持记录启用，旧版代码仍可读取这些提示词。
    """
    是什么：downgrade 是 backend/alembic/versions/113_refresh_saas_skill_sql_examples.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return None
