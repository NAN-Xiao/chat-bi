"""Executable examples and contract checks for the supplied attribution document."""
import sqlite3

import pytest
import sqlglot
from sqlglot import exp

from apps.dashboard.crud import ai_sql_generator as generator
from attribution_sql_fixture import attribution_sql
from test_dashboard_attribution_validation import config
from test_dashboard_ai_sql_generator import _attribution_request


def execute(sql, records):
    def sqlite_interval(node):
        if isinstance(node, exp.Sub) and isinstance(node.expression, exp.Interval):
            interval = node.expression
            return exp.Anonymous(this="DATETIME", expressions=[
                node.this.copy(), exp.Literal.string(f"-{interval.this.this} {interval.args['unit'].name}"),
            ])
        return node

    query = sqlglot.parse_one(sql, read="mysql").transform(sqlite_interval).sql(dialect="sqlite")
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE events(event_id INT, actor TEXT, occurred_at TEXT, kind TEXT, channel TEXT, amount REAL, session_id TEXT)")
        db.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)", records)
        return [dict(row) for row in db.execute(query)]


def document_sql(method, include_direct=True, **kwargs):
    return attribution_sql(method=method, mode="duration", include_direct=include_direct,
                           target_value="amount", window_value=3, window_unit="HOUR", **kwargs).replace(
        "kind IN ('email', 'search')", "kind IN ('A', 'B', 'C')")


DOCUMENT_EVENTS = [
    (1, "u1", "2026-09-01 07:00:00", "conversion", "east", 648, "s1"),
    (2, "u1", "2026-09-01 09:00:00", "A", "entry_a", None, "s1"),
    (3, "u1", "2026-09-01 10:30:00", "B", "entry_b", None, "s1"),
    (4, "u1", "2026-09-01 11:30:00", "conversion", "east", 648, "s1"),
    (5, "u1", "2026-09-01 12:00:00", "C", "entry_c", None, "s1"),
    (6, "u1", "2026-09-01 13:30:00", "conversion", "east", 648, "s1"),
]


@pytest.mark.parametrize("method,values,effective", [
    ("first", [648, 648, 0], [1, 1, 0]),
    ("last", [0, 648, 648], [0, 1, 1]),
    ("linear", [324, 648, 324], [1, 1, 1]),
])
@pytest.mark.parametrize("include_direct", [True, False])
def test_document_contributions_and_unique_touches(method, values, effective, include_direct):
    sql = document_sql(method, include_direct)
    normalized = config(method, "duration")
    normalized["attribution"]["window"] = {"mode": "duration", "value": 3, "unit": "hour"}
    assert generator._attribution_sql_result_issues(sql, normalized, sql_dialect="mysql") == []
    rows = {row["attribution_event"]: row for row in execute(sql, DOCUMENT_EVENTS)}
    for event, value, count in zip("ABC", values, effective):
        assert rows[event]["attributed_value"] == value
        assert rows[event]["total_touch_count"] == 1
        assert rows[event]["effective_touch_count"] == count
        assert rows[event]["effective_entity_count"] == count
        assert rows[event]["effective_touch_rate"] == count * 100
        assert rows[event]["contribution_rate"] == pytest.approx(value / (1944 if include_direct else 1296) * 100)
    assert ("direct" in rows) is include_direct
    if include_direct:
        assert rows["direct"]["attributed_value"] == 648
        assert rows["direct"]["effective_touch_count"] == rows["direct"]["effective_entity_count"] == 0
        assert rows["direct"]["total_touch_count"] == 0
        assert rows["direct"]["effective_touch_rate"] is None


def test_duplicate_touch_timestamps_and_multiple_targets_do_not_collapse_events():
    records = [
        (1, "u", "2026-09-01 01:00:00", "email", "web", None, None),
        (2, "u", "2026-09-01 01:00:00", "email", "web", None, None),
        (3, "u", "2026-09-01 02:00:00", "conversion", "web", 20, None),
        (4, "u", "2026-09-01 02:00:00", "conversion", "web", 30, None),
        (5, "other", "2026-09-01 01:00:00", "email", "web", None, None),
    ]
    row, = execute(attribution_sql(target_value="amount"), records)
    assert row["target_count"] == 2
    assert row["attributed_value"] == 50
    assert row["total_touch_count"] == 3
    assert row["effective_touch_count"] == 2
    assert row["effective_entity_count"] == 1


def test_custom_scan_expands_before_start_and_preserves_unselected_touches():
    records = [
        (1, "u", "2026-08-31 23:59:00", "email", "web", None, None),
        (2, "u", "2026-09-01 00:01:00", "conversion", "web", 20, None),
        (3, "u", "2026-08-20 00:01:00", "search", "web", None, None),
        (4, "other", "2026-08-31 23:59:00", "search", "web", None, None),
    ]
    rows = execute(attribution_sql(mode="duration", start="2026-09-01 00:00:00", end="2026-09-02 00:00:00"), records)
    assert {row["attribution_event"]: (row["total_touch_count"], row["attributed_value"]) for row in rows} == {
        "email": (1, 1), "search": (1, 0),
    }


