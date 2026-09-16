"""Metric grain and join-key regressions for event analysis."""
from copy import deepcopy
import sqlite3

import pytest
import sqlglot


def _contract(groups=()):
    return {
        "type": "event_table", "date_field": "day_key", "date_scaffold_required": True,
        "time": {"field": {"table": "activity", "field": "day_key"}, "grain": "day", "date_parameter_type": "yyyymmdd_number"},
        "groups": [{"field": name, "table": "activity", "alias": name} for name in groups],
        "final_grain": ["day_key", *groups],
        "metrics": [{"alias": "metric", "table": "activity", "aggregation": "count", "metric_field": None}],
    }


def _issues(sql, contract=None, dialect="mysql"):
    from apps.dashboard.crud.event_grain_validation import event_grain_issues
    return event_grain_issues(sqlglot.parse_one(sql, read=dialect), contract or _contract(), dialect)


def _daily_query(group="day_key", on="f.day_key = CAST(DATE_FORMAT(d.calendar_date, '%Y%m%d') AS SIGNED)"):
    projections = f"{group}, " if group else ""
    group_by = f"GROUP BY {group}" if group else ""
    return f"""WITH dashboard_dates AS (SELECT CAST('2024-02-28' AS DATE) AS calendar_date),
        f AS (SELECT {projections} COUNT(*) AS n FROM activity
            WHERE action_key='open' AND day_key BETWEEN :dashboard_start AND :dashboard_end {group_by})
        SELECT d.calendar_date AS day_key, COALESCE(f.n, 0) AS metric
        FROM dashboard_dates AS d LEFT JOIN f ON {on}
    """


def test_whole_range_count_cannot_be_repeated_for_each_date():
    assert _issues(_daily_query(group="", on="1=1"))


def test_daily_aggregate_requires_a_date_join_key():
    assert _issues(_daily_query(on="1=1"))
    assert _issues(_daily_query(on="f.day_key = f.day_key"))


def test_unconfigured_actor_grain_is_rejected():
    assert _issues(_daily_query(group="day_key, actor_id"))


def test_correct_daily_encoded_aggregate_passes():
    assert _issues(_daily_query()) == []


def test_missing_days_must_keep_date_from_preserved_scaffold():
    sql = _daily_query().replace("d.calendar_date AS day_key", "f.day_key AS day_key")
    assert _issues(sql)


def test_empty_buckets_must_keep_group_from_preserved_dimension_grid():
    sql = """WITH dashboard_dates AS (SELECT CAST('2024-02-28' AS DATE) AS calendar_date),
        dimensions AS (SELECT DISTINCT region FROM activity),
        f AS (SELECT day_key, region, COUNT(*) AS n FROM activity GROUP BY day_key, region)
        SELECT d.calendar_date AS day_key, f.region, COALESCE(f.n,0) AS metric
        FROM dashboard_dates d CROSS JOIN dimensions x LEFT JOIN f
        ON f.day_key=CAST(DATE_FORMAT(d.calendar_date,'%Y%m%d') AS SIGNED) AND f.region=x.region
    """
    assert _issues(sql, _contract(("region",)))
    assert _issues(sql.replace("AS day_key, f.region", "AS day_key, x.region"), _contract(("region",))) == []


@pytest.mark.parametrize("dialect,parse_date", [
    ("mysql", "STR_TO_DATE(CAST(day_key AS CHAR), '%Y%m%d')"),
    ("postgres", "TO_DATE(CAST(day_key AS TEXT), 'YYYYMMDD')"),
])
def test_date_decoding_and_cte_aliases_preserve_grain(dialect, parse_date):
    sql = f"""WITH dashboard_dates AS (SELECT CAST('2024-02-28' AS DATE) AS calendar_date),
        decoded AS (SELECT {parse_date} AS event_date FROM activity),
        aggregated AS (SELECT event_date, COUNT(*) AS n FROM decoded GROUP BY event_date),
        renamed AS (SELECT event_date AS metric_date, n FROM aggregated)
        SELECT d.calendar_date AS day_key, COALESCE(f.n,0) AS metric
        FROM dashboard_dates AS d LEFT JOIN renamed AS f ON f.metric_date=d.calendar_date
    """
    assert _issues(sql, dialect=dialect) == []


@pytest.mark.parametrize("join_keys,valid", [
    ("f.day_key=d.calendar_date", False),
    ("f.day_key=d.calendar_date AND f.region=x.region", False),
    ("f.day_key=d.calendar_date AND f.region=x.region AND f.channel=x.channel", True),
])
def test_all_configured_group_join_keys_are_required(join_keys, valid):
    join_keys = join_keys.replace("d.calendar_date", "CAST(DATE_FORMAT(d.calendar_date, '%Y%m%d') AS SIGNED)")
    sql = f"""WITH dashboard_dates AS (SELECT CAST('2024-02-28' AS DATE) AS calendar_date),
        dimensions AS (SELECT DISTINCT region, channel FROM activity),
        f AS (SELECT day_key, region, channel, COUNT(*) AS n FROM activity GROUP BY day_key, region, channel)
        SELECT d.calendar_date AS day_key, x.region, x.channel, f.n AS metric
        FROM dashboard_dates AS d CROSS JOIN dimensions AS x LEFT JOIN f ON {join_keys}
    """
    assert bool(_issues(sql, _contract(("region", "channel")))) is not valid


def test_missing_configured_group_inside_aggregate_is_rejected():
    assert _issues(_daily_query(), _contract(("region",)))


