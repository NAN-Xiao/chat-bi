"""Result-equivalent SQL must pass; actual missing/extra attribution rows must fail."""
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
import sqlglot
from sqlglot import exp

from apps.dashboard.crud import ai_sql_generator as generator
from apps.dashboard.crud.sql_generation_validation import derived_column_issues
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateResponse
from attribution_sql_fixture import attribution_sql
from test_dashboard_attribution_validation import config


RECORDS = [
    (1, "a", "2026-09-01 01:00:00", "email", "web"),
    (2, "a", "2026-09-01 02:00:00", "conversion", "web"),
    (3, "a", "2026-09-01 03:00:00", "conversion", "web"),
    (4, "b", "2026-09-01 02:00:00", "conversion", "web"),
    (5, "b", "2026-09-01 03:00:00", "search", "web"),
]


def execute(sql, records=RECORDS):
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE events(event_id INT, actor TEXT, occurred_at TEXT, kind TEXT, channel TEXT)")
        db.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?)", records)
        return sorted(db.execute(sql).fetchall(), key=repr)


def issues(sql):
    return generator._attribution_sql_result_issues(sql, config(), sql_dialect="mysql")


@pytest.mark.parametrize("style", ["aliases", "inline_date", "cast"])
def test_equivalent_day_expressions_execute_and_pass(style):
    baseline = attribution_sql()
    query = sqlglot.parse_one(baseline, read="mysql")
    if style == "aliases":
        for identifier in query.find_all(exp.Identifier):
            if identifier.name in {"target_date", "touch_date"}:
                identifier.set("this", identifier.name.replace("_date", "_day"))
    else:
        for condition in query.find_all(exp.EQ):
            if {column.name for column in condition.find_all(exp.Column)} == {"target_date", "touch_date"}:
                expression = "DATE(t.target_time) = DATE(tc.touch_time)" if style == "inline_date" else "CAST(t.target_time AS DATE) = CAST(tc.touch_time AS DATE)"
                condition.replace(sqlglot.parse_one(expression, read="mysql"))
    sql = query.sql(dialect="mysql")
    assert issues(sql) == []
    # SQLite CAST AS DATE is not a SQL DATE cast; DATE() and renamed aliases execute directly.
    if style != "cast":
        assert execute(sql) == execute(baseline)


@pytest.mark.parametrize("condition", [
    "DATE(t.target_time) = DATE(t.target_time)",
    "DATE(t.target_time) = DATE(tc.touch_time) OR 1 = 1",
    "DATE(t.target_time) >= DATE(tc.touch_time)",
])
def test_equivalent_day_validation_still_rejects_missing_boundary(condition):
    sql = attribution_sql().replace("t.target_date = tc.touch_date", condition)
    assert any("当天窗口" in issue for issue in issues(sql))


@pytest.mark.parametrize("rate", [
    "CASE WHEN total_touch_count = 0 THEN NULL ELSE effective_touch_count * 100.0 / total_touch_count END",
    "CASE WHEN total_touch_count > 0 THEN effective_touch_count * 100.0 / total_touch_count ELSE NULL END",
    "CASE WHEN 0 < total_touch_count THEN effective_touch_count * 100.0 / total_touch_count ELSE NULL END",
    "CASE WHEN total_touch_count <> 0 THEN effective_touch_count * 100.0 / total_touch_count ELSE NULL END",
])
def test_equivalent_zero_guards_preserve_direct_conversion_null_rate(rate):
    baseline = attribution_sql()
    sql = baseline.replace("effective_touch_count * 100.0 / NULLIF(total_touch_count, 0)", rate)
    assert execute(sql) == execute(baseline)
    assert issues(sql) == []


@pytest.mark.parametrize("rate", [
    "effective_touch_count * 100.0 / total_touch_count",
    "effective_touch_count * 100.0 / NULLIF(total_touch_count, 1)",
    "effective_touch_count * 100.0 / NULLIF(target_count, 0)",
    "effective_touch_count * 10.0 / NULLIF(total_touch_count, 0)",
    "CASE WHEN target_count = 0 THEN NULL ELSE effective_touch_count * 100.0 / total_touch_count END",
    "CASE WHEN total_touch_count = 0 THEN effective_touch_count * 100.0 / total_touch_count ELSE NULL END",
    "CASE WHEN total_touch_count = 0 THEN 0 ELSE effective_touch_count * 100.0 / total_touch_count END",
])
def test_unsafe_or_wrong_rates_are_rejected(rate):
    sql = attribution_sql().replace("effective_touch_count * 100.0 / NULLIF(total_touch_count, 0)", rate)
    assert any("有效触发率" in issue for issue in issues(sql))


def test_inner_join_target_uid_is_equivalent():
    baseline = attribution_sql(include_direct=False)
    sql = baseline.replace("SELECT t.target_id, tc.entity_id,", "SELECT t.target_id, t.entity_id,")
    assert execute(sql) == execute(baseline)
    assert issues(sql) == []


