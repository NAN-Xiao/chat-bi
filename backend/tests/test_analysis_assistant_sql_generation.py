"""验证分析助手生成 SQL 时会显式接收语义字段表达式。"""

import ast
import sqlite3
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlglot import exp, parse_one

from apps.analysis_assistant.api import analysis_assistant as analysis_api
from apps.analysis_assistant.service.analysis_time_policy import (
    AnalysisTimeAnchor,
    AnalysisTimePolicy,
    AnalysisTimeResolution,
    AnalysisTimeSource,
)
from apps.analysis_assistant.service.analysis_time_sql import (
    AnalysisTimeSqlError,
    enforce_analysis_time_sql,
)
from apps.db.db import get_sqlglot_dialect

SCHEMA_TIME_FIELDS = {
    "fact_orders": ("business_date",),
    "fact_refunds": ("refund_date",),
}

FORBIDDEN_ANALYSIS_TIME_MODULE = (
    "apps.analysis_assistant.service.analysis_time_policy"
)
FORBIDDEN_ANALYSIS_TIME_SYMBOLS = {
    "AnalysisTimePolicy",
    "AnalysisTimeResolution",
    "DEFAULT_14_DAYS",
    "_resolve_chat_time_policy",
}


def _forbidden_analysis_time_references(source: str) -> set[str]:
    """返回源码 AST 中越过分析助手边界的时间策略引用。"""
    tree = ast.parse(source)
    references: set[str] = set()
    module_aliases: set[str] = set()
    symbol_aliases: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == FORBIDDEN_ANALYSIS_TIME_MODULE:
                    references.add(FORBIDDEN_ANALYSIS_TIME_MODULE)
                    module_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imported_name = f"{module}.{alias.name}" if module else alias.name
                if (
                    module == FORBIDDEN_ANALYSIS_TIME_MODULE
                    or imported_name == FORBIDDEN_ANALYSIS_TIME_MODULE
                ):
                    references.add(FORBIDDEN_ANALYSIS_TIME_MODULE)
                if imported_name == FORBIDDEN_ANALYSIS_TIME_MODULE:
                    module_aliases.add(alias.asname or alias.name)
                if alias.name in FORBIDDEN_ANALYSIS_TIME_SYMBOLS:
                    references.add(alias.name)
                    symbol_aliases[alias.asname or alias.name] = alias.name

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id in FORBIDDEN_ANALYSIS_TIME_SYMBOLS:
                references.add(node.id)
            if node.id in symbol_aliases:
                references.add(symbol_aliases[node.id])
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ANALYSIS_TIME_SYMBOLS:
                references.add(node.attr)
            if isinstance(node.value, ast.Name) and node.value.id in module_aliases:
                references.add(FORBIDDEN_ANALYSIS_TIME_MODULE)

    return references


def _resolved_time() -> AnalysisTimeResolution:
    policy = AnalysisTimePolicy(
        source=AnalysisTimeSource.DEFAULT_14_DAYS,
        window_days=14,
        anchor_date=date(2026, 7, 26),
        start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 26),
        start_inclusive=True,
        end_inclusive=True,
        anchor=AnalysisTimeAnchor("fact_orders", "business_date"),
        description="最近 14 个自然日",
    )
    return AnalysisTimeResolution(policy=policy, status="resolved")


def _enforce(
    sql: str, fields: list[dict[str, str]], *, rewrite: bool = False
) -> str:
    return enforce_analysis_time_sql(
        sql,
        policy=_resolved_time().policy,
        declared_time_fields=fields,
        schema_time_fields=SCHEMA_TIME_FIELDS,
        dialect="postgres",
        allow_rewrite=rewrite,
    )


def test_time_sql_accepts_exact_constant_bounds() -> None:
    sql = "SELECT business_date, SUM(amount) FROM fact_orders WHERE business_date >= DATE '2026-07-13' AND business_date <= DATE '2026-07-26' GROUP BY business_date"

    assert "2026-07-13" in _enforce(
        sql, [{"table": "fact_orders", "field": "business_date"}]
    )


def test_time_sql_rejects_dynamic_max_boundary() -> None:
    sql = "WITH bounds AS (SELECT MAX(business_date) end_date FROM fact_orders) SELECT * FROM fact_orders CROSS JOIN bounds WHERE business_date <= end_date"

    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        _enforce(sql, [{"table": "fact_orders", "field": "business_date"}])


def test_time_sql_rejects_conflicting_constant_range() -> None:
    sql = "SELECT * FROM fact_orders WHERE business_date >= DATE '2026-01-01' AND business_date <= DATE '2026-01-31'"

    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        _enforce(sql, [{"table": "fact_orders", "field": "business_date"}])


def test_time_sql_rewrites_only_one_unambiguous_target() -> None:
    rewritten = _enforce(
        "SELECT * FROM fact_orders",
        [{"table": "fact_orders", "field": "business_date"}],
        rewrite=True,
    )

    assert "2026-07-13" in rewritten
    assert "2026-07-26" in rewritten


def test_time_sql_requires_each_declared_fact_scan() -> None:
    sql = "SELECT * FROM fact_orders o JOIN fact_refunds r ON r.order_id = o.id WHERE o.business_date >= DATE '2026-07-13' AND o.business_date <= DATE '2026-07-26'"

    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        _enforce(
            sql,
            [
                {"table": "fact_orders", "field": "business_date"},
                {"table": "fact_refunds", "field": "refund_date"},
            ],
        )


