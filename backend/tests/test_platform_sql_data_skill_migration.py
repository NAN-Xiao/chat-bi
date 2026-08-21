"""验证平台通用 SQL 日期与分组 Data Skill 的迁移契约。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

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


def test_default_date_window_followup_supports_offline_sql(monkeypatch) -> None:
    migration = _load_migration("151_platform_default_date_window_data_skill.py")
    statements = []
    monkeypatch.setattr(
        migration.op,
        "get_context",
        lambda: type("Context", (), {"as_sql": True})(),
    )
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.upgrade()

    assert len(statements) == 1
    assert "POSTCOMPILE_date_section" in str(statements[0])


def test_platform_date_skill_rules_do_not_exempt_date_bound_metrics() -> None:
    root = Path(__file__).resolve().parents[2]
    files = [
        root / "tools" / "repair_data_skill_scope_conflicts.py",
        root / "backend" / "alembic" / "versions" / "146_platform_sql_grouping_data_skill.py",
        root / "backend" / "alembic" / "versions" / "147_refresh_platform_sql_grouping_data_skill.py",
        root / "backend" / "alembic" / "versions" / "151_platform_default_date_window_data_skill.py",
    ]
    old_rule = "固定语义指标卡（例如明确限定“今日”或“本月”的单值指标）保持其自身语义，不将看板日期范围强加到该指标。"
    new_rule = "指标卡只要查询或过滤日期字段，就必须使用成对看板日期 token 和完整 `date_filter`"

    for path in files:
        content = path.read_text(encoding="utf-8")
        assert old_rule not in content, path
        assert new_rule in content, path


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


def test_metric_date_contract_migration_replaces_existing_platform_skill_rule() -> None:
    migration = _load_migration("163_platform_metric_date_contract.py")

    assert migration.down_revision == "162platformmysqlunsignedruntime"
    assert "指标卡只要查询或过滤日期字段" in migration.NEW_RULE
    assert "固定日期字面量" in migration.NEW_RULE

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
    assert "embedding = NULL" in statement
    assert params["old_rule"] == migration.OLD_RULE
    assert params["new_rule"] == migration.NEW_RULE

    migration.downgrade()
    assert len(bind.executions) == 2
    _statement, downgrade_params = bind.executions[1]
    assert downgrade_params["old_rule"] == migration.NEW_RULE
    assert downgrade_params["new_rule"] == migration.OLD_RULE


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


def test_alias_quoting_followup_supports_offline_sql(monkeypatch) -> None:
    migration = _load_migration("152_platform_sql_alias_quoting_data_skill.py")
    statements = []
    monkeypatch.setattr(
        migration.op,
        "get_context",
        lambda: type("Context", (), {"as_sql": True})(),
    )
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.upgrade()

    assert len(statements) == 1
    assert "POSTCOMPILE_alias_section" in str(statements[0])


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


def test_hourly_zero_fill_followup_uses_generic_dimension_rule() -> None:
    migration = _load_migration("154_platform_hourly_zero_fill_data_skill.py")

    assert migration.down_revision == "153platformdailyzerofill"
    assert "platform-foundation-skill:hourly-zero-fill:v1" in migration.ZERO_FILL_SECTION
    assert migration.ZERO_FILL_VALIDATION_RULES[1]["when_sql_has_non_time_group_by"] is True
    assert migration.ZERO_FILL_VALIDATION_RULES[3]["when_sql_has_non_time_group_by"] is True
    assert migration.ZERO_FILL_VALIDATION_RULES[1]["required_outer_select_cross_join"] is True
    assert migration.ZERO_FILL_VALIDATION_RULES[3]["required_outer_select_cross_join"] is True
    assert "时间字段之外的任意分组维度" in migration.ZERO_FILL_SECTION
    assert "当天 `00:00` 到该最大事件时间所在小时" in migration.ZERO_FILL_SECTION
    assert "对当前数据源 Schema 配置的事实 `time` 字段取 `MAX`" in migration.ZERO_FILL_SECTION
    assert "不得使用 `CURRENT_DATE`" in migration.ZERO_FILL_SECTION


def test_mysql_unsigned_compatibility_followup_updates_platform_skill(monkeypatch: pytest.MonkeyPatch) -> None:
    migration = _load_migration("155_platform_mysql_unsigned_compatibility_data_skill.py")

    assert migration.down_revision == "154platformhourlyzerofill"
    assert "platform-foundation-skill:mysql-unsigned-compat:v1" in migration.ZERO_FILL_SECTION
    assert "CAST(... AS UNSIGNED)" in migration.ZERO_FILL_SECTION
    assert "SIGNED" in migration.ZERO_FILL_SECTION
    assert "DECIMAL" in migration.ZERO_FILL_SECTION
    assert "JSON 数值字段" in migration.ZERO_FILL_SECTION

    class _Result:
        rowcount = 1

    class _Bind:
        def __init__(self) -> None:
            self.executions = []

        def execute(self, statement, params):
            self.executions.append((str(statement), params))
            return _Result()

    bind = _Bind()
    monkeypatch.setattr(migration.op, "get_bind", lambda: bind)

    migration.upgrade()

    assert len(bind.executions) == 1
    statement, params = bind.executions[0]
    assert "UPDATE custom_prompt" in statement
    assert "embedding = NULL" in statement
    assert "embedding_signature = NULL" in statement
    assert "unsigned_marker" in params
    assert params["section"] == migration.ZERO_FILL_SECTION


def test_recursive_cte_week_compatibility_followup_updates_platform_skill(monkeypatch: pytest.MonkeyPatch) -> None:
    migration = _load_migration("156_platform_recursive_cte_week_interval_data_skill.py")

    assert migration.down_revision == "155platformmysqlunsignedcompat"
    assert "platform-foundation-skill:recursive-cte-week-compat:v1" in migration.SECTION
    assert "每个 CTE 都必须写完整列清单" in migration.SECTION
    assert "INTERVAL <列或表达式> WEEK" in migration.SECTION
    assert "INTERVAL (week_offset * 7) DAY" in migration.SECTION
    assert migration.VALIDATION_RULES[0]["forbidden_sql_patterns"]

    assert llm._data_skill_sql_validation_violation(
        "最近8周趋势",
        "SELECT DATE_SUB(dt, INTERVAL 1 WEEK) AS week_start FROM events",
        migration.SECTION,
    ) is None

    class _Result:
        rowcount = 1

    class _Bind:
        def __init__(self) -> None:
            self.executions = []

        def execute(self, statement, params):
            self.executions.append((str(statement), params))
            return _Result()

    bind = _Bind()
    monkeypatch.setattr(migration.op, "get_bind", lambda: bind)
    migration.upgrade()


def test_mysql_unsigned_runtime_capability_followup_removes_global_ban(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration("162_platform_mysql_unsigned_runtime_capability.py")

    assert migration.down_revision == "161platformskilltenantexclusion"
    assert "mysql-unsigned-compat:v1" in migration.OLD_SECTION_MARKER
    assert "mysql-unsigned-runtime-capability:v2" in migration.NEW_SECTION_MARKER
    assert "不支持 `CAST(... AS UNSIGNED)`" in migration.OLD_GUIDANCE
    assert "支持 `CAST(... AS SIGNED)` 和 `CAST(... AS UNSIGNED)`" in migration.NEW_GUIDANCE
    assert "不得在执行前全局禁止" in migration.NEW_GUIDANCE
    assert "实际执行错误明确拒绝" in migration.NEW_GUIDANCE

    class _Result:
        rowcount = 1

    class _Bind:
        def __init__(self) -> None:
            self.executions = []

        def execute(self, statement, params):
            self.executions.append((str(statement), params))
            return _Result()

    bind = _Bind()
    monkeypatch.setattr(migration.op, "get_bind", lambda: bind)

    migration.upgrade()

    assert len(bind.executions) == 1
    statement, params = bind.executions[0]
    assert "UPDATE custom_prompt" in statement
    assert "embedding = NULL" in statement
    assert "embedding_signature = NULL" in statement
    assert params["old_marker"] == migration.OLD_SECTION_MARKER
    assert params["new_marker"] == migration.NEW_SECTION_MARKER
    assert params["old_guidance"] == migration.OLD_GUIDANCE
    assert params["new_guidance"] == migration.NEW_GUIDANCE

    migration.downgrade()

    assert len(bind.executions) == 2
    _statement, downgrade_params = bind.executions[1]
    assert downgrade_params["old_marker"] == migration.NEW_SECTION_MARKER
    assert downgrade_params["new_marker"] == migration.OLD_SECTION_MARKER
    assert downgrade_params["old_guidance"] == migration.NEW_GUIDANCE
    assert downgrade_params["new_guidance"] == migration.OLD_GUIDANCE


def test_time_scaffold_performance_followup_updates_platform_skill(monkeypatch: pytest.MonkeyPatch) -> None:
    migration = _load_migration("157_platform_time_scaffold_performance_data_skill.py")

    assert migration.down_revision == "156platformrecursivecteweek"
    assert "platform-foundation-skill:time-scaffold-performance:v1" in migration.SECTION
    assert "事实明细表必须先" in migration.SECTION
    assert "不得把物理事实表直接按日期、小时或周范围 JOIN 到时间骨架" in migration.SECTION

    class _Result:
        rowcount = 1

    class _Bind:
        def __init__(self) -> None:
            self.executions = []

        def execute(self, statement, params):
            self.executions.append((str(statement), params))
            return _Result()

    bind = _Bind()
    monkeypatch.setattr(migration.op, "get_bind", lambda: bind)
    migration.upgrade()

    assert len(bind.executions) == 1
    statement, params = bind.executions[0]
    assert "UPDATE custom_prompt" in statement
    assert params["section_marker"] == migration.SECTION_MARKER

    assert len(bind.executions) == 1
    statement, params = bind.executions[0]
    assert "UPDATE custom_prompt" in statement
    assert params["section"] == migration.SECTION


def test_date_function_commas_do_not_trigger_dimension_scaffold_rule() -> None:
    migration = _load_migration("154_platform_hourly_zero_fill_data_skill.py")
    sql = """
        WITH calendar AS (
            SELECT DATE_ADD(
                STR_TO_DATE(CAST({{dashboard_start_yyyymmdd}} AS CHAR), '%Y%m%d'),
                INTERVAL n DAY
            ) AS dt
            FROM params CROSS JOIN numbers
        ), metrics AS (
            SELECT DATE_FORMAT(e.dt, '%Y-%m-%d') AS dt, COUNT(*) AS value
            FROM event e
            GROUP BY DATE_FORMAT(e.dt, '%Y-%m-%d')
        )
        SELECT c.dt, COALESCE(m.value, 0) AS value
        FROM calendar c
        LEFT JOIN metrics m ON m.dt = c.dt
        WHERE c.dt <= STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d')
    """

    assert (
        llm._data_skill_sql_validation_violation(
            "最近14天每日新增用户趋势",
            sql,
            migration.ZERO_FILL_SECTION,
        )
        is None
    )


def test_any_non_time_dimension_requires_date_dimension_scaffold() -> None:
    migration = _load_migration("154_platform_hourly_zero_fill_data_skill.py")
    sql = """
        WITH calendar AS (
            SELECT DATE_ADD(
                STR_TO_DATE(CAST({{dashboard_start_yyyymmdd}} AS CHAR), '%Y%m%d'),
                INTERVAL n DAY
            ) AS dt
            FROM numbers
        ), metrics AS (
            SELECT e.dt, e.region_code, COUNT(*) AS value
            FROM event e
            GROUP BY e.dt, e.region_code
        )
        SELECT c.dt, m.region_code, COALESCE(m.value, 0) AS value
        FROM calendar c
        LEFT JOIN metrics m ON m.dt = c.dt
        WHERE c.dt <= STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d')
    """

    violation = llm._data_skill_sql_validation_violation(
        "最近14天每日各地区新增用户趋势",
        sql,
        migration.ZERO_FILL_SECTION,
    )

    assert violation is not None
    assert "时间之外的分组维度" in violation.message


def test_realtime_hourly_zero_fill_requires_continuous_hour_series() -> None:
    migration = _load_migration("154_platform_hourly_zero_fill_data_skill.py")
    incomplete_sql = """
        SELECT DATE_FORMAT(FROM_UNIXTIME(e.time / 1000), '%H:00') AS hour_label,
               COUNT(*) AS value
        FROM event_realtime e
        GROUP BY DATE_FORMAT(FROM_UNIXTIME(e.time / 1000), '%H:00')
    """
    complete_sql = """
        WITH hour_offsets AS (
            SELECT 0 AS hour_offset UNION ALL SELECT 1 UNION ALL SELECT 2
        ), max_event_time AS (
            SELECT MAX(e.time) AS max_time
            FROM event_realtime e
            WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
        ), hour_series AS (
            SELECT h.hour_offset AS hour_index
            FROM hour_offsets h CROSS JOIN max_event_time x
            WHERE h.hour_offset <= HOUR(FROM_UNIXTIME(x.max_time / 1000))
        ), hourly_metrics AS (
            SELECT e.dt,
                   HOUR(FROM_UNIXTIME(e.time / 1000)) AS hour_index,
                   COUNT(*) AS value
            FROM event_realtime e
            WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
            GROUP BY e.dt, HOUR(FROM_UNIXTIME(e.time / 1000))
        )
        SELECT h.hour_index, COALESCE(m.value, 0) AS value
        FROM hour_series h
        LEFT JOIN hourly_metrics m ON m.hour_index = h.hour_index
    """

    assert (
        llm._data_skill_sql_validation_violation(
            "今天实时每小时新增用户趋势",
            incomplete_sql,
            migration.ZERO_FILL_SECTION,
        )
        is not None
    )
    assert (
        llm._data_skill_sql_validation_violation(
            "今天实时每小时新增用户趋势",
            complete_sql,
            migration.ZERO_FILL_SECTION,
        )
        is None
    )
    current_clock_sql = complete_sql.replace(
        "MAX(e.time) AS max_time",
        "CURRENT_TIMESTAMP AS max_time",
    )
    assert (
        llm._data_skill_sql_validation_violation(
            "今天实时每小时新增用户趋势",
            current_clock_sql,
            migration.ZERO_FILL_SECTION,
        )
        is not None
    )
    assert (
        llm._data_skill_sql_validation_violation(
            "实时新增用户总数",
            "SELECT COUNT(*) FROM event_realtime",
            migration.ZERO_FILL_SECTION,
        )
        is None
    )
    assert (
        llm._data_skill_sql_validation_violation(
            "实时累计新增用户趋势",
            incomplete_sql,
            migration.ZERO_FILL_SECTION,
        )
        is not None
    )


def test_realtime_hourly_non_time_dimension_requires_cross_join() -> None:
    migration = _load_migration("154_platform_hourly_zero_fill_data_skill.py")
    sql = """
        WITH max_event_time AS (
            SELECT MAX(e.time) AS max_time
            FROM event_realtime e
            WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
        ), hour_series AS (
            SELECT h.hour_offset AS hour_index
            FROM hour_offsets h CROSS JOIN max_event_time x
            WHERE h.hour_offset <= HOUR(FROM_UNIXTIME(x.max_time / 1000))
        ), hourly_metrics AS (
            SELECT HOUR(FROM_UNIXTIME(e.time / 1000)) AS hour_index,
                   e.region_code,
                   COUNT(*) AS value
            FROM event_realtime e
            WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
            GROUP BY HOUR(FROM_UNIXTIME(e.time / 1000)), e.region_code
        )
        SELECT h.hour_index, m.region_code, COALESCE(m.value, 0) AS value
        FROM hour_series h
        LEFT JOIN hourly_metrics m ON m.hour_index = h.hour_index
    """

    violation = llm._data_skill_sql_validation_violation(
        "今天每小时各地区新增用户趋势",
        sql,
        migration.ZERO_FILL_SECTION,
    )

    assert violation is not None
    assert "时间之外的分组维度" in violation.message


def test_realtime_hourly_scope_followup_separates_freshness_from_hour_grain() -> None:
    migration = _load_migration("158_platform_realtime_hourly_intent_scope.py")
    hourly_migration = _load_migration("155_platform_mysql_unsigned_compatibility_data_skill.py")
    updated_skill = hourly_migration.ZERO_FILL_SECTION.replace(
        migration.OLD_HOURLY_MATCH,
        migration.NEW_HOURLY_MATCH,
    ).replace(
        migration.OLD_HOURLY_GUIDANCE,
        migration.NEW_HOURLY_GUIDANCE,
    )
    dimension_sql = """
        SELECT channel, COUNT(*) AS value
        FROM event_realtime
        GROUP BY channel
    """
    incomplete_hourly_sql = """
        SELECT HOUR(event_time) AS hour_index, COUNT(*) AS value
        FROM event_realtime
        GROUP BY HOUR(event_time)
    """

    assert migration.down_revision == "157platformtimescaffoldperf"
    assert "\"实时\"" not in migration.NEW_HOURLY_MATCH
    assert "\"实时趋势\"" in migration.NEW_HOURLY_MATCH
    assert (
        llm._data_skill_sql_validation_violation(
            "按渠道统计实时订单",
            dimension_sql,
            updated_skill,
        )
        is None
    )
    assert (
        llm._data_skill_sql_validation_violation(
            "实时订单按小时趋势",
            incomplete_hourly_sql,
            updated_skill,
        )
        is not None
    )


def test_realtime_sql_shape_followup_rejects_database_clock_and_recursive_hours() -> None:
    migration = _load_migration("159_platform_realtime_sql_shape.py")

    assert migration.down_revision == "158platformrealtimehourlyscope"
    assert "platform-foundation-skill:realtime-sql-shape:v1" in migration.SECTION
    assert (
        llm._data_skill_sql_validation_violation(
            "今天实时付费金额",
            "SELECT SUM(amount) FROM event_realtime WHERE dt = YEAR(UTC_TIMESTAMP())",
            migration.SECTION,
        )
        is not None
    )
    assert (
        llm._data_skill_sql_validation_violation(
            "实时付费按小时趋势",
            "WITH RECURSIVE hours(h) AS (SELECT 0 UNION ALL SELECT h + 1 FROM hours) SELECT h FROM hours JOIN event_realtime e ON 1=1",
            migration.SECTION,
        )
        is not None
    )


def test_historical_hourly_followup_separates_complete_days_from_current_day() -> None:
    migration = _load_migration("164_platform_historical_hourly_zero_fill.py")
    historical_complete_sql = """
        WITH hour_series AS (
            SELECT 0 AS hour_offset UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3
            UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7
            UNION ALL SELECT 8 UNION ALL SELECT 9 UNION ALL SELECT 10 UNION ALL SELECT 11
            UNION ALL SELECT 12 UNION ALL SELECT 13 UNION ALL SELECT 14 UNION ALL SELECT 15
            UNION ALL SELECT 16 UNION ALL SELECT 17 UNION ALL SELECT 18 UNION ALL SELECT 19
            UNION ALL SELECT 20 UNION ALL SELECT 21 UNION ALL SELECT 22 UNION ALL SELECT 23
        ), hourly_data AS (
            SELECT HOUR(FROM_UNIXTIME(e.time / 1000)) AS hour_offset,
                   SUM(e.amount) AS amount
            FROM event e
            WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
            GROUP BY HOUR(FROM_UNIXTIME(e.time / 1000))
        )
        SELECT h.hour_offset, COALESCE(d.amount, 0) AS amount
        FROM hour_series h
        LEFT JOIN hourly_data d ON d.hour_offset = h.hour_offset
    """
    historical_clipped_sql = historical_complete_sql.replace(
        "WITH hour_series AS (",
        "WITH max_hour AS (SELECT MAX(time) AS max_hour_offset FROM event WHERE dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}), hour_series AS (",
    ).replace(
        "LEFT JOIN hourly_data d ON d.hour_offset = h.hour_offset",
        "CROSS JOIN max_hour m LEFT JOIN hourly_data d ON d.hour_offset = h.hour_offset WHERE h.hour_offset <= m.max_hour_offset",
    )
    current_day_sql = historical_clipped_sql

    assert migration.down_revision == "163platformmetricdatecontract"
    assert "历史完整日按小时结果" in migration.ZERO_FILL_SECTION
    assert "禁止全表取最大时间" in migration.ZERO_FILL_SECTION
    assert (
        llm._data_skill_sql_validation_violation(
            "按小时统计八月19日的充值金额",
            historical_complete_sql,
            migration.ZERO_FILL_SECTION,
        )
        is None
    )
    violation = llm._data_skill_sql_validation_violation(
        "按小时统计八月19日的充值金额",
        historical_clipped_sql,
        migration.ZERO_FILL_SECTION,
    )
    assert violation is not None
    assert "历史按小时" in violation.message
    assert (
        llm._data_skill_sql_validation_violation(
            "今天实时按小时统计充值金额",
            current_day_sql,
            migration.ZERO_FILL_SECTION,
        )
        is None
    )


def test_historical_hourly_followup_requires_full_day_scaffold_even_without_facts() -> None:
    migration = _load_migration("164_platform_historical_hourly_zero_fill.py")
    incomplete_sql = """
        WITH hour_series AS (SELECT 0 AS hour_offset UNION ALL SELECT 9),
        hourly_data AS (
            SELECT HOUR(FROM_UNIXTIME(e.time / 1000)) AS hour_offset, COUNT(*) AS value
            FROM event e
            WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
            GROUP BY HOUR(FROM_UNIXTIME(e.time / 1000))
        )
        SELECT h.hour_offset, COALESCE(d.value, 0) AS value
        FROM hour_series h LEFT JOIN hourly_data d ON d.hour_offset = h.hour_offset
    """

    violation = llm._data_skill_sql_validation_violation(
        "2026年8月19日每小时订单数",
        incomplete_sql,
        migration.ZERO_FILL_SECTION,
    )

    assert violation is not None
    assert "complete hour sequence 0-23" in violation.missing_required_patterns
    total_violation = llm._data_skill_sql_validation_violation(
        "2026年8月19日每小时充值总额",
        incomplete_sql,
        migration.ZERO_FILL_SECTION,
    )
    assert total_violation is not None
    assert "complete hour sequence 0-23" in total_violation.missing_required_patterns


def test_current_day_hourly_followup_rejects_unscoped_max_time() -> None:
    migration = _load_migration("164_platform_historical_hourly_zero_fill.py")
    unscoped_sql = """
        WITH max_hour AS (SELECT MAX(e.time) AS max_time FROM event_realtime e),
        hour_series AS (SELECT 0 AS hour_offset UNION ALL SELECT 1),
        hourly_data AS (
            SELECT HOUR(FROM_UNIXTIME(e.time / 1000)) AS hour_offset, COUNT(*) AS value
            FROM event_realtime e
            WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
            GROUP BY HOUR(FROM_UNIXTIME(e.time / 1000))
        )
        SELECT h.hour_offset, COALESCE(d.value, 0) AS value
        FROM hour_series h CROSS JOIN max_hour m
        LEFT JOIN hourly_data d ON d.hour_offset = h.hour_offset
        WHERE h.hour_offset <= HOUR(FROM_UNIXTIME(m.max_time / 1000))
    """

    violation = llm._data_skill_sql_validation_violation(
        "今天实时按小时统计订单数",
        unscoped_sql,
        migration.ZERO_FILL_SECTION,
    )

    assert violation is not None
    assert "MAX(time) scoped by dashboard date range" in violation.missing_required_patterns


def test_current_day_hourly_followup_accepts_scoped_qualified_max_time() -> None:
    migration = _load_migration("164_platform_historical_hourly_zero_fill.py")
    scoped_sql = """
        WITH max_hour AS (
            SELECT MAX(e.time) AS max_time
            FROM event_realtime e
            WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
        ), hour_series AS (SELECT 0 AS hour_offset UNION ALL SELECT 1),
        hourly_data AS (
            SELECT HOUR(FROM_UNIXTIME(e.time / 1000)) AS hour_offset, COUNT(*) AS value
            FROM event_realtime e
            WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
            GROUP BY HOUR(FROM_UNIXTIME(e.time / 1000))
        )
        SELECT h.hour_offset, COALESCE(d.value, 0) AS value
        FROM hour_series h CROSS JOIN max_hour m
        LEFT JOIN hourly_data d ON d.hour_offset = h.hour_offset
        WHERE h.hour_offset <= HOUR(FROM_UNIXTIME(m.max_time / 1000))
    """

    assert (
        llm._data_skill_sql_validation_violation(
            "今天实时按小时统计订单数",
            scoped_sql,
            migration.ZERO_FILL_SECTION,
        )
        is None
    )


def test_historical_hourly_followup_replaces_only_zero_fill_section() -> None:
    migration = _load_migration("164_platform_historical_hourly_zero_fill.py")
    original = (
        "prefix\n"
        + migration.SECTION_START_MARKER
        + "\nold zero fill\n\n"
        + migration.SECTION_END_MARKER
        + "\nsuffix"
    )

    updated = migration.replace_zero_fill_section(original, migration.ZERO_FILL_SECTION)

    assert updated.startswith("prefix\n" + migration.ZERO_FILL_SECTION)
    assert updated.endswith(migration.SECTION_END_MARKER + "\nsuffix")
    assert "old zero fill" not in updated
