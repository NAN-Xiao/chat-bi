"""验证平台通用 SQL 日期与分组 Data Skill 的迁移契约。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from apps.chat.task import llm


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


def test_platform_sql_grouping_skill_includes_default_date_window_and_dashboard_tokens() -> None:
    migration = _load_migration("147_refresh_platform_sql_grouping_data_skill.py")

    assert "用户未指定日期范围时，默认使用过去 7 个完整自然日。" in migration.SKILL_PROMPT
    assert "{{dashboard_start_yyyymmdd}}" in migration.SKILL_PROMPT
    assert "{{dashboard_end_yyyymmdd}}" in migration.SKILL_PROMPT


def test_default_date_window_followup_migration_keeps_dashboard_template_tokens() -> None:
    migration = _load_migration("151_platform_default_date_window_data_skill.py")

    assert migration.down_revision == "150dashboarddatefilteraudit"
    assert "用户未指定日期范围时，默认使用过去 7 个完整自然日。" in migration.DATE_SECTION
    assert "{{dashboard_start_yyyymmdd}}" in migration.DATE_SECTION
    assert "{{dashboard_end_yyyymmdd}}" in migration.DATE_SECTION


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


def test_alias_quoting_followup_migration_contains_dialect_and_scope_rules() -> None:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "152_platform_sql_alias_quoting_data_skill.py"
    )
    assert module_path.exists(), "缺少平台 SQL 中文别名引用刷新迁移"
    migration = _load_migration("152_platform_sql_alias_quoting_data_skill.py")

    assert migration.down_revision == "151platformdefaultdate"
    assert "platform-foundation-skill:sql-alias-quoting:v1" in migration.ALIAS_SECTION
    assert "MySQL、AnalyticDB、Doris 和 StarRocks" in migration.ALIAS_SECTION
    assert "AS `注册日期`" in migration.ALIAS_SECTION
    assert "单引号表示字符串值" in migration.ALIAS_SECTION
    assert "ORDER BY `注册日期`, `地区`" in migration.ALIAS_SECTION
    assert "同一查询块" in migration.ALIAS_SECTION
    assert "上游 CTE 或子查询" in migration.ALIAS_SECTION


def test_alias_quoting_followup_migration_appends_section_idempotently() -> None:
    migration = _load_migration("152_platform_sql_alias_quoting_data_skill.py")

    class _Result:
        rowcount = 1

    class _Bind:
        def __init__(self) -> None:
            self.executions = []

        def execute(self, statement, params):
            self.executions.append((str(statement), params))
            return _Result()

    bind = _Bind()
    migration.op.get_bind = lambda: bind

    migration.upgrade()

    assert len(bind.executions) == 1
    statement, params = bind.executions[0]
    assert "UPDATE custom_prompt" in statement
    assert "position(:alias_marker" in statement
    assert "embedding = NULL" in statement
    assert params["alias_marker"] == migration.ALIAS_SECTION_MARKER
    assert params["alias_section"] == migration.ALIAS_SECTION
    assert params["skill_marker"] == migration.SKILL_MARKER


def test_daily_zero_fill_followup_contains_enforceable_platform_rule() -> None:
    migration = _load_migration("153_platform_daily_zero_fill_data_skill.py")

    assert migration.down_revision == "152platformsqlaliasquote"
    assert "platform-foundation-skill:daily-zero-fill:v1" in migration.ZERO_FILL_SECTION
    assert "dashboard_start_yyyymmdd" in migration.ZERO_FILL_SECTION
    assert "dashboard_end_yyyymmdd" in migration.ZERO_FILL_SECTION
    assert "CROSS JOIN" in migration.ZERO_FILL_SECTION
    assert "LEFT JOIN" in migration.ZERO_FILL_SECTION
    assert "COALESCE(指标, 0)" in migration.ZERO_FILL_SECTION
    assert migration.ZERO_FILL_VALIDATION_RULES[1]["when_sql_patterns"] == [r"\bgroup\s+by\b[^;]*,"]


def test_daily_zero_fill_platform_rule_rejects_fact_only_grouping_sql() -> None:
    migration = _load_migration("153_platform_daily_zero_fill_data_skill.py")
    sql = """
        SELECT e.dt AS `日期`,
               COALESCE(NULLIF(e.channel, ''), '未知') AS `渠道`,
               COUNT(DISTINCT e.uid) AS `新增用户数`
        FROM event e
        WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
        GROUP BY e.dt, COALESCE(NULLIF(e.channel, ''), '未知')
    """

    violation = llm._data_skill_sql_validation_violation(
        "最近14天各投放渠道每日新增用户趋势如何？",
        sql,
        migration.ZERO_FILL_SECTION,
    )

    assert violation is not None
    assert "连续日期序列" in violation.message


def test_daily_zero_fill_platform_rule_requires_date_dimension_scaffold() -> None:
    migration = _load_migration("153_platform_daily_zero_fill_data_skill.py")
    sql_without_dimension_scaffold = """
        WITH calendar AS (
            SELECT DATE_ADD(
                STR_TO_DATE(CAST({{dashboard_start_yyyymmdd}} AS CHAR), '%Y%m%d'),
                INTERVAL day_offset DAY
            ) AS dt
            FROM day_offsets
        ), metrics AS (
            SELECT dt, channel, COUNT(DISTINCT uid) AS value
            FROM event
            GROUP BY dt, channel
        )
        SELECT c.dt, COALESCE(m.value, 0) AS value
        FROM calendar c
        LEFT JOIN metrics m ON m.dt = c.dt
        WHERE c.dt <= STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d')
    """

    violation = llm._data_skill_sql_validation_violation(
        "最近14天各投放渠道每日新增用户趋势如何？",
        sql_without_dimension_scaffold,
        migration.ZERO_FILL_SECTION,
    )

    assert violation is not None
    assert "CROSS JOIN" in violation.message


def test_daily_zero_fill_platform_rule_accepts_complete_scaffold() -> None:
    migration = _load_migration("153_platform_daily_zero_fill_data_skill.py")
    sql = """
        WITH calendar AS (
            SELECT DATE_ADD(
                STR_TO_DATE(CAST({{dashboard_start_yyyymmdd}} AS CHAR), '%Y%m%d'),
                INTERVAL day_offset DAY
            ) AS dt
            FROM day_offsets
        ), dimensions AS (
            SELECT DISTINCT channel FROM event
        ), metrics AS (
            SELECT dt, channel, COUNT(DISTINCT uid) AS value
            FROM event
            GROUP BY dt, channel
        )
        SELECT c.dt, d.channel, COALESCE(m.value, 0) AS value
        FROM calendar c
        CROSS JOIN dimensions d
        LEFT JOIN metrics m ON m.dt = c.dt AND m.channel = d.channel
        WHERE c.dt <= STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d')
    """

    assert (
        llm._data_skill_sql_validation_violation(
            "最近14天各投放渠道每日新增用户趋势如何？",
            sql,
            migration.ZERO_FILL_SECTION,
        )
        is None
    )
    assert (
        llm._data_skill_sql_validation_violation(
            "最近14天各投放渠道每日新增用户趋势如何？",
            sql.replace("COALESCE(m.value, 0)", 'COALESCE(m."value", 0)'),
            migration.ZERO_FILL_SECTION,
        )
        is None
    )
    assert (
        llm._data_skill_sql_validation_violation(
            "最近14天各渠道累计新增用户数",
            "SELECT channel, COUNT(*) FROM event GROUP BY channel",
            migration.ZERO_FILL_SECTION,
        )
        is None
    )