def test_time_sql_does_not_choose_first_field_when_declaration_is_ambiguous() -> None:
    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        enforce_analysis_time_sql(
            "SELECT * FROM fact_orders",
            policy=_resolved_time().policy,
            declared_time_fields=[],
            schema_time_fields={"fact_orders": ("business_date", "created_at")},
            dialect="postgres",
            allow_rewrite=True,
        )


def test_time_sql_allows_dimension_query_without_temporal_fields() -> None:
    sql = enforce_analysis_time_sql(
        "SELECT region_id, region_name FROM dim_region",
        policy=_resolved_time().policy,
        declared_time_fields=[],
        schema_time_fields=SCHEMA_TIME_FIELDS,
        dialect="postgres",
        allow_rewrite=False,
    )

    assert "dim_region" in sql


def test_time_sql_ignores_irrelevant_declarations_for_dimension_query() -> None:
    sql = enforce_analysis_time_sql(
        "SELECT region_id, region_name FROM dim_region",
        policy=_resolved_time().policy,
        declared_time_fields=[{"table": "", "field": ""}],
        schema_time_fields=SCHEMA_TIME_FIELDS,
        dialect="postgres",
        allow_rewrite=False,
    )

    assert "dim_region" in sql


def test_time_sql_error_message_never_exposes_sql_or_fields() -> None:
    raw_sql = "SELECT * FROM fact_orders WHERE"

    with pytest.raises(AnalysisTimeSqlError) as caught:
        _enforce(
            raw_sql,
            [{"table": "fact_orders", "field": "business_date"}],
        )

    assert str(caught.value) == "时间边界校验未通过，当前分析角度未执行。"
    assert raw_sql not in str(caught.value)
    assert "business_date" not in str(caught.value)


def test_time_sql_accepts_qualified_alias_bounds() -> None:
    sql = "SELECT * FROM fact_orders AS Orders WHERE Orders.business_date >= DATE '2026-07-13' AND Orders.business_date <= DATE '2026-07-26'"

    assert "2026-07-26" in _enforce(
        sql, [{"table": "FACT_ORDERS", "field": "BUSINESS_DATE"}]
    )


def test_time_sql_rewrite_preserves_quoted_alias_identifier() -> None:
    rewritten = _enforce(
        'SELECT * FROM fact_orders AS "Orders"',
        [{"table": "fact_orders", "field": "business_date"}],
        rewrite=True,
    )
    where = parse_one(rewritten, read="postgres").args["where"]
    qualifiers = [column.args.get("table") for column in where.find_all(exp.Column)]

    assert qualifiers
    assert all(qualifier.name == "Orders" for qualifier in qualifiers)
    assert all(qualifier.args.get("quoted") is True for qualifier in qualifiers)


def test_time_sql_accepts_reversed_constant_comparisons() -> None:
    sql = "SELECT * FROM fact_orders o WHERE DATE '2026-07-13' <= o.business_date AND DATE '2026-07-26' >= o.business_date"

    assert "2026-07-13" in _enforce(
        sql, [{"table": "fact_orders", "field": "business_date"}]
    )


def test_time_sql_accepts_exact_between_bounds() -> None:
    sql = "SELECT * FROM fact_orders o WHERE o.business_date BETWEEN DATE '2026-07-13' AND DATE '2026-07-26'"

    assert "BETWEEN" in _enforce(
        sql, [{"table": "fact_orders", "field": "business_date"}]
    )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM fact_orders o WHERE CASE WHEN FALSE THEN o.business_date >= DATE '2026-07-13' AND o.business_date <= DATE '2026-07-26' ELSE TRUE END",
        "SELECT * FROM fact_orders o WHERE COALESCE(o.business_date >= DATE '2026-07-13' AND o.business_date <= DATE '2026-07-26', TRUE)",
    ],
)
def test_time_sql_rejects_non_conjunctive_where_wrappers(sql: str) -> None:
    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        _enforce(sql, [{"table": "fact_orders", "field": "business_date"}])


def test_time_sql_accepts_parenthesized_conjunctive_bounds() -> None:
    sql = "SELECT * FROM fact_orders o WHERE ((o.business_date >= DATE '2026-07-13') AND (o.business_date <= DATE '2026-07-26'))"

    assert "2026-07-13" in _enforce(
        sql, [{"table": "fact_orders", "field": "business_date"}]
    )


def test_time_sql_normalizes_qualified_table_without_losing_schema() -> None:
    rewritten = enforce_analysis_time_sql(
        "SELECT * FROM Analytics.Fact_Orders AS Orders",
        policy=_resolved_time().policy,
        declared_time_fields=[
            {"table": "analytics.fact_orders", "field": "business_date"}
        ],
        schema_time_fields={"ANALYTICS.FACT_ORDERS": ("BUSINESS_DATE",)},
        dialect="postgres",
        allow_rewrite=True,
    )

    assert "2026-07-13" in rewritten
    assert "2026-07-26" in rewritten


def test_time_sql_binds_unique_qualified_schema_to_unqualified_scan() -> None:
    rewritten = enforce_analysis_time_sql(
        "SELECT * FROM fact_orders o",
        policy=_resolved_time().policy,
        declared_time_fields=[
            {"table": "analytics.fact_orders", "field": "business_date"}
        ],
        schema_time_fields={"analytics.fact_orders": ("business_date",)},
        dialect="postgres",
        allow_rewrite=True,
    )

    assert "2026-07-13" in rewritten
    assert "2026-07-26" in rewritten