def test_rank_with_null_for_unmatched_touch_filters_target_uid_safely():
    baseline = attribution_sql(method="last", include_direct=False)
    sql = baseline.replace("SELECT t.target_id, tc.entity_id,", "SELECT t.target_id, t.entity_id,")
    sql = sql.replace("FROM targets t JOIN touches", "FROM targets t LEFT JOIN touches")
    sql = sql.replace("ROW_NUMBER() OVER (PARTITION BY t.target_id ORDER BY tc.touch_time DESC, tc.attribution_event)",
                      "CASE WHEN tc.touch_id IS NULL THEN NULL ELSE ROW_NUMBER() OVER (PARTITION BY t.target_id ORDER BY tc.touch_time DESC, tc.attribution_event) END")
    assert execute(sql) == execute(baseline)
    assert generator._attribution_sql_result_issues(sql, config("last"), sql_dialect="mysql") == []
    unsafe = sql.replace("THEN NULL ELSE ROW_NUMBER()", "THEN 1 ELSE ROW_NUMBER()")
    assert any("触点侧" in issue for issue in generator._attribution_sql_result_issues(unsafe, config("last"), sql_dialect="mysql"))


def separated_effective_counts():
    sql = attribution_sql().replace(
        "COUNT(DISTINCT entity_id) AS effective_entity_count", "COUNT(DISTINCT entity_id) AS unused_entity_count",
    ).replace(
        "), touches_total AS (",
        "), effective_entities AS (SELECT attribution_event, COUNT(DISTINCT entity_id) AS effective_entity_count "
        "FROM weighted WHERE touch_id IS NOT NULL GROUP BY attribution_event), touches_total AS (",
    ).replace("COALESCE(a.effective_entity_count, 0)", "COALESCE(e.effective_entity_count, 0)").replace(
        "ON s.attribution_event = a.attribution_event",
        "ON s.attribution_event = a.attribution_event LEFT JOIN effective_entities e ON s.attribution_event = e.attribution_event",
    ).replace("0 AS total_touch_count, effective_touch_count, effective_entity_count",
              "0 AS total_touch_count, effective_touch_count, 0 AS effective_entity_count")
    return sql


def test_left_join_target_uid_is_safe_after_filter_at_count_owner():
    baseline = separated_effective_counts()
    sql = baseline.replace("SELECT t.target_id, tc.entity_id,", "SELECT t.target_id, t.entity_id,")
    assert execute(sql) == execute(attribution_sql())
    assert issues(sql) == []


@pytest.mark.parametrize("filter_clause", ["", "WHERE target_id IS NOT NULL", "WHERE touch_id IS NOT NULL OR target_id IS NOT NULL"])
def test_unmatched_target_uid_cannot_count_as_effective_user(filter_clause):
    sql = separated_effective_counts().replace("SELECT t.target_id, tc.entity_id,", "SELECT t.target_id, t.entity_id,")
    sql = sql.replace("WHERE touch_id IS NOT NULL GROUP BY", f"{filter_clause} GROUP BY")
    assert any("触点侧" in issue for issue in issues(sql))


def test_scalar_denominator_join_does_not_remove_zero_contribution_rows():
    baseline = attribution_sql()
    sql = baseline.replace(
        ")\nSELECT attribution_event", "), total_value AS (SELECT SUM(attributed_value) AS total FROM aggregated)\nSELECT attribution_event",
    ).replace("NULLIF(SUM(attributed_value) OVER (), 0)", "NULLIF(tv.total, 0)").replace(
        "FROM complete", "FROM complete CROSS JOIN total_value tv",
    )
    assert execute(sql) == execute(baseline)
    assert issues(sql) == []


def test_scalar_subquery_in_an_empty_relation_does_not_prove_one_row():
    sql = attribution_sql().replace(
        ")\nSELECT attribution_event",
        "), missing_total AS (SELECT (SELECT SUM(attributed_value) FROM aggregated) AS total "
        "FROM aggregated WHERE 1=0)\nSELECT attribution_event",
    ).replace("FROM complete", "FROM complete CROSS JOIN missing_total")
    assert execute(sql) == []
    assert any("零贡献行" in issue for issue in issues(sql))


@pytest.mark.parametrize("join", [
    "FROM aggregated a LEFT JOIN touches_total s ON s.attribution_event = a.attribution_event",
    "FROM touches_total s JOIN aggregated a ON s.attribution_event = a.attribution_event",
    "FROM touches_total s LEFT JOIN aggregated a ON s.attribution_event = a.attribution_event WHERE a.target_count > 0",
])
def test_zero_contribution_loss_is_rejected_for_each_join_path(join):
    baseline = attribution_sql()
    sql = baseline.replace("FROM touches_total s LEFT JOIN aggregated a ON s.attribution_event = a.attribution_event", join)
    assert execute(sql) != execute(baseline)
    assert any("零贡献行" in issue for issue in issues(sql))


def test_right_join_preserving_touch_set_is_equivalent():
    baseline = attribution_sql()
    sql = baseline.replace("FROM touches_total s LEFT JOIN aggregated a", "FROM aggregated a RIGHT JOIN touches_total s")
    assert execute(sql) == execute(baseline)
    assert issues(sql) == []


