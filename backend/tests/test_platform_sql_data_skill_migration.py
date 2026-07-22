"""验证平台通用 SQL 日期与分组 Data Skill 的迁移契约。"""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_migration(filename: str = "146_platform_sql_grouping_data_skill.py"):
    module_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / filename
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


def test_followup_migration_refreshes_existing_platform_skill() -> None:
    original = _load_migration()
    followup = _load_migration("147_refresh_platform_sql_grouping_data_skill.py")

    assert followup.down_revision == original.revision
    assert followup.SKILL_MARKER == original.SKILL_MARKER
    assert followup.SKILL_PROMPT == original.SKILL_PROMPT

    class _Result:
        rowcount = 1

    class _Bind:
        dialect = type("Dialect", (), {"name": "postgresql"})()

        def __init__(self) -> None:
            self.executions = []

        def execute(self, statement, params):
            self.executions.append((str(statement), params))
            return _Result()

    bind = _Bind()
    followup._bind = lambda: bind

    followup.upgrade()

    assert len(bind.executions) == 1
    statement, params = bind.executions[0]
    assert "UPDATE custom_prompt" in statement
    assert "embedding = NULL" in statement
    assert "embedding_signature = NULL" in statement
    assert params["marker"] == original.SKILL_MARKER
    assert params["prompt"] == original.SKILL_PROMPT.strip()
