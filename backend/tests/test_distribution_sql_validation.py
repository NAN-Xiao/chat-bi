import pytest

from distribution_sql_fixture import config, field, module, plan, property_config, simultaneous


@pytest.mark.parametrize("aggregation",["count","median","variance"])
def test_population_and_complete_compiler_contract(aggregation):
    c=config() if aggregation=="count" else property_config(aggregation)
    c["groups"]=[field("category")]
    p=plan(simultaneous(c,"count_distinct","tag"))
    sql=module("distribution_sql_compiler").compile_distribution_sql(p)
    assert module("distribution_sql_validation").distribution_result_contract_issues(sql,p)==[]


@pytest.mark.parametrize("before,after",[("'A'","'B'"),("COUNT(*) OVER","SUM(1) OVER"),
    ("{{dashboard_end_yyyymmdd}}","{{dashboard_start_yyyymmdd}}"),("100.0","1.0"),
    ("AS entity_count","AS wrong_count"),("IS NOT NULL","IS NULL")])
def test_mutations_of_authorized_plan_are_rejected(before,after):
    p=plan(); sql=module("distribution_sql_compiler").compile_distribution_sql(p)
    assert before in sql
    assert module("distribution_sql_validation").distribution_result_contract_issues(sql.replace(before,after),p)
