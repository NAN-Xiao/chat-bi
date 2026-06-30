"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
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
    是什么：_load_saas_skills_module 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移需要的数据找出来，整理成后面好用的样子。
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
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    saas_skills = _load_saas_skills_module()
    saas_skills.op = op
    saas_skills._create_saas_20_skills()


def downgrade() -> None:
    # 上一个迁移版本已经创建了不含 SQL 模板的同名 SaaS 技能。
    # 降级时保持记录启用，旧版代码仍可读取这些提示词。
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    return None
