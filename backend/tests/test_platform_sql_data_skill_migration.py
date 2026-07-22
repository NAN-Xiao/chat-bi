"""验证平台通用 SQL 日期与分组 Data Skill 的迁移契约。"""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_migration():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "146_platform_sql_grouping_data_skill.py"
    )
    spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_platform_sql_grouping_skill_is_global_and_contains_required_rules() -> None:
    migration = _load_migration()

    assert migration.SKILL_NAME == "平台通用 SQL 日期与分组规范"
    assert migration.SKILL_TARGET_SCOPE == "ALL"
    assert migration.SKILL_VISIBILITY_SCOPE == "PLATFORM_PUBLIC"
    assert "%Y-%m-%d" in migration.SKILL_PROMPT
    assert "%Y%m%d" in migration.SKILL_PROMPT
    assert "TO_CHAR" in migration.SKILL_PROMPT
    assert "按数据库方言" in migration.SKILL_PROMPT
    assert "日期展示默认使用 `DATE_FORMAT" not in migration.SKILL_PROMPT
    assert "SELECT" in migration.SKILL_PROMPT
    assert "GROUP BY" in migration.SKILL_PROMPT
    assert "完全一致" in migration.SKILL_PROMPT
