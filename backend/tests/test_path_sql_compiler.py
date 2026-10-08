from dataclasses import replace
import pytest
import sqlglot
from path_compiler_fixture import plan, config
from apps.dashboard.crud.path_sql_compiler import compile_path_sql
from apps.dashboard.crud.path_sql_validation import path_result_contract_issues


@pytest.mark.parametrize("dialect", ["postgres", "mysql", "starrocks", "doris"])
def test_compiled_query_has_all_steps_and_guard(dialect):
    p=plan(dialect=dialect); sql=compile_path_sql(p)
    parsed=sqlglot.parse_one(sql.replace('{{dashboard_start_date}}',"'2026-09-01'").replace('{{dashboard_end_date}}',"'2026-09-28'"),read=dialect)
    assert set(parsed.named_selects)=={*p.required_columns,"__path_order_error"}
    assert "step_in_session <= 10" in sql
    assert "ORDER BY step_in_session ASC" in sql
    assert path_result_contract_issues(sql,p,compiled_sql=sql)==[]
    assert compile_path_sql(p)==sql


@pytest.mark.parametrize("dialect", ["postgres", "mysql", "starrocks", "doris"])
def test_compiler_passes_public_sql_safety_for_every_dialect(dialect):
    from apps.dashboard.crud.ai_sql_generator import validate_sql_for_generation
    validate_sql_for_generation(compile_path_sql(plan(dialect=dialect)), dialect)


@pytest.mark.parametrize("before,after", [(" > 1800", " >= 1800"), ("<= 10", "<= 2"),
    ("event_key = 'A'", "event_key = 'B'"), ("COUNT(*)", "COUNT(DISTINCT entity_id)"),
    ("ORDER BY step_in_session ASC", "ORDER BY event_time ASC"),
    ("dashboard_end_date", "dashboard_end_yyyymmdd"), ("__path_order_error", "ignored_guard")])
def test_mutated_compiled_contract_fails(before,after):
    p=plan(); sql=compile_path_sql(p)
    assert before in sql
    assert path_result_contract_issues(sql.replace(before,after),p,compiled_sql=sql)


def test_single_event_and_identical_configuration():
    c=config(); c["path"]["events"]=c["path"]["events"][:1]
    assert compile_path_sql(plan(c))
    assert compile_path_sql(plan())!=compile_path_sql(replace(plan(),session_gap_seconds=1))