def test_related_properties_require_equal_non_null_values():
    records = [
        (1, "u", "2026-09-01 01:00:00", "email", "web", None, "session_a"),
        (2, "u", "2026-09-01 01:30:00", "search", "web", None, "session_b"),
        (3, "u", "2026-09-01 02:00:00", "conversion", "web", 20, "session_a"),
        (4, "v", "2026-09-01 01:00:00", "email", "web", None, None),
        (5, "v", "2026-09-01 02:00:00", "conversion", "web", 30, None),
    ]
    rows = {row["attribution_event"]: row for row in execute(attribution_sql(related=True, target_value="amount"), records)}
    assert rows["email"]["attributed_value"] == 20
    assert rows["search"]["attributed_value"] == 0
    assert rows["direct"]["attributed_value"] == 30


@pytest.mark.parametrize("mutation,issue", [
    (lambda sql: sql.replace("COUNT(DISTINCT touch_id) AS effective_touch_count", "COUNT(*) AS effective_touch_count"), "effective_touch_count"),
    (lambda sql: sql.replace("COUNT(DISTINCT entity_id) AS effective_entity_count", "COUNT(DISTINCT target_id) AS effective_entity_count"), "effective_entity_count"),
    (lambda sql: sql.replace("FROM touches \n", "FROM matched \n"), "总触发数"),
    (lambda sql: sql.replace("event_id AS touch_id", "CONCAT(actor, occurred_at) AS touch_id"), "touch_id"),
    (lambda sql: sql.replace("effective_touch_count * 100.0 / NULLIF(total_touch_count, 0)", "1"), "有效触发率"),
    (lambda sql: sql.replace("touches_total s LEFT JOIN", "touches_total s JOIN"), "零贡献行"),
    (lambda sql: sql.replace("SELECT t.target_id, tc.entity_id,", "SELECT t.target_id, t.entity_id,"), "触点侧"),
    (lambda sql: sql.replace("t.entity_id = tc.entity_id", "1 = 1"), "跨主体"),
])
def test_rejects_incorrect_touch_statistics(mutation, issue):
    sql = mutation(attribution_sql())
    assert sql != attribution_sql()
    assert any(issue in text for text in generator._attribution_sql_result_issues(sql, config(), sql_dialect="mysql"))


def test_contribution_denominator_uses_only_target_groups():
    normalized = config()
    normalized["groups"] = [{"attributionSide": "touch"}]
    issues = generator._attribution_sql_result_issues(attribution_sql(grouped=True), normalized, sql_dialect="mysql")
    assert any("分母只能按目标" in issue for issue in issues)


def test_sum_target_value_cannot_silently_become_event_count():
    normalized = config()
    normalized["attribution"]["targetMetric"] = {"aggregation": "sum", "metricField": {"field": "amount"}}
    assert any("目标数值属性" in issue for issue in generator._attribution_sql_result_issues(attribution_sql(), normalized, sql_dialect="mysql"))
    assert generator._attribution_sql_result_issues(attribution_sql(target_value="amount"), normalized, sql_dialect="mysql") == []


def validate(request):
    normalized = generator._normalize_manual_config(request)
    result = generator._deterministic_validate_manual_config(request, normalized, generator._build_formula_ir(normalized),
        allowed_tables=["event"], allowed_fields_by_table={"event": {"user_id", "event_name", "dt", "amount", "session_id"}})
    return normalized, result


@pytest.mark.parametrize("aggregation", ["count_distinct", "avg", "min", "max"])
def test_non_additive_target_metrics_are_rejected_without_substitution(aggregation):
    normalized, result = validate(_attribution_request(targetMetric={"aggregation": aggregation, "metricField": {"table": "event", "field": "amount"}}))
    assert normalized["attribution"]["targetMetric"]["aggregation"] == aggregation
    assert not result.success
    assert any("逐事件分配" in issue for issue in result.issues)


def test_group_side_and_related_property_permissions_survive_normalization():
    request = _attribution_request()
    request.context["groups"] = [{"table": "event", "field": "session_id", "attributionSide": "target"}]
    related = {"enabled": True, "targetProperty": {"table": "event", "field": "session_id"},
               "touchProperty": {"table": "event", "field": "session_id"}}
    request.context["attribution"]["events"][0]["relatedProperty"] = related
    normalized, result = validate(request)
    assert result.success, result.issues
    assert normalized["groups"][0]["attributionSide"] == "target"
    assert normalized["attribution"]["events"][0]["relatedProperty"] == related
    related["touchProperty"] = {"table": "private_events", "field": "secret"}
    _, result = validate(request)
    assert not result.success
    related["touchProperty"] = None
    _, result = validate(request)
    assert not result.success
    assert any("请选择字段" in issue for issue in result.issues)


def test_existing_group_keeps_target_group_semantics_without_new_ui_config():
    request = _attribution_request()
    request.context["groups"] = [{"table": "event", "field": "session_id"}]
    _, result = validate(request)
    assert result.success, result.issues
