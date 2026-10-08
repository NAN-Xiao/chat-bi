import importlib.util
import sqlglot
import pytest
from event_sql_fixture import build, config, formula_config

def test_event_template_feature_exists():
    assert importlib.util.find_spec("apps.dashboard.crud.event_sql_compiler") is not None

@pytest.mark.parametrize("dialect",["postgres","mysql","starrocks","doris"])
@pytest.mark.parametrize("aggregation",["count","count_distinct","sum","avg","max","min"])
def test_templates_parse_and_preserve_output_contract(dialect,aggregation):
    from apps.dashboard.crud.event_sql_compiler import compile_event_sql
    p=build(config(aggregation,groups=True),dialect=dialect);sql=compile_event_sql(p)
    parsed=sqlglot.parse_one(sql.replace("{{dashboard_start_yyyymmdd}}","20260901").replace("{{dashboard_end_yyyymmdd}}","20260903"),read=dialect)
    assert tuple(parsed.named_selects)==p.required_columns
    assert not list(parsed.find_all(sqlglot.exp.Limit))
    assert compile_event_sql(p)==sql

def test_formula_rounds_only_after_independent_aggregation():
    from apps.dashboard.crud.event_sql_compiler import compile_event_sql
    sql=compile_event_sql(build(formula_config()))
    assert "NULLIF" in sql and "ROUND" in sql
    assert "FULL OUTER JOIN" not in sql