def test_metric_card_requires_no_date_group_but_rejects_extra_actor_group():
    contract = _contract()
    contract.update(date_field="", date_scaffold_required=False, final_grain=[])
    assert _issues("SELECT COUNT(*) AS metric FROM activity", contract) == []
    assert _issues("SELECT COUNT(*) AS metric FROM activity GROUP BY actor_id", contract)


def test_direct_fact_aggregate_uses_same_configured_grain():
    contract = _contract(("region",))
    contract["date_scaffold_required"] = False
    assert _issues("SELECT day_key, region, COUNT(*) AS metric FROM activity GROUP BY day_key, region", contract) == []
    assert _issues("SELECT day_key, region, COUNT(*) AS metric FROM activity GROUP BY day_key, region, actor_id", contract)


def test_count_over_raw_fact_join_also_needs_date_match():
    sql = """WITH dashboard_dates AS (SELECT CAST('2024-02-28' AS DATE) AS calendar_date)
        SELECT d.calendar_date AS day_key, COUNT(a.actor_id) AS metric
        FROM dashboard_dates AS d LEFT JOIN activity AS a ON 1=1 GROUP BY d.calendar_date"""
    assert _issues(sql)


def test_week_grain_requires_explicit_week_expression_not_raw_day():
    contract = _contract()
    contract["date_scaffold_required"] = False
    contract["time"].update(grain="week", date_parameter_type="date")
    assert _issues("SELECT DATE_TRUNC('week', day_key) AS day_key, COUNT(*) AS metric FROM activity GROUP BY DATE_TRUNC('week', day_key)", contract, "postgres") == []
    assert _issues("SELECT day_key, COUNT(*) AS metric FROM activity GROUP BY day_key", contract, "postgres")


def test_non_event_contracts_are_unchanged():
    contract = deepcopy(_contract())
    contract["type"] = "property_table"
    assert _issues(_daily_query(group="", on="1=1"), contract) == []


def test_each_raw_metric_join_is_checked_even_in_the_same_aggregate_scope():
    contract = _contract()
    contract["metrics"].append({"alias": "other_metric", "table": "other_activity", "aggregation": "count"})
    sql = """WITH dashboard_dates AS (SELECT CAST('2024-02-28' AS DATE) AS calendar_date)
        SELECT d.calendar_date AS day_key, COUNT(a.actor_id) AS metric, COUNT(b.actor_id) AS other_metric
        FROM dashboard_dates AS d
        LEFT JOIN activity AS a ON a.day_key=CAST(DATE_FORMAT(d.calendar_date,'%Y%m%d') AS SIGNED)
        LEFT JOIN other_activity AS b ON 1=1
        GROUP BY d.calendar_date"""
    assert _issues(sql, contract)


@pytest.mark.parametrize("group_by", ["1", "bucket"])
def test_group_by_ordinal_and_projection_alias_are_resolved(group_by):
    contract = _contract()
    contract.update(date_field="bucket", date_scaffold_required=False)
    sql = f"""SELECT STR_TO_DATE(CAST(day_key AS CHAR), '%Y%m%d') AS bucket, COUNT(*) AS metric
        FROM activity GROUP BY {group_by}"""
    assert _issues(sql, contract) == []


def test_timestamp_day_grain_requires_date_truncation():
    contract = _contract()
    contract["date_scaffold_required"] = False
    contract["time"]["date_parameter_type"] = "timestamp"
    assert _issues("SELECT CAST(day_key AS DATE) AS day_key, COUNT(*) AS metric FROM activity GROUP BY CAST(day_key AS DATE)", contract, "postgres") == []
    assert _issues("SELECT day_key, COUNT(*) AS metric FROM activity GROUP BY day_key", contract, "postgres")


def test_formula_only_hidden_base_metric_still_has_grain_checked():
    contract = _contract()
    metric = contract["metrics"].pop()
    contract["formula_metrics"] = [{"alias": "formula", "base_metrics": [metric]}]
    assert _issues(_daily_query(group="", on="1=1").replace("AS metric", "AS formula"), contract)


def test_real_fixture_exposes_range_total_repeated_on_every_day():
    contract = _contract()
    contract["time"]["date_parameter_type"] = "date"
    prefix = """WITH dashboard_dates AS (
        SELECT '2024-02-28' AS calendar_date UNION ALL SELECT '2024-02-29'
    ), f AS ("""
    suffix = """ SELECT d.calendar_date AS day_key, f.n AS metric
        FROM dashboard_dates AS d LEFT JOIN f ON {join} ORDER BY d.calendar_date"""
    bad = prefix + "SELECT COUNT(*) AS n FROM activity)" + suffix.format(join="1=1")
    good = prefix + "SELECT day_key, COUNT(*) AS n FROM activity GROUP BY day_key)" + suffix.format(join="f.day_key=d.calendar_date")
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE activity(day_key TEXT)")
        connection.executemany("INSERT INTO activity VALUES (?)", [("2024-02-28",), ("2024-02-28",), ("2024-02-29",)])
        assert connection.execute(bad).fetchall() == [("2024-02-28", 3), ("2024-02-29", 3)]
        assert connection.execute(good).fetchall() == [("2024-02-28", 2), ("2024-02-29", 1)]
    assert _issues(bad, contract)
    assert _issues(good, contract) == []


def test_rollup_cannot_add_an_unconfigured_total_grain():
    contract = _contract()
    contract["date_scaffold_required"] = False
    assert _issues("SELECT day_key, COUNT(*) AS metric FROM activity GROUP BY day_key WITH ROLLUP", contract)


def test_or_join_does_not_guarantee_the_required_date_key():
    assert _issues(_daily_query(on="f.day_key=CAST(DATE_FORMAT(d.calendar_date,'%Y%m%d') AS SIGNED) OR f.n > 0"))