def test_time_sql_rejects_missing_bounds_for_unqualified_unique_schema_scan() -> None:
    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        enforce_analysis_time_sql(
            "SELECT * FROM fact_orders o",
            policy=_resolved_time().policy,
            declared_time_fields=[
                {"table": "analytics.fact_orders", "field": "business_date"}
            ],
            schema_time_fields={"analytics.fact_orders": ("business_date",)},
            dialect="postgres",
            allow_rewrite=False,
        )


def test_time_sql_rejects_ambiguous_qualified_schemas_for_unqualified_scan() -> None:
    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        enforce_analysis_time_sql(
            "SELECT * FROM fact_orders o",
            policy=_resolved_time().policy,
            declared_time_fields=[],
            schema_time_fields={
                "analytics.fact_orders": ("business_date",),
                "archive.fact_orders": ("archived_date",),
            },
            dialect="postgres",
            allow_rewrite=False,
        )


def test_time_sql_rejects_qualified_scan_with_different_full_schema_identity() -> None:
    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        enforce_analysis_time_sql(
            "SELECT * FROM analytics.fact_orders o",
            policy=_resolved_time().policy,
            declared_time_fields=[
                {
                    "table": "warehouse.analytics.fact_orders",
                    "field": "business_date",
                }
            ],
            schema_time_fields={
                "warehouse.analytics.fact_orders": ("business_date",)
            },
            dialect="postgres",
            allow_rewrite=True,
        )


def test_time_sql_does_not_mix_same_table_name_from_different_schemas() -> None:
    sql = "SELECT * FROM analytics.fact_orders current_orders JOIN archive.fact_orders archived_orders ON archived_orders.id = current_orders.id WHERE current_orders.business_date >= DATE '2026-07-13' AND current_orders.business_date <= DATE '2026-07-26'"

    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        enforce_analysis_time_sql(
            sql,
            policy=_resolved_time().policy,
            declared_time_fields=[
                {"table": "analytics.fact_orders", "field": "business_date"},
                {"table": "archive.fact_orders", "field": "archived_date"},
            ],
            schema_time_fields={
                "analytics.fact_orders": ("business_date",),
                "archive.fact_orders": ("archived_date",),
            },
            dialect="postgres",
            allow_rewrite=False,
        )


def test_time_sql_rewrites_the_select_that_owns_the_unique_scan() -> None:
    rewritten = _enforce(
        "SELECT * FROM (SELECT * FROM fact_orders o) nested_orders",
        [{"table": "fact_orders", "field": "business_date"}],
        rewrite=True,
    )
    tree = parse_one(rewritten, read="postgres")
    inner_select = tree.find(exp.Subquery).this

    assert tree.args.get("where") is None
    assert isinstance(inner_select, exp.Select)
    assert inner_select.args.get("where") is not None


def test_time_sql_scopes_repeated_aliases_in_different_subqueries() -> None:
    sql = "SELECT * FROM (SELECT * FROM fact_orders o WHERE o.business_date >= DATE '2026-07-13' AND o.business_date <= DATE '2026-07-26') bounded JOIN (SELECT * FROM fact_orders o) unbounded ON TRUE"

    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        _enforce(
            sql,
            [{"table": "fact_orders", "field": "business_date"}],
            rewrite=False,
        )


def test_time_sql_rewrites_one_missing_repeated_alias_in_its_own_scope() -> None:
    sql = "SELECT * FROM (SELECT * FROM fact_orders o WHERE o.business_date >= DATE '2026-07-13' AND o.business_date <= DATE '2026-07-26') bounded JOIN (SELECT * FROM fact_orders o) unbounded ON TRUE"

    rewritten = _enforce(
        sql,
        [{"table": "fact_orders", "field": "business_date"}],
        rewrite=True,
    )

    assert rewritten.count("2026-07-13") == 2
    assert rewritten.count("2026-07-26") == 2


def test_time_sql_rewrite_adds_only_the_missing_partial_boundary() -> None:
    sql = "SELECT * FROM fact_orders o WHERE o.business_date >= DATE '2026-07-13'"

    rewritten = _enforce(
        sql,
        [{"table": "fact_orders", "field": "business_date"}],
        rewrite=True,
    )

    assert rewritten.count("2026-07-13") == 1
    assert rewritten.count("2026-07-26") == 1


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM fact_orders o WHERE o.business_date > DATE '2026-07-13'",
        "SELECT * FROM fact_orders o WHERE o.business_date >= DATE '2026-07-13' AND o.business_date <= CURRENT_DATE",
    ],
)
def test_time_sql_rewrite_rejects_existing_non_policy_boundaries(sql: str) -> None:
    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        _enforce(
            sql,
            [{"table": "fact_orders", "field": "business_date"}],
            rewrite=True,
        )


def test_time_sql_rejects_unqualified_same_named_fields_across_tables() -> None:
    sql = "SELECT * FROM fact_orders o JOIN fact_shipments s ON s.order_id = o.id WHERE business_date >= DATE '2026-07-13' AND business_date <= DATE '2026-07-26'"

    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        enforce_analysis_time_sql(
            sql,
            policy=_resolved_time().policy,
            declared_time_fields=[
                {"table": "fact_orders", "field": "business_date"},
                {"table": "fact_shipments", "field": "business_date"},
            ],
            schema_time_fields={
                "fact_orders": ("business_date",),
                "fact_shipments": ("business_date",),
            },
            dialect="postgres",
            allow_rewrite=False,
        )


