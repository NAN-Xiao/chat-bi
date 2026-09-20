"""Distribution denominators use the configured population, across all buckets."""
import sqlite3

import pytest

from apps.dashboard.crud import ai_sql_generator as generator


def config(group_count=2):
    return {
        "analysis_model": "distribution", "time": {}, "chart": {"type": "table"},
        "groups": [{"table": "events", "field": f"key_{i}"} for i in range(group_count)],
        "distribution": {"entityField": {"table": "events", "field": "uid"},
                         "metric": {"kind": "count"}, "interval": {"mode": "discrete"}},
    }


def window_sql(group_count=2):
    groups = "".join(f", group_{i + 1}" for i in range(group_count))
    return f"""
    WITH entity_values AS (
        SELECT distribution_date{groups}, entity_id, COUNT(*) AS distribution_value
        FROM events WHERE entity_id IS NOT NULL
        GROUP BY distribution_date{groups}, entity_id
    ), population AS (
        SELECT distribution_date{groups}, entity_id, distribution_value,
               COUNT(*) OVER (PARTITION BY distribution_date{groups}) AS total_entities
        FROM entity_values
    ), bucketed AS (
        SELECT distribution_date{groups}, entity_id, total_entities,
               distribution_value AS interval_order,
               CAST(distribution_value AS TEXT) AS interval_label
        FROM population
    )
    SELECT distribution_date{groups}, interval_order, interval_label,
           COUNT(DISTINCT entity_id) AS entity_count,
           MAX(total_entities) AS total_entities,
           ROUND(COUNT(DISTINCT entity_id) * 100.0 / NULLIF(MAX(total_entities), 0), 2) AS entity_rate
    FROM bucketed
    GROUP BY distribution_date{groups}, interval_order, interval_label
    """


@pytest.mark.parametrize("group_count", [0, 1, 2, 4])
def test_accepts_population_window_for_every_configured_group(group_count):
    assert generator._distribution_sql_result_issues(window_sql(group_count), config(group_count)) == []


@pytest.mark.parametrize("before,after", [
    ("PARTITION BY distribution_date, group_1, group_2", "PARTITION BY distribution_date, group_1"),
    ("PARTITION BY distribution_date, group_1, group_2", "PARTITION BY distribution_date, group_1, group_2, entity_id"),
    ("PARTITION BY distribution_date, group_1, group_2", "PARTITION BY distribution_date, group_1, group_2 ORDER BY entity_id"),
    ("PARTITION BY distribution_date, group_1, group_2", "PARTITION BY distribution_date, group_1, group_2 ROWS BETWEEN 1 PRECEDING AND CURRENT ROW"),
    ("GROUP BY distribution_date, group_1, group_2, entity_id", "GROUP BY distribution_date, group_1, group_2, entity_id, event_id"),
    ("FROM entity_values\n", "FROM events\n"),
    ("WHERE entity_id IS NOT NULL", "WHERE entity_id IS NOT NULL OR group_1 = 'a'"),
    ("COUNT(*) OVER", "COUNT(distribution_value) OVER"),
    ("FROM entity_values\n", "FROM entity_values CROSS JOIN events AS duplicates\n"),
    ("MAX(total_entities) AS total_entities", "1 AS total_entities"),
    ("NULLIF(MAX(total_entities), 0)", "NULLIF(COUNT(DISTINCT entity_id), 0)"),
])
def test_rejects_wrong_population_even_with_unused_compliant_cte(before, after):
    sql = window_sql().replace(before, after)
    # A textual match in an unused query must not bypass output validation.
    sql = sql.replace("WITH entity_values", "WITH decoy AS (SELECT distribution_date, "
                      "COUNT(DISTINCT entity_id) AS total_entities FROM events GROUP BY distribution_date), entity_values")
    assert generator._distribution_sql_result_issues(sql, config())


def test_explicit_full_window_frame_is_supported():
    sql = window_sql().replace("PARTITION BY distribution_date, group_1, group_2)",
                              "PARTITION BY distribution_date, group_1, group_2 ORDER BY entity_id "
                              "ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)")
    assert generator._distribution_sql_result_issues(sql, config()) == []


def test_window_population_counts_subjects_not_events_and_preserves_null_groups():
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE events (distribution_date TEXT, group_1 TEXT, group_2 TEXT, entity_id TEXT)")
        db.executemany("INSERT INTO events VALUES (?, ?, ?, ?)", [
            ("2026-09-01", "a", "x", "u1"), ("2026-09-01", "a", "x", "u1"),
            ("2026-09-01", "a", "x", "u2"), ("2026-09-01", "a", "x", "u3"),
            ("2026-09-01", "a", "y", "u1"), ("2026-09-01", "a", "y", None),
            ("2026-09-01", None, "x", "u1"), ("2026-09-01", None, "x", "u2"),
            ("2026-09-02", "a", "x", "u1"),
        ])
        rows = db.execute(window_sql()).fetchall()
    assert set(rows) == {
        ("2026-09-01", "a", "x", 1, "1", 2, 3, 66.67),
        ("2026-09-01", "a", "x", 2, "2", 1, 3, 33.33),
        ("2026-09-01", "a", "y", 1, "1", 1, 1, 100.0),
        ("2026-09-01", None, "x", 1, "1", 2, 2, 100.0),
        ("2026-09-02", "a", "x", 1, "1", 1, 1, 100.0),
    }
    assert generator._distribution_sql_result_issues(window_sql(), config()) == []
