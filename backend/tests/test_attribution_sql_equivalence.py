import re
import sqlite3

import pytest

from apps.dashboard.crud import ai_sql_generator as generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateResponse
from attribution_sql_fixture import attribution_sql
from test_dashboard_attribution_validation import config


@pytest.mark.parametrize("count_style", ["window", "inline", "grouped"])
@pytest.mark.parametrize("include_direct", [True, False])
def test_equivalent_counts_pass_and_preserve_results(count_style, include_direct):
    sql = attribution_sql(count_style=count_style, include_direct=include_direct)
    assert generator._attribution_sql_result_issues(sql, config(), sql_dialect="mysql") == []
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE events(event_id INT, actor TEXT, occurred_at TEXT, kind TEXT, channel TEXT)")
        db.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?)", [
            (1, "a", "2026-09-01 01:00:00", "email", "web"),
            (2, "a", "2026-09-01 02:00:00", "conversion", "web"),
            (3, "a", "2026-09-01 03:00:00", "search", "web"),
            (4, "a", "2026-09-01 04:00:00", "conversion", "web"),
            (5, "b", "2026-09-01 02:00:00", "conversion", "web"),
            (6, "b", "2026-09-01 03:00:00", "email", "web"),
        ])
        expected = sorted(db.execute(attribution_sql(include_direct=include_direct)).fetchall())
        assert sorted(db.execute(sql).fetchall()) == expected
        assert sum(row[2] for row in expected) == (3 if include_direct else 2)


def test_inner_join_inline_star_is_valid():
    sql = attribution_sql(count_style="inline", include_direct=False).replace("COUNT(touch_time) OVER", "COUNT(*) OVER")
    assert generator._attribution_sql_result_issues(sql, config(), sql_dialect="mysql") == []


def test_left_join_inline_star_is_rejected():
    sql = attribution_sql(count_style="inline").replace("COUNT(touch_time) OVER", "COUNT(*) OVER")
    issues = generator._attribution_sql_result_issues(sql, config(), sql_dialect="mysql")
    assert any("COUNT(*)" in issue for issue in issues)


@pytest.mark.parametrize("mutation, expected", [
    (lambda sql: sql.replace("GROUP BY target_id)", "GROUP BY target_id, attribution_event)"), "分区或分组"),
    (lambda sql: sql.replace("m.target_id = c.target_id", "1 = 1"), "关联回"),
    (lambda sql: sql.replace("COUNT(touch_time) AS hits", "5 AS hits"), "分母必须来自"),
    (lambda sql: sql.replace("COUNT(touch_time) AS hits", "COUNT(DISTINCT touch_time) AS hits"), "非空 touch_time"),
    (lambda sql: sql.replace("1.0 / NULLIF(c.hits, 0)", "target_value / NULLIF(c.hits, 0)"), "linear_weight"),
])
def test_grouped_count_does_not_weaken_validation(mutation, expected):
    sql = mutation(attribution_sql(count_style="grouped"))
    issues = generator._attribution_sql_result_issues(sql, config(), sql_dialect="mysql")
    assert any(expected in issue for issue in issues)


def test_weight_join_inherits_upstream_window():
    sql = attribution_sql(count_style="grouped").replace(
        "SELECT m.target_id, m.target_value, m.group_1,",
        "SELECT m.target_id, m.target_value, m.group_1, m.target_time, m.touch_time, m.target_date, m.touch_date,",
    )
    assert generator._attribution_sql_result_issues(sql, config(), sql_dialect="mysql") == []
    bad_sql = sql.replace("AND t.target_date = tc.touch_date", "")
    assert any("target_date = touch_date" in issue for issue in generator._attribution_sql_result_issues(bad_sql, config(), sql_dialect="mysql"))


def test_count_alias_can_be_renamed_and_passed_through():
    sql = re.sub(r"\btouch_count\b", "number_of_touches", attribution_sql())
    assert generator._attribution_sql_result_issues(sql, config(), sql_dialect="mysql") == []


def test_grouped_count_can_pass_through_another_cte():
    sql = attribution_sql(count_style="grouped").replace(
        "), weighted AS (", "), forwarded AS (SELECT target_id, hits AS n FROM counts), weighted AS (",
    ).replace("JOIN counts c", "JOIN forwarded c").replace("c.hits", "c.n")
    assert generator._attribution_sql_result_issues(sql, config(), sql_dialect="mysql") == []


def test_grouped_count_rejoins_using_target_id():
    sql = attribution_sql(count_style="grouped").replace("ON m.target_id = c.target_id", "USING (target_id)")
    assert generator._attribution_sql_result_issues(sql, config(), sql_dialect="mysql") == []


def test_weight_can_use_equivalent_numeric_literals():
    sql = attribution_sql().replace("1.0 / NULLIF(touch_count, 0)", "1.00 / NULLIF(touch_count, 0.0)")
    assert generator._attribution_sql_result_issues(sql, config(), sql_dialect="mysql") == []


def test_unused_valid_counter_does_not_mask_wrong_denominator():
    sql = attribution_sql(count_style="grouped").replace("GROUP BY target_id)", "GROUP BY target_id, attribution_event)")
    sql = sql.replace("WITH targets AS", "WITH unused_counts AS (SELECT COUNT(touch_time) OVER(PARTITION BY target_id) AS n FROM other_data), targets AS")
    assert any("分区或分组" in issue for issue in generator._attribution_sql_result_issues(sql, config(), sql_dialect="mysql"))


def test_repair_revalidates_equivalent_grouped_count():
    sql = attribution_sql(count_style="grouped").replace(
        "WHERE kind = 'conversion'",
        "WHERE kind = 'conversion' AND dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}",
    )
    invalid = sql.replace("GROUP BY target_id)", "GROUP BY target_id, attribution_event)")
    state = {"normalized_config": config(), "sql_dialect": "mysql",
             "response": DashboardAiSqlGenerateResponse(success=True, sql=invalid)}
    rejected = generator._node_validate_sql(state)
    assert not rejected["response"].success
    assert generator._route_after_sql_validate({**state, **rejected}) == "repair_sql"
    repaired = generator._node_validate_sql({**state, "sql_repair_attempts": 1,
        "response": DashboardAiSqlGenerateResponse(success=True, sql=sql)})
    assert repaired["response"].success
    assert not repaired["response"].issues