def test_time_sql_rejects_duplicate_aliases_in_one_select_scope() -> None:
    sql = "SELECT * FROM fact_orders o JOIN fact_orders o ON o.parent_id = o.id WHERE o.business_date >= DATE '2026-07-13' AND o.business_date <= DATE '2026-07-26'"

    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        _enforce(
            sql,
            [{"table": "fact_orders", "field": "business_date"}],
            rewrite=False,
        )


def test_time_sql_allows_selected_max_when_where_has_exact_bounds() -> None:
    sql = "SELECT MAX(o.business_date) AS latest_date FROM fact_orders o WHERE o.business_date >= DATE '2026-07-13' AND o.business_date <= DATE '2026-07-26'"

    assert "MAX" in _enforce(
        sql, [{"table": "fact_orders", "field": "business_date"}]
    )


def test_time_sql_allows_unrelated_dimension_cross_join_with_exact_bounds() -> None:
    sql = "SELECT o.id, d.region_name FROM fact_orders o CROSS JOIN dim_region d WHERE o.business_date >= DATE '2026-07-13' AND o.business_date <= DATE '2026-07-26'"

    assert "CROSS JOIN" in _enforce(
        sql, [{"table": "fact_orders", "field": "business_date"}]
    )


def test_time_sql_ignores_same_named_max_column_from_other_alias() -> None:
    sql = "SELECT MAX(d.business_date) AS dimension_date FROM fact_orders o JOIN dim_events d ON d.order_id = o.id WHERE o.business_date >= DATE '2026-07-13' AND o.business_date <= DATE '2026-07-26'"

    assert "MAX" in _enforce(
        sql, [{"table": "fact_orders", "field": "business_date"}]
    )


def test_time_sql_rejects_dynamic_bound_cte_even_when_rewrite_is_allowed() -> None:
    sql = "WITH bounds AS (SELECT MAX(snapshot_date) AS end_date FROM dim_calendar) SELECT * FROM fact_orders o CROSS JOIN bounds b WHERE o.business_date >= DATE '2026-07-13' AND o.business_date <= b.end_date"

    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        _enforce(
            sql,
            [{"table": "fact_orders", "field": "business_date"}],
            rewrite=True,
        )


def test_time_sql_requires_explicit_field_even_for_one_temporal_candidate() -> None:
    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        enforce_analysis_time_sql(
            "SELECT * FROM fact_orders",
            policy=_resolved_time().policy,
            declared_time_fields=[],
            schema_time_fields={"fact_orders": ("business_date",)},
            dialect="postgres",
            allow_rewrite=True,
        )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM dim_region d LEFT JOIN fact_orders o ON o.region_id = d.id",
        "SELECT * FROM fact_orders o RIGHT JOIN dim_region d ON d.id = o.region_id",
        "SELECT * FROM fact_orders o FULL JOIN dim_region d ON d.id = o.region_id",
    ],
)
def test_time_sql_does_not_rewrite_nullable_outer_join_side(sql: str) -> None:
    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        _enforce(
            sql,
            [{"table": "fact_orders", "field": "business_date"}],
            rewrite=True,
        )


def test_time_sql_rewrites_inner_join_added_after_right_join() -> None:
    sql = (
        "SELECT * FROM dim_old a RIGHT JOIN dim_current b ON b.id = a.id "
        "INNER JOIN fact_orders o ON o.region_id = b.id"
    )

    rewritten = _enforce(
        sql,
        [{"table": "fact_orders", "field": "business_date"}],
        rewrite=True,
    )

    assert "2026-07-13" in rewritten
    assert "2026-07-26" in rewritten


def test_time_sql_accepts_mandatory_inner_join_on_bounds() -> None:
    sql = (
        "SELECT * FROM dim_region d INNER JOIN fact_orders o "
        "ON o.region_id = d.id "
        "AND o.business_date >= DATE '2026-07-13' "
        "AND o.business_date <= DATE '2026-07-26'"
    )

    assert "INNER JOIN" in _enforce(
        sql,
        [{"table": "fact_orders", "field": "business_date"}],
    )


def test_time_sql_fails_closed_when_declared_field_has_no_verified_metadata() -> None:
    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        enforce_analysis_time_sql(
            "SELECT * FROM event_log",
            policy=_resolved_time().policy,
            declared_time_fields=[{"table": "public.event_log", "field": "dt"}],
            schema_time_fields={},
            dialect="postgres",
            allow_rewrite=True,
        )


def test_time_sql_fails_closed_for_unverified_declared_scan_in_mixed_join() -> None:
    sql = (
        "SELECT * FROM fact_orders o "
        "JOIN legacy_events l ON l.order_id = o.id "
        "WHERE o.business_date >= DATE '2026-07-13' "
        "AND o.business_date <= DATE '2026-07-26'"
    )

    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        enforce_analysis_time_sql(
            sql,
            policy=_resolved_time().policy,
            declared_time_fields=[
                {"table": "fact_orders", "field": "business_date"},
                {"table": "legacy_events", "field": "dt"},
            ],
            schema_time_fields={"fact_orders": ("business_date",)},
            dialect="postgres",
            allow_rewrite=False,
        )


def test_time_sql_fails_closed_for_unique_bare_declaration_on_qualified_scan() -> None:
    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        enforce_analysis_time_sql(
            "SELECT * FROM analytics.legacy_events",
            policy=_resolved_time().policy,
            declared_time_fields=[{"table": "legacy_events", "field": "dt"}],
            schema_time_fields={},
            dialect="postgres",
            allow_rewrite=True,
        )