def test_all_zero_contributions_are_preserved():
    records = [row for row in RECORDS if row[1] != "a"]
    rows = execute(attribution_sql(), records)
    assert next(row for row in rows if row[0] == "search")[1:3] == (0, 0)
    assert issues(attribution_sql()) == []


def test_intermediate_star_and_union_keep_metric_lineage():
    baseline = attribution_sql()
    sql = baseline.replace("), aggregated AS (", "), forwarded AS (SELECT w.* FROM weighted w), aggregated AS (")
    sql = sql.replace("FROM weighted GROUP BY", "FROM forwarded GROUP BY")
    sql = sql.replace(")\nSELECT attribution_event", "), final_rows AS (SELECT * FROM complete)\nSELECT attribution_event")
    sql = sql.replace("FROM complete\n", "FROM final_rows\n")
    assert execute(sql) == execute(baseline)
    assert issues(sql) == []


def test_first_last_case_guard_needs_no_unrelated_nullif():
    baseline = attribution_sql(method="first")
    sql = baseline.replace("effective_touch_count * 100.0 / NULLIF(total_touch_count, 0)",
                           "CASE WHEN total_touch_count=0 THEN NULL ELSE effective_touch_count*100.0/total_touch_count END")
    sql = sql.replace("attributed_value * 100.0 / NULLIF(SUM(attributed_value) OVER (), 0)",
                      "CASE WHEN SUM(attributed_value) OVER ()=0 THEN NULL ELSE attributed_value*100.0/SUM(attributed_value) OVER () END")
    assert "NULLIF" not in sql
    assert execute(sql) == execute(baseline)
    assert generator._attribution_sql_result_issues(sql, config("first"), sql_dialect="mysql") == []


@pytest.mark.parametrize("name, invalid", [("grand_total", False), ("missing_total", True)])
def test_scalar_subquery_fields_resolve_in_their_own_scope(name, invalid):
    query = sqlglot.parse_one(f"WITH totals AS (SELECT SUM(value) AS grand_total FROM facts), "
                             f"rows AS (SELECT id FROM facts) SELECT id, (SELECT {name} FROM totals) FROM rows")
    assert bool(derived_column_issues(query)) is invalid


def test_expanded_union_preserves_explicit_cte_column_aliases():
    query = sqlglot.parse_one('WITH a(x) AS (SELECT uid FROM events UNION ALL SELECT actor FROM events) SELECT x FROM a')
    assert derived_column_issues(query) == []


def test_except_cannot_claim_to_preserve_all_touch_rows():
    sql = attribution_sql().replace('UNION ALL', 'EXCEPT')
    assert any('零贡献行' in issue for issue in issues(sql))


def test_real_model_union_and_scalar_total_pass_full_generation_validation_and_execute():
    sql = (Path(__file__).parent / 'fixtures/attribution_last_scalar_total.sql').read_text(encoding='utf-8')
    state = {'normalized_config': config('last'), 'sql_dialect': 'mysql',
             'response': DashboardAiSqlGenerateResponse(success=True, sql=sql)}
    validated = generator._node_validate_sql(state)
    assert validated['response'].success, validated['response'].issues
    assert generator._route_after_sql_validate({**state, **validated}) == 'explain_advice'
    query = sql.replace('{{dashboard_start_yyyymmdd}}', '20260805').replace('{{dashboard_end_yyyymmdd}}', '20260901')
    with sqlite3.connect(':memory:') as db:
        db.row_factory = sqlite3.Row
        db.create_function('STR_TO_DATE', 2, lambda value, fmt: datetime.strptime(str(value), fmt).strftime('%Y-%m-%d'))
        db.execute('CREATE TABLE event(event_id INT, user_id TEXT, event_name TEXT, occurred_at TEXT, dt INT)')
        db.executemany('INSERT INTO event VALUES (?,?,?,?,?)', [
            (1,'a','login','2026-09-01 01:00:00',20260901),
            (2,'a','purchase','2026-09-01 02:00:00',20260901),
            (3,'a','purchase','2026-09-01 03:00:00',20260901),
            (4,'b','purchase','2026-09-01 02:00:00',20260901),
            (5,'c','login','2026-09-01 01:00:00',20260901),
            (6,'a','login','2026-09-01 02:30:00',20260901),
        ])
        rows = {row['attribution_event']: dict(row) for row in db.execute(query)}
        touch, direct = rows['login'], rows['直接转化']
        assert (touch['total_touch_count'], touch['effective_touch_count'], touch['effective_entity_count'], touch['attributed_value']) == (3, 2, 1, 2)
        assert direct['effective_entity_count'] == 0 and direct['attributed_value'] == 1
        assert direct['effective_touch_rate'] is None
        db.execute("DELETE FROM event WHERE user_id='a' AND event_name='purchase'")
        rows = {row['attribution_event']: dict(row) for row in db.execute(query)}
        assert rows['login']['attributed_value'] == 0 and rows['login']['total_touch_count'] == 3
