"""Execute the generated date spine against local fixtures, without a datasource."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

import pytest
import sqlglot
from sqlglot import exp

from apps.dashboard.crud.sql_generation_rules import (
    build_date_scaffold,
    date_scaffold_issues as _scaffold_issues,
    generation_sql_rules,
)


def _render(sql: str, parameter_type: str, start: str, end: str) -> str:
    if parameter_type == "date":
        return sql.replace("{{dashboard_start_date}}", repr(start)).replace(
            "{{dashboard_end_date}}", repr(end)
        )
    values = [value.replace("-", "") for value in (start, end)]
    if parameter_type == "yyyymmdd_text":
        values = [repr(value) for value in values]
    return sql.replace("{{dashboard_start_yyyymmdd}}", values[0]).replace(
        "{{dashboard_end_yyyymmdd}}", values[1]
    )


def _sqlite_sql(sql: str, dialect: str) -> str:
    """Adapt date operations missing from sqlglot's SQLite transpiler.

    The date generator's joins, UNIONs, predicates, and arithmetic on integer
    offsets remain intact. DATE +/- INTEGER and dynamic MySQL INTERVAL use
    SQLite's documented date modifiers; DATE - DATE uses JULIANDAY.
    """
    tree = sqlglot.parse_one(sql, read=dialect)
    assert not tree.args["with_"].args.get("recursive")
    assert tree.find(exp.Limit) is None
    if dialect == "postgres":
        def typed_dates(node: exp.Expression) -> exp.Expression:
            if isinstance(node, exp.Sub) and isinstance(node.this, exp.Column):
                if node.this.name == "end_date" and node.expression.name == "start_date":
                    return exp.DateDiff(this=node.this.copy(), expression=node.expression.copy(), unit=exp.Var(this="DAY"))
            if isinstance(node, exp.Add) and isinstance(node.this, exp.Column):
                if node.this.name == "start_date":
                    return exp.DateAdd(this=node.this.copy(), expression=node.expression.copy(), unit=exp.Var(this="DAY"))
            return node
        tree = tree.transform(typed_dates)
    def sqlite_dates(node: exp.Expression) -> exp.Expression:
        if isinstance(node, exp.DateAdd):
            return exp.Anonymous(this="DATE", expressions=[
                node.this.copy(),
                exp.DPipe(this=node.expression.copy(), expression=exp.Literal.string(" DAY")),
            ])
        if isinstance(node, exp.DateDiff):
            return exp.Cast(this=exp.Sub(
                this=exp.Anonymous(this="JULIANDAY", expressions=[node.this.copy()]),
                expression=exp.Anonymous(this="JULIANDAY", expressions=[node.expression.copy()]),
            ), to=exp.DataType.build("INT"))
        return node
    return tree.transform(sqlite_dates).sql(dialect="sqlite")


def _execute(sql: str, dialect: str) -> list[tuple]:
    with sqlite3.connect(":memory:") as connection:
        connection.create_function(
            "STR_TO_DATE", 2,
            lambda value, fmt: datetime.strptime(str(value), fmt).date().isoformat(),
        )
        return connection.execute(_sqlite_sql(sql, dialect)).fetchall()


@pytest.mark.parametrize("dialect", ["mysql", "postgres"])
@pytest.mark.parametrize("parameter_type", ["yyyymmdd_number", "yyyymmdd_text", "date"])
@pytest.mark.parametrize("start,end,count", [
    ("2026-09-01", "2026-09-07", 7),
    ("2026-08-20", "2026-09-16", 28),
    ("2023-12-20", "2024-02-02", 45),
    ("2024-02-27", "2024-03-02", 5),
    ("2023-12-31", "2025-02-02", 400),
    ("2024-01-01", "2024-12-31", 366),
    ("2026-09-16", "2026-09-16", 1),
])
def test_spine_returns_every_date_once(dialect, parameter_type, start, end, count):
    scaffold = build_date_scaffold(
        {"grain": "day", "date_parameter_type": parameter_type}, dialect
    )
    assert scaffold["supported"]
    sql = _render(scaffold["select_sql"], parameter_type, start, end)
    rows = _execute(sql, dialect)
    expected = [(date.fromisoformat(start) + timedelta(days=index)).isoformat() for index in range(count)]
    assert [row[0] for row in rows] == expected


@pytest.mark.parametrize("dialect", ["mysql", "postgres"])
@pytest.mark.parametrize("parameter_type,key_type", [("yyyymmdd_number", int), ("yyyymmdd_text", str)])
def test_spine_key_preserves_encoded_filter_type(dialect, parameter_type, key_type):
    scaffold = build_date_scaffold({"grain": "day", "dateParameterType": parameter_type}, dialect)
    sql = f"WITH {scaffold['cte_sql']} SELECT {scaffold['key_expression']} FROM {scaffold['cte_name']} ORDER BY {scaffold['date_expression']}"
    rows = _execute(_render(sql, parameter_type, "2024-02-28", "2024-03-01"), dialect)
    assert rows == [(key_type(value),) for value in (20240228, 20240229, 20240301)]
    assert scaffold["required_tokens"] == ["{{dashboard_start_yyyymmdd}}", "{{dashboard_end_yyyymmdd}}"]


@pytest.mark.parametrize("grain", ["hour", "week", "month", "year", "", None])
def test_unsupported_grain_is_not_silently_changed_to_day(grain):
    scaffold = build_date_scaffold({"grain": grain, "date_parameter_type": "date"}, "mysql")
    assert not scaffold["supported"]
    assert scaffold["cte_sql"] == scaffold["select_sql"] == ""
    assert scaffold["reason"]
    assert scaffold["instructions"]


@pytest.mark.parametrize("parameter_type", ["timestamp", "unix_millis", "", None])
def test_unsupported_parameter_type_has_explicit_capability_message(parameter_type):
    scaffold = build_date_scaffold({"grain": "day", "date_parameter_type": parameter_type}, "mysql")
    assert not scaffold["supported"]
    assert scaffold["reason"]
    assert not scaffold["select_sql"]


@pytest.mark.parametrize("dialect", ["oracle", "tsql", "pymysql", "", "redshift", "postgres mysql"])
def test_unknown_or_ambiguous_engine_keeps_generic_rules_without_guessing_scaffold(dialect):
    rules = generation_sql_rules(dialect, {"grain": "day", "date_parameter_type": "date"})
    assert not rules["supported"]
    assert rules["identifier_quote"] is None
    assert rules["capability_issues"]
    assert any("SELECT" in rule and "只读" in rule for rule in rules["rules"])
    assert not build_date_scaffold({"grain": "day", "date_parameter_type": "date"}, dialect)["supported"]


@pytest.mark.parametrize("dialect", ["mysql", "mariadb", "doris", "starrocks", "analyticdb", "mysql AnalyticDB MySQL"])
def test_mysql_family_uses_same_rules_for_numeric_dates(dialect):
    rules = generation_sql_rules(dialect, {"grain": "day", "dateParameterType": "yyyymmdd_number"})
    assert rules["supported"]
    assert rules["dialect_family"] == "mysql"
    assert rules["identifier_quote"] == "`"
    assert rules["required_tokens"] == ["{{dashboard_start_yyyymmdd}}", "{{dashboard_end_yyyymmdd}}"]
    assert any("STR_TO_DATE" in rule for rule in rules["rules"])
    assert any("递归" in rule for rule in rules["rules"])


def test_rules_do_not_mutate_configuration_or_share_mutable_results():
    config = {"grain": "day", "date_parameter_type": "yyyymmdd_number"}
    first = generation_sql_rules("postgres", config)
    assert first["identifier_quote"] == '"'
    assert any("TO_DATE" in rule for rule in first["rules"])
    first["rules"].clear()
    first["required_tokens"].clear()
    second = generation_sql_rules("postgres", config)
    assert second["rules"] and second["required_tokens"]
    assert config == {"grain": "day", "date_parameter_type": "yyyymmdd_number"}


@pytest.mark.parametrize("dialect", ["mysql", "postgres"])
def test_composed_aggregate_keeps_dates_without_source_rows(dialect):
    scaffold = build_date_scaffold({"grain": "day", "date_parameter_type": "yyyymmdd_number"}, dialect)
    sql = f"""WITH {scaffold['cte_sql']},
        fixture_records AS (
            SELECT 20240228 AS date_key, 3 AS amount UNION ALL
            SELECT 20240228 AS date_key, 5 AS amount UNION ALL
            SELECT 20240301 AS date_key, 7 AS amount
        ),
        daily_metrics AS (
            SELECT date_key, SUM(amount) AS metric_value
            FROM fixture_records
            WHERE date_key BETWEEN {{{{dashboard_start_yyyymmdd}}}} AND {{{{dashboard_end_yyyymmdd}}}}
            GROUP BY date_key
        )
        SELECT {scaffold['date_expression']}, COALESCE(m.metric_value, 0) AS metric_value
        FROM {scaffold['cte_name']}
        LEFT JOIN daily_metrics AS m ON m.date_key = {scaffold['key_expression']}
        ORDER BY {scaffold['date_expression']}
    """
    rows = _execute(_render(sql, "yyyymmdd_number", "2024-02-28", "2024-03-02"), dialect)
    assert rows == [("2024-02-28", 8), ("2024-02-29", 0), ("2024-03-01", 7), ("2024-03-02", 0)]
    assert _scaffold_issues(sql, scaffold, dialect) == []


@pytest.mark.parametrize("dialect", ["mysql", "postgres"])
def test_reversed_bounds_do_not_manufacture_dates(dialect):
    scaffold = build_date_scaffold({"grain": "day", "date_parameter_type": "date"}, dialect)
    assert _execute(_render(scaffold["select_sql"], "date", "2026-09-16", "2026-09-01"), dialect) == []


@pytest.mark.parametrize("dialect", ["mysql", "postgres"])
def test_scaffold_validation_accepts_composition_and_formatting(dialect):
    scaffold = build_date_scaffold({"grain": "day", "date_parameter_type": "yyyymmdd_number"}, dialect)
    sql = f"""WITH {scaffold['cte_sql']},
        totals AS (SELECT calendar_date, 0 AS metric FROM dashboard_dates),
        latest AS (SELECT amount FROM fixture_records ORDER BY amount DESC LIMIT 1)
        SELECT totals.calendar_date, totals.metric
        FROM totals LEFT JOIN latest ON 1=1 ORDER BY totals.calendar_date
    """
    quote = "`" if dialect == "mysql" else '"'
    sql = sql.replace("p.n + d.n * 10 AS n", "((p.n + d.n * 10)) AS n")
    sql = sql.replace(" AS ", " as ").replace("calendar_date", f"{quote}calendar_date{quote}")
    sql = sql.replace("SELECT", "SELECT /* formatting only */")
    assert _scaffold_issues(sql, scaffold, dialect) == []


@pytest.mark.parametrize("dialect", ["mysql", "postgres"])
@pytest.mark.parametrize("mutation", ["short_sequence", "missing_stage", "reversed_tokens", "same_bound", "static_bound", "quoted_token"])
def test_scaffold_validation_rejects_changed_dynamic_range(dialect, mutation):
    scaffold = build_date_scaffold({"grain": "day", "date_parameter_type": "yyyymmdd_number"}, dialect)
    sql = scaffold["select_sql"]
    if mutation == "short_sequence":
        sql = sql.replace("d.n <= b.day_count", "d.n <= LEAST(b.day_count, 30)")
    elif mutation == "missing_stage":
        sql = sql.replace("FROM dashboard_offsets_6 AS p", "FROM dashboard_offsets_1 AS p")
    elif mutation == "reversed_tokens":
        sql = sql.replace("dashboard_start_yyyymmdd", "temporary_end").replace("dashboard_end_yyyymmdd", "dashboard_start_yyyymmdd").replace("temporary_end", "dashboard_end_yyyymmdd")
    elif mutation == "same_bound":
        sql = sql.replace("dashboard_end_yyyymmdd", "dashboard_start_yyyymmdd")
    elif mutation == "static_bound":
        sql = sql.replace("{{dashboard_end_yyyymmdd}}", "20260916")
    else:
        sql = sql.replace("{{dashboard_start_yyyymmdd}}", "'{{dashboard_start_yyyymmdd}}'")
    assert _scaffold_issues(sql, scaffold, dialect)


@pytest.mark.parametrize("final_select", [
    "SELECT calendar_date FROM fixture_records",
    "SELECT calendar_date FROM unrelated",
    "SELECT (SELECT COUNT(*) FROM dashboard_dates) AS metric",
])
def test_unused_scaffold_is_not_accepted_as_date_output(final_select):
    scaffold = build_date_scaffold({"grain": "day", "date_parameter_type": "date"}, "mysql")
    sql = f"WITH {scaffold['cte_sql']}, unused AS (SELECT calendar_date FROM dashboard_dates), unrelated AS (SELECT calendar_date FROM fixture_records) {final_select}"
    assert _scaffold_issues(sql, scaffold, "mysql")


@pytest.mark.parametrize("wrapper", [
    "SELECT calendar_date FROM dashboard_dates LIMIT 31",
    "SELECT calendar_date FROM (SELECT calendar_date FROM dashboard_dates LIMIT 31) AS limited",
    "SELECT calendar_date FROM dashboard_dates ORDER BY calendar_date OFFSET 1",
    "SELECT calendar_date FROM dashboard_dates UNION ALL SELECT calendar_date FROM fixture_records LIMIT 31",
])
def test_limits_along_the_scaffold_output_path_are_rejected(wrapper):
    scaffold = build_date_scaffold({"grain": "day", "date_parameter_type": "date"}, "postgres")
    assert _scaffold_issues(f"WITH {scaffold['cte_sql']} {wrapper}", scaffold, "postgres")


def test_cte_shadowing_cannot_replace_the_supplied_scaffold():
    scaffold = build_date_scaffold({"grain": "day", "date_parameter_type": "date"}, "mysql")
    sql = f"""WITH {scaffold['cte_sql']},
        hidden AS (
            WITH dashboard_dates AS (SELECT calendar_date FROM fixture_records)
            SELECT calendar_date FROM dashboard_dates
        )
        SELECT calendar_date FROM hidden
    """
    assert _scaffold_issues(sql, scaffold, "mysql")


def test_scaffold_validation_reports_parse_failure_without_raising():
    scaffold = build_date_scaffold({"grain": "day", "date_parameter_type": "date"}, "mysql")
    assert _scaffold_issues("SELECT FROM (", scaffold, "mysql")


def test_unsupported_scaffold_has_no_new_validation_requirement():
    scaffold = build_date_scaffold({"grain": "week", "date_parameter_type": "date"}, "oracle")
    assert _scaffold_issues("SELECT configured_week FROM fixture_records", scaffold, "oracle") == []


@pytest.mark.parametrize("parameter_type", ["date", "yyyymmdd_text"])
def test_bound_identity_is_preserved_for_string_date_parameters(parameter_type):
    scaffold = build_date_scaffold({"grain": "day", "date_parameter_type": parameter_type}, "postgres")
    sql = scaffold["select_sql"]
    assert _scaffold_issues(sql, scaffold, "postgres") == []
    start, end = scaffold["required_tokens"]
    changed = sql.replace(start, "<temporary>").replace(end, start).replace("<temporary>", end)
    assert _scaffold_issues(changed, scaffold, "postgres")


def test_missing_scaffold_and_multiple_statements_are_rejected():
    scaffold = build_date_scaffold({"grain": "day", "date_parameter_type": "date"}, "mysql")
    assert _scaffold_issues("SELECT calendar_date FROM fixture_records", scaffold, "mysql")
    assert _scaffold_issues(scaffold["select_sql"] + "; SELECT 1", scaffold, "mysql")


def test_malformed_scaffold_metadata_returns_an_issue():
    scaffold = build_date_scaffold({"grain": "day", "date_parameter_type": "date"}, "mysql")
    scaffold["cte_name"] = "missing_output"
    assert _scaffold_issues(scaffold["select_sql"], scaffold, "mysql")


def _scaffold_query(query, extra_ctes=""):
    scaffold = build_date_scaffold({"grain": "day", "date_parameter_type": "date"}, "postgres")
    sql = f"""WITH {scaffold['cte_sql']},
        aggregated AS (
            SELECT CAST(record_date AS DATE) AS metric_date, SUM(amount) AS metric
            FROM fixture_records WHERE amount > 0 GROUP BY CAST(record_date AS DATE)
        ){extra_ctes}
        {query}
    """
    return sql, scaffold


@pytest.mark.parametrize("join", ["JOIN", "INNER JOIN", "LEFT SEMI JOIN", "LEFT ANTI JOIN", "RIGHT JOIN"])
def test_non_preserving_join_on_date_path_is_rejected(join):
    sql, scaffold = _scaffold_query(f"""
        SELECT d.calendar_date, a.metric FROM dashboard_dates AS d
        {join} aggregated AS a ON d.calendar_date = a.metric_date
    """)
    assert _scaffold_issues(sql, scaffold, "postgres")


def test_dates_on_right_side_requires_the_supported_left_join_shape():
    sql, scaffold = _scaffold_query("""
        SELECT d.calendar_date, a.metric FROM aggregated AS a
        RIGHT JOIN dashboard_dates AS d ON d.calendar_date = a.metric_date
    """)
    issues = _scaffold_issues(sql, scaffold, "postgres")
    assert issues
    assert any("FROM" in issue and "LEFT JOIN" in issue for issue in issues)


@pytest.mark.parametrize("clause", [
    "WHERE a.metric > 0",
    "WHERE COALESCE(a.metric, 0) > 0",
    "WHERE a.metric_date IS NOT NULL",
    "HAVING SUM(a.metric) > 0",
    "HAVING metric_alias > 0",
])
def test_fact_filter_after_left_join_is_rejected(clause):
    sql, scaffold = _scaffold_query(f"""
        SELECT d.calendar_date, SUM(a.metric) AS metric_alias FROM dashboard_dates AS d
        LEFT JOIN aggregated AS a ON d.calendar_date = a.metric_date
        {clause}
    """)
    assert _scaffold_issues(sql, scaffold, "postgres")


@pytest.mark.parametrize("projection", ["calendar_date, metric_alias", "*", "filled.*"])
def test_fact_filter_in_outer_scope_tracks_renamed_and_star_projections(projection):
    sql, scaffold = _scaffold_query(
        "SELECT out.calendar_date, out.metric_alias FROM forwarded AS out WHERE out.metric_alias > 0",
        f""", filled AS (
            SELECT d.calendar_date, COALESCE(a.metric, 0) AS metric_alias
            FROM dashboard_dates AS d LEFT JOIN aggregated AS a ON a.metric_date=d.calendar_date
        ), forwarded AS (SELECT {projection} FROM filled)
        """,
    )
    assert _scaffold_issues(sql, scaffold, "postgres")


def test_non_preserving_join_in_an_intermediate_date_scope_is_rejected():
    sql, scaffold = _scaffold_query(
        "SELECT calendar_date, metric FROM shortened",
        """, shortened AS (
            SELECT d.calendar_date, a.metric FROM dashboard_dates AS d
            INNER JOIN aggregated AS a ON a.metric_date=d.calendar_date
        )""",
    )
    assert _scaffold_issues(sql, scaffold, "postgres")


@pytest.mark.parametrize("clause", [
    "WHERE d.calendar_date BETWEEN {{dashboard_start_date}} AND {{dashboard_end_date}}",
    "WHERE x.dimension_key IN ('selected')",
    "WHERE d.calendar_date >= {{dashboard_start_date}} AND x.dimension_key = 'selected'",
    "HAVING d.calendar_date <= {{dashboard_end_date}}",
])
def test_date_and_cross_join_dimension_filters_preserve_standard_shape(clause):
    sql, scaffold = _scaffold_query(f"""
        SELECT d.calendar_date, x.dimension_key, COALESCE(a.metric, 0) AS metric_alias
        FROM dashboard_dates AS d CROSS JOIN authorized_dimensions AS x
        LEFT JOIN aggregated AS a ON a.metric_date=d.calendar_date AND a.metric > 0
        {clause}
    """)
    assert _scaffold_issues(sql, scaffold, "postgres") == []


def test_outer_date_and_dimension_filters_follow_projection_lineage():
    sql, scaffold = _scaffold_query(
        """SELECT result_date, group_key, metric FROM renamed
            WHERE result_date >= {{dashboard_start_date}} AND group_key = 'selected'""",
        """, filled AS (
            SELECT d.calendar_date AS result_date, x.dimension_key AS group_key, a.metric
            FROM dashboard_dates AS d CROSS JOIN authorized_dimensions AS x
            LEFT JOIN aggregated AS a ON a.metric_date=d.calendar_date
        ), renamed AS (SELECT * FROM filled)""",
    )
    assert _scaffold_issues(sql, scaffold, "postgres") == []


def test_fact_cte_internal_filters_and_joins_are_outside_date_path():
    sql, scaffold = _scaffold_query("""
        SELECT d.calendar_date, a.metric FROM dashboard_dates AS d LEFT JOIN (
            SELECT a.metric_date, a.metric FROM aggregated AS a
            INNER JOIN fixture_categories AS c ON c.category_key = a.metric_date
            WHERE a.metric > 0
        ) AS a ON a.metric_date=d.calendar_date
    """)
    assert _scaffold_issues(sql, scaffold, "postgres") == []


def test_left_join_fact_source_can_use_dates_to_bound_its_own_scan():
    sql, scaffold = _scaffold_query("""
        SELECT d.calendar_date, a.metric FROM dashboard_dates AS d LEFT JOIN (
            SELECT a.metric_date, a.metric FROM aggregated AS a
            INNER JOIN dashboard_dates AS filter_dates ON filter_dates.calendar_date = a.metric_date
            WHERE a.metric > 0 LIMIT 10
        ) AS a ON a.metric_date=d.calendar_date
    """)
    assert _scaffold_issues(sql, scaffold, "postgres") == []


@pytest.mark.parametrize("mutation", ["inner_join", "fact_where"])
def test_rejected_shapes_reproduce_missing_dates_on_local_fixture(mutation):
    scaffold = build_date_scaffold({"grain": "day", "date_parameter_type": "date"}, "mysql")
    sql = f"""WITH {scaffold['cte_sql']}, daily_metrics AS (
        SELECT CAST('2024-02-28' AS DATE) AS metric_date, 8 AS metric
        UNION ALL SELECT CAST('2024-03-01' AS DATE), 7
    )
    SELECT d.calendar_date, COALESCE(a.metric, 0) AS metric
    FROM dashboard_dates AS d LEFT JOIN daily_metrics AS a ON a.metric_date=d.calendar_date
    ORDER BY d.calendar_date
    """
    if mutation == "inner_join":
        sql = sql.replace("LEFT JOIN", "INNER JOIN")
    else:
        sql = sql.replace("ORDER BY", "WHERE a.metric > 0 ORDER BY")
    assert _execute(_render(sql, "date", "2024-02-28", "2024-03-02"), "mysql") == [
        ("2024-02-28", 8), ("2024-03-01", 7),
    ]
    assert _scaffold_issues(sql, scaffold, "mysql")