def test_time_sql_fails_closed_for_empty_field_on_current_unverified_scan() -> None:
    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        enforce_analysis_time_sql(
            "SELECT * FROM legacy_events",
            policy=_resolved_time().policy,
            declared_time_fields=[{"table": "legacy_events", "field": ""}],
            schema_time_fields={},
            dialect="postgres",
            allow_rewrite=True,
        )


def test_timestamp_bounds_use_next_day_half_open_interval() -> None:
    schema = """
# Table: fact_orders
[
(created_at:timestamp, role=event_time)
]
"""
    candidates = analysis_api._schema_time_field_candidates(schema, ["fact_orders"])
    rewritten = enforce_analysis_time_sql(
        "SELECT * FROM fact_orders o",
        policy=_resolved_time().policy,
        declared_time_fields=[{"table": "fact_orders", "field": "created_at"}],
        schema_time_fields=candidates,
        dialect="postgres",
        allow_rewrite=True,
    )

    assert ">= CAST('2026-07-13 00:00:00' AS TIMESTAMP)" in rewritten
    assert "< CAST('2026-07-27 00:00:00' AS TIMESTAMP)" in rewritten


def test_time_sql_accepts_existing_timestamp_half_open_bounds() -> None:
    schema = "# Table: fact_orders\n[\n(created_at:timestamp, role=event_time)\n]"
    sql = (
        "SELECT * FROM fact_orders o "
        "WHERE o.created_at >= CAST('2026-07-13 00:00:00' AS TIMESTAMP) "
        "AND o.created_at < CAST('2026-07-27 00:00:00' AS TIMESTAMP)"
    )

    assert "2026-07-27" in enforce_analysis_time_sql(
        sql,
        policy=_resolved_time().policy,
        declared_time_fields=[{"table": "fact_orders", "field": "created_at"}],
        schema_time_fields=analysis_api._schema_time_field_candidates(
            schema, ["fact_orders"]
        ),
        dialect="postgres",
        allow_rewrite=False,
    )


def test_timestamp_open_start_moves_to_next_day_and_uses_gte() -> None:
    policy = AnalysisTimePolicy(
        source=AnalysisTimeSource.USER,
        window_days=None,
        anchor_date=date(2026, 7, 26),
        start_date=date(2026, 7, 14),
        end_date=date(2026, 7, 26),
        start_inclusive=False,
        end_inclusive=True,
        anchor=AnalysisTimeAnchor("fact_orders", "created_at"),
        description="14 日之后",
    )
    schema = "# Table: fact_orders\n[\n(created_at:timestamp, role=event_time)\n]"
    rewritten = enforce_analysis_time_sql(
        "SELECT * FROM fact_orders",
        policy=policy,
        declared_time_fields=[{"table": "fact_orders", "field": "created_at"}],
        schema_time_fields=analysis_api._schema_time_field_candidates(
            schema, ["fact_orders"]
        ),
        dialect="postgres",
        allow_rewrite=True,
    )

    assert ">= CAST('2026-07-15 00:00:00' AS TIMESTAMP)" in rewritten


@pytest.mark.parametrize(
    ("field_type", "metadata", "expected_lower", "expected_upper"),
    [
        ("varchar", "role=partition_date; encoding=yyyyMMdd", "'20260713'", "'20260726'"),
        ("integer", "role=partition_date; encoding=yyyyMMdd", "20260713", "20260726"),
        ("bigint", "role=event_time; encoding=epoch_milliseconds", "1783900800000", "1785110400000"),
    ],
)
def test_structured_non_native_time_encoding_generates_matching_constants(
    field_type: str,
    metadata: str,
    expected_lower: str,
    expected_upper: str,
) -> None:
    schema = f"# Table: event_log\n[\n(event_time:{field_type}, {metadata})\n]"
    candidates = analysis_api._schema_time_field_candidates(schema, ["event_log"])
    rewritten = enforce_analysis_time_sql(
        "SELECT * FROM event_log e",
        policy=_resolved_time().policy,
        declared_time_fields=[{"table": "event_log", "field": "event_time"}],
        schema_time_fields=candidates,
        dialect="postgres",
        allow_rewrite=True,
    )

    assert expected_lower in rewritten
    assert expected_upper in rewritten


def test_unstructured_non_native_time_declaration_fails_closed() -> None:
    schema = "# Table: event_log\n[\n(event_time:bigint, role=event_time)\n]"
    candidates = analysis_api._schema_time_field_candidates(schema, ["event_log"])

    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        enforce_analysis_time_sql(
            "SELECT * FROM event_log",
            policy=_resolved_time().policy,
            declared_time_fields=[{"table": "event_log", "field": "event_time"}],
            schema_time_fields=candidates,
            dialect="postgres",
            allow_rewrite=True,
        )


def test_sqlite_iso_text_date_rewrite_executes_against_real_database() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE orders (business_date TEXT, amount INTEGER)")
        connection.executemany(
            "INSERT INTO orders VALUES (?, ?)",
            [
                ("2026-07-12", 1),
                ("2026-07-13", 2),
                ("2026-07-26", 3),
                ("2026-07-27", 4),
            ],
        )
        schema = (
            "# Table: orders\n[\n"
            "(business_date:text, role=partition_date; encoding=iso_date)\n]"
        )
        rewritten = enforce_analysis_time_sql(
            "SELECT business_date FROM orders ORDER BY business_date",
            policy=_resolved_time().policy,
            declared_time_fields=[{"table": "orders", "field": "business_date"}],
            schema_time_fields=analysis_api._schema_time_field_candidates(
                schema, ["orders"]
            ),
            dialect="sqlite",
            allow_rewrite=True,
        )

        rows = connection.execute(rewritten).fetchall()
    finally:
        connection.close()

    assert "CAST(" not in rewritten.upper()
    assert rows == [("2026-07-13",), ("2026-07-26",)]


