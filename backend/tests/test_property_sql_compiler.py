import copy
import sqlite3
from datetime import date, datetime

import pytest
import sqlglot

from apps.dashboard.crud.property_sql_compiler import compile_property_sql
from test_property_sql_plan import config, field, plan


ROWS = [(20260901, "u1", "A", 10), (20260901, "u1", "A", 20),
        (20260901, "u2", "B", None), (20260903, "u3", None, 5)]


def execute(conf=None, rows=ROWS, transform=lambda sql: sql):
    sql = compile_property_sql(plan(conf))
    sql = sql.replace("{{dashboard_start_yyyymmdd}}", "20260901").replace("{{dashboard_end_yyyymmdd}}", "20260903")
    sql = transform(sql)
    # Test aggregates on SQLite; real-engine date/JSON execution is a separate gate.
    sql = sqlglot.transpile(sql, read="postgres", write="sqlite")[0]
    with sqlite3.connect(":memory:") as db:
        # PostgreSQL DATE arithmetic uses integral days. SQLite has no DATE
        # type, so emulate that scalar algebra only; this is not engine QA.
        db.create_function("STR_TO_DATE", 2, lambda value, fmt: datetime.strptime(value, fmt).date().toordinal())
        db.create_function("DATE", 1, lambda value: value)
        db.execute("CREATE TABLE records(day INTEGER, subject TEXT, region TEXT, amount NUMERIC, payload TEXT)")
        db.executemany("INSERT INTO records(day,subject,region,amount) VALUES(?,?,?,?)", rows)
        rows = db.execute(sql).fetchall()
        if plan(conf).date_expression:
            rows = [(date.fromordinal(row[0]).isoformat(), *row[1:]) for row in rows]
        return rows


def rule(name, op, value=None):
    return {"field": field(name), "operator": op, "value": value}


def filters(*rules, logic="and"):
    return {"logic": logic, "rules": list(rules)}


def test_six_aggregations_and_none_grain():
    conf = config()
    conf["time"]["grain"] = "none"
    conf["metrics"] = [{"field": field("amount"), "aggregation": a} for a in ("count", "count_distinct", "sum", "avg", "min", "max")]
    assert execute(conf) == [(3, 3, 35, 35 / 3, 5, 20)]
    assert execute(conf, []) == [(0, 0, None, None, None, None)]


def test_distinct_and_metric_filters_use_correct_grain():
    conf = config()
    conf["time"]["grain"] = "none"
    conf["metrics"].append({"field": field("subject"), "aggregation": "count_distinct",
                            "filters": filters(rule("amount", "gt", "15"))})
    assert execute(conf) == [(3, 1)]
    conf["filters"] = filters(rule("region", "eq", "A"))
    assert execute(conf) == [(1, 1)]


def test_literal_contains_and_nested_filters():
    conf = config()
    conf["time"]["grain"] = "none"
    conf["filters"] = filters({"type": "group", "logic": "or", "children": [rule("region", "contains", "%_"), rule("region", "eq", "中文'")]}, rule("amount", "gt", "0"))
    rows = [(20260901, "a", "%_", 1), (20260901, "b", "anything", 1), (20260901, "c", "中文'", 1)]
    assert execute(conf, rows) == [(2,)]


def test_day_scaffold_and_null_metric_semantics():
    conf = config()
    conf["metrics"].append({"field": field("amount"), "aggregation": "sum"})
    result = execute(conf)
    assert [row[1:] for row in result] == [(2, 30), (0, None), (1, 5)]
    assert [str(row[0])[:10] for row in result] == ["2026-09-01", "2026-09-02", "2026-09-03"]


def test_null_groups_and_filtered_dimension_domain():
    conf = config()
    conf["groups"] = [field("region")]
    result = execute(conf)
    assert len(result) == 9
    assert any(str(row[0]).startswith("2026-09-03") and row[1:] == (None, 1) for row in result)
    conf["metrics"][0]["filters"] = filters(rule("amount", "gt", "15"))
    assert {row[1] for row in execute(conf)} == {"A"}
    assert execute(conf, []) == []


def test_audiences_overlap_and_empty_audience_is_preserved():
    conf = config()
    conf["property"] = {"groupMode": "audience", "audiences": [
        {"name": "全部", "filters": {}},
        {"name": "地区A", "filters": filters(rule("region", "eq", "A"))},
        {"name": "空人群", "filters": filters(rule("region", "eq", "missing"))}]}
    rows = execute(conf)
    assert len(rows) == 9
    assert [row[2] for row in rows[:3]] == [2, 1, 0]
    assert [row[2] for row in rows[3:6]] == [0, 0, 0]
    assert len(execute(conf, [])) == 9


@pytest.mark.parametrize("dialect", ["postgres", "mysql"])
@pytest.mark.parametrize("grain", ["day", "week", "month", "none"])
def test_output_is_stable_and_dialect_parseable(dialect, grain):
    conf = config()
    conf["time"]["grain"] = grain
    original = copy.deepcopy(conf)
    compiled = plan(conf, dialect=dialect)
    sql = compile_property_sql(compiled)
    assert sql == compile_property_sql(compiled)
    assert conf == original
    parsed = sqlglot.parse_one(sql.replace("{{dashboard_start_yyyymmdd}}", "20260901").replace("{{dashboard_end_yyyymmdd}}", "20260903"), read=dialect)
    assert tuple(parsed.named_selects) == compiled.required_columns
    assert "WITH RECURSIVE" not in sql


def test_duplicate_audience_name_rejected():
    conf = config()
    conf["property"] = {"groupMode": "audience", "audiences": [{"name": "same"}, {"name": "same"}]}
    from apps.dashboard.crud.property_sql_plan import PropertyConfigurationError
    with pytest.raises(PropertyConfigurationError):
        plan(conf)


def test_row_permissions_cover_dimension_domain_and_audience_branches():
    from types import SimpleNamespace
    from apps.datasource.crud.sql_permission import apply_row_permission_filters

    def restrict(sql):
        return apply_row_permission_filters(sql, SimpleNamespace(type="pg"),
                                            [{"table": "records", "filter": "region = 'A'"}])

    conf = config()
    conf["groups"] = [field("region")]
    assert {row[1] for row in execute(conf, transform=restrict)} == {"A"}
    conf["groups"] = []
    conf["property"] = {"groupMode": "audience", "audiences": [
        {"name": "全部", "filters": {}}, {"name": "B", "filters": filters(rule("region", "eq", "B"))}]}
    rows = execute(conf, transform=restrict)
    assert rows[0][2] == 1
    assert all(row[2] == 0 for row in rows if row[1] == "B")