def test_sqlite_datasource_type_preserves_sqlglot_dialect() -> None:
    assert get_sqlglot_dialect("sqlite") == "sqlite"


def test_time_sql_rewrite_preserves_quoted_case_sensitive_field() -> None:
    schema = '# Table: orders\n[\n("BusinessDate":date, role=partition_date)\n]'
    rewritten = enforce_analysis_time_sql(
        "SELECT * FROM orders",
        policy=_resolved_time().policy,
        declared_time_fields=[{"table": "orders", "field": "BusinessDate"}],
        schema_time_fields=analysis_api._schema_time_field_candidates(
            schema, ["orders"]
        ),
        dialect="postgres",
        allow_rewrite=True,
    )

    assert 'orders."BusinessDate"' in rewritten


def test_sql_generation_semantic_mappings_preserve_json_expression() -> None:
    """JSON 子字段必须在生成 SQL 前以可执行表达式提供给模型。"""
    schema = """
# Table: user
[
(remain:json, 用户留存标记 JSON),
(remain.remain7:boolean_flag, 注册后第 7 日留存标记; role=json_path_flag; source=remain; json_path=$.remain7; expression=JSON_UNQUOTE(JSON_EXTRACT(`user`.`remain`, '$.remain7')); SQL must use expression instead of this dictionary field name)
]
"""

    mappings = analysis_api._sql_generation_semantic_mappings(schema)

    assert "逻辑字段：remain.remain7" in mappings
    assert "SQL 表达式：JSON_UNQUOTE(JSON_EXTRACT(`user`.`remain`, '$.remain7'))" in mappings
    assert "不得把 JSON 子字段末段 remain7 当作物理列" in mappings


def test_all_sql_generation_prompts_require_backend_resolved_time_policy() -> None:
    """计划与预测必须返回时间字段元数据并服从后端常量边界。"""
    plan_prompts = (
        analysis_api.PLAN_PROMPT,
        analysis_api.FORECAST_PLAN_PROMPT,
    )

    for prompt in plan_prompts:
        assert "后端提供的时间策略是最终约束，不得重新解释或扩大" in prompt
        assert "具体日期常量" in prompt
        assert "不得使用动态 MAX(date)、bounds CTE 或 CROSS JOIN bounds" in prompt
        assert '每个 query 必须返回 time_fields 数组，元素格式为 {"table":"物理表名","field":"物理时间字段"}' in prompt
        assert "图表标题、分析说明和最终结论必须说明实际使用的时间范围" in prompt
        assert "WITH bounds AS (SELECT MAX" not in prompt


def test_sql_repair_prompt_only_requires_preserving_backend_time_bounds() -> None:
    """SQL 修复输出只能包含 SQL，不承担计划或回答元数据契约。"""
    prompt = analysis_api.SQL_REPAIR_PROMPT

    assert '"sql": "修正后的只读 SQL"' in prompt
    assert "后端提供的时间策略是最终约束，不得重新解释或扩大" in prompt
    assert "具体起止日期和包含关系" in prompt
    assert "不得使用动态 MAX(date)、bounds CTE 或 CROSS JOIN bounds" in prompt
    assert "time_fields" not in prompt
    assert "图表标题、分析说明和最终结论" not in prompt


def test_default_analysis_time_policy_stays_inside_analysis_assistant() -> None:
    """默认分析时间策略不得进入分析助手之外的后端应用源码。"""
    repo_apps = Path(__file__).resolve().parents[1] / "apps"
    violations: dict[str, list[str]] = {}

    for path in sorted(repo_apps.rglob("*.py")):
        relative_path = path.relative_to(repo_apps)
        if relative_path.parts[0] == "analysis_assistant":
            continue
        references = _forbidden_analysis_time_references(
            path.read_text(encoding="utf-8-sig")
        )
        if references:
            violations[relative_path.as_posix()] = sorted(references)

    assert violations == {}


def test_analysis_time_scope_ast_detects_aliased_imports() -> None:
    """AST 范围检查必须识别模块别名和符号别名导入。"""
    source = """
import apps.analysis_assistant.service.analysis_time_policy as time_policy
from apps.analysis_assistant.service.analysis_time_policy import (
    AnalysisTimeResolution as TimeResolution,
)

policy = time_policy.AnalysisTimePolicy
"""

    references = _forbidden_analysis_time_references(source)

    assert FORBIDDEN_ANALYSIS_TIME_MODULE in references
    assert "AnalysisTimePolicy" in references
    assert "AnalysisTimeResolution" in references


def test_analysis_prompts_forbid_dynamic_time_bounds() -> None:
    """计划、预测和修复提示词必须共同服从后端解析的常量时间边界。"""
    prompts = (
        analysis_api.PLAN_PROMPT,
        analysis_api.FORECAST_PLAN_PROMPT,
        analysis_api.SQL_REPAIR_PROMPT,
    )

    for prompt in prompts:
        assert "具体日期常量" in prompt
        assert "CROSS JOIN bounds" in prompt
        assert "不得重新解释或扩大" in prompt


def test_plan_prompt_receives_backend_resolved_constant_time_policy() -> None:
    class CaptureLLM:
        def __init__(self) -> None:
            self.messages = []

        def invoke(self, messages):
            self.messages = messages
            return SimpleNamespace(
                content=(
                    '{"intro":"分析","queries":[{"id":"q1","title":"趋势",'
                    '"purpose":"趋势","sql":"SELECT 1","time_fields":[]}]}'
                )
            )

    llm = CaptureLLM()
    request = analysis_api.AnalysisAssistantRequest(
        datasource_id=1,
        messages=[analysis_api.AnalysisAssistantMessage(role="user", content="分析收入")],
    )

    analysis_api._build_plan(
        llm,
        request,
        "",
        "",
        SimpleNamespace(name="测试", type="pg"),
        time_resolution=_resolved_time(),
    )

    prompt = llm.messages[-1].content
    assert "2026-07-13" in prompt
    assert "2026-07-26" in prompt
    assert "不得重新解释或扩大" in prompt
    assert "具体日期常量" in prompt


def test_forecast_plan_prompt_receives_same_backend_time_policy() -> None:
    class CaptureLLM:
        def __init__(self) -> None:
            self.messages = []

        def invoke(self, messages):
            self.messages = messages
            return SimpleNamespace(
                content=(
                    '{"intro":"预测","queries":[{"id":"q1","title":"预测趋势",'
                    '"purpose":"预测","sql":"SELECT 1","time_fields":[]}]}'
                )
            )

    llm = CaptureLLM()
    request = analysis_api.AnalysisAssistantRequest(
        datasource_id=1,
        messages=[analysis_api.AnalysisAssistantMessage(role="user", content="预测收入")],
    )

    analysis_api._build_forecast_plan(
        llm,
        request,
        "",
        "",
        SimpleNamespace(name="测试", type="pg"),
        time_resolution=_resolved_time(),
    )

    prompt = llm.messages[-1].content
    assert "2026-07-13" in prompt
    assert "2026-07-26" in prompt


def test_initial_outline_receives_backend_resolved_time_policy() -> None:
    request = analysis_api.AnalysisAssistantRequest(
        datasource_id=1,
        messages=[analysis_api.AnalysisAssistantMessage(role="user", content="分析收入")],
    )

    messages = analysis_api._initial_outline_messages(
        request,
        time_resolution=_resolved_time(),
    )

    prompt = messages[-1].content
    assert "2026-07-13" in prompt
    assert "2026-07-26" in prompt


def test_unresolved_time_policy_context_limits_plan_scope() -> None:
    context = analysis_api._time_policy_context(
        AnalysisTimeResolution(policy=None, status="unresolved")
    )

    assert "当前无法确认最大业务日期" in context
    assert "只生成能够明确证明时间边界的数据块" in context


def test_summary_and_final_answer_receive_backend_resolved_time_policy() -> None:
    class CaptureLLM:
        def __init__(self) -> None:
            self.messages = []

        def invoke(self, messages):
            self.messages = messages
            return SimpleNamespace(content="时间范围内收入稳定")

    llm = CaptureLLM()
    block = {
        "title": "收入趋势",
        "purpose": "查看收入",
        "sql": "SELECT 1",
        "fields": ["收入"],
        "data": [{"收入": 1}],
    }
    time_resolution = _resolved_time()

    analysis_api._summarise_block(
        llm,
        "分析收入",
        block,
        time_resolution=time_resolution,
    )
    summary_prompt = llm.messages[-1].content

    analysis_api._final_answer(
        llm,
        "分析收入",
        "分析收入趋势",
        [block],
        time_resolution=time_resolution,
    )
    final_prompt = llm.messages[-1].content

    for prompt in (summary_prompt, final_prompt):
        assert "2026-07-13" in prompt
        assert "2026-07-26" in prompt
        assert "不得重新解释或扩大" in prompt
        assert "必须说明实际使用的时间范围" in prompt
        assert "无适用时间字段时不得虚构时间过滤" in prompt


def test_empty_summary_reports_resolved_time_policy_without_calling_llm() -> None:
    class UnexpectedLLM:
        def invoke(self, _messages):
            raise AssertionError("空结果摘要不应调用 LLM")

    summary = analysis_api._summarise_block(
        UnexpectedLLM(),
        "分析收入",
        {"title": "收入趋势", "data": [], "time_fields": []},
        time_resolution=_resolved_time(),
    )

    assert summary.startswith("后端为本次分析确定的时间范围是")
    assert "2026-07-13（含）" in summary
    assert "2026-07-26（含）" in summary
    assert "没有返回数据" in summary
    assert "已添加时间过滤" not in summary


def test_empty_summary_reports_unresolved_time_policy_without_calling_llm() -> None:
    class UnexpectedLLM:
        def invoke(self, _messages):
            raise AssertionError("空结果摘要不应调用 LLM")

    summary = analysis_api._summarise_block(
        UnexpectedLLM(),
        "分析收入",
        {"title": "收入趋势", "data": []},
        time_resolution=AnalysisTimeResolution(policy=None, status="unresolved"),
    )

    assert "没有返回数据" in summary
    assert "无法确认时间边界" in summary
    assert "已添加时间过滤" not in summary


def test_sql_repair_keeps_data_skill_when_tracking_context_is_large() -> None:
    """失败重试不能让长埋点上下文截断数据源专属 SQL 示例。"""
    class CaptureLLM:
        def __init__(self) -> None:
            self.messages = []

        def invoke(self, messages):
            self.messages = messages
            return SimpleNamespace(content='{"sql":"SELECT 1"}')

    llm = CaptureLLM()
    data_skill = "D7 规则\n" + "d" * 19000 + "\n## 七日留存 SQL 示例\nWITH bounds AS (...)"
    tracking_context = "埋点上下文\n" + "t" * 25000

    analysis_api._repair_sql(
        llm,
        question="近14天的七日留存趋势",
        raw_query={"title": "七日留存趋势", "purpose": "查看 D7 留存"},
        failed_sql="SELECT broken",
        error=ValueError("执行失败"),
        schema="",
        sample_data="",
        tracking_context=tracking_context,
        data_skill=data_skill,
        time_resolution=_resolved_time(),
    )

    prompt = llm.messages[-1].content
    assert "## 七日留存 SQL 示例" in prompt
    assert "工作空间数据字典/埋点方案" in prompt
    assert tracking_context[:12000] in prompt
    assert tracking_context[12000:] not in prompt
    assert "2026-07-13" in prompt
    assert "2026-07-26" in prompt


def test_prepare_time_safe_sql_repairs_before_ast_rewrite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[bool] = []

    def fake_prepare(*_args, allow_time_rewrite=False, **_kwargs):
        calls.append(allow_time_rewrite)
        if len(calls) == 1:
            raise AnalysisTimeSqlError()
        return (
            "SELECT * FROM fact_orders "
            "WHERE business_date >= DATE '2026-07-13' "
            "AND business_date <= DATE '2026-07-26'"
        )

    monkeypatch.setattr(analysis_api, "_prepare_sql_for_execution", fake_prepare)
    monkeypatch.setattr(
        analysis_api,
        "_repair_sql",
        lambda *_args, **_kwargs: "SELECT * FROM fact_orders",
    )

    result = analysis_api._prepare_time_safe_query_sql(
        llm=object(),
        session=object(),
        current_user=object(),
        datasource=SimpleNamespace(type="postgresql"),
        raw_query={
            "sql": "SELECT * FROM fact_orders",
            "time_fields": [
                {"table": "fact_orders", "field": "business_date"}
            ],
        },
        question="分析收入",
        schema="",
        sample_data="",
        data_profile="",
        custom_agent="",
        tracking_context="",
        data_skill="",
        allowed_tables=["fact_orders"],
        time_resolution=_resolved_time(),
        schema_time_fields=SCHEMA_TIME_FIELDS,
        dialect="postgres",
    )

    assert "2026-07-13" in result
    assert calls == [False, True]


def test_prepare_time_safe_sql_never_executes_unbounded_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repair_calls: list[str] = []

    def fake_repair(*_args, **_kwargs):
        repair_calls.append("repair")
        return "SELECT * FROM fact_orders"

    monkeypatch.setattr(
        analysis_api,
        "_repair_sql",
        fake_repair,
    )
    monkeypatch.setattr(
        analysis_api,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], {"fact_orders"}),
    )

    with pytest.raises(AnalysisTimeSqlError):
        analysis_api._prepare_time_safe_query_sql(
            llm=object(),
            session=object(),
            current_user=object(),
            datasource=SimpleNamespace(type="postgresql"),
            raw_query={"sql": "SELECT * FROM fact_orders", "time_fields": []},
            question="分析收入",
            schema="",
            sample_data="",
            data_profile="",
            custom_agent="",
            tracking_context="",
            data_skill="",
            allowed_tables=["fact_orders"],
            time_resolution=_resolved_time(),
            schema_time_fields={
                "fact_orders": ("business_date", "created_at")
            },
            dialect="postgres",
        )

    assert repair_calls == ["repair"]


def test_prepare_sql_unresolved_policy_uses_ast_table_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validated: list[str] = []

    def fake_validate(**kwargs):
        validated.append(kwargs["sql"])
        return kwargs["sql"], {"dim_region"}

    monkeypatch.setattr(
        analysis_api,
        "validate_user_query_sql_or_raise",
        fake_validate,
    )
    unresolved = AnalysisTimeResolution(policy=None, status="unresolved")

    prepared = analysis_api._prepare_sql_for_execution(
        object(),
        object(),
        object(),
        SimpleNamespace(type="postgresql"),
        "SELECT 'fact_orders' AS source_name FROM dim_region",
        ["dim_region"],
        time_resolution=unresolved,
        schema_time_fields={"fact_orders": ("business_date",)},
        declared_time_fields=[],
        dialect="postgres",
    )

    assert "dim_region" in prepared
    assert len(validated) == 1

    with pytest.raises(AnalysisTimeSqlError):
        analysis_api._prepare_sql_for_execution(
            object(),
            object(),
            object(),
            SimpleNamespace(type="postgresql"),
            "SELECT * FROM fact_orders",
            ["fact_orders"],
            time_resolution=unresolved,
            schema_time_fields={"fact_orders": ("business_date",)},
            declared_time_fields=[],
            dialect="postgres",
        )

    assert len(validated) == 1


def test_prepare_sql_rejects_malformed_declared_time_fields_before_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validate_calls: list[bool] = []
    monkeypatch.setattr(
        analysis_api,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: validate_calls.append(True) or (kwargs["sql"], set()),
    )

    with pytest.raises(AnalysisTimeSqlError):
        analysis_api._prepare_sql_for_execution(
            object(),
            object(),
            object(),
            SimpleNamespace(type="postgresql"),
            "SELECT * FROM fact_orders",
            ["fact_orders"],
            time_resolution=_resolved_time(),
            schema_time_fields={"fact_orders": ("business_date",)},
            declared_time_fields=[None],
            dialect="postgres",
        )

    assert validate_calls == []
