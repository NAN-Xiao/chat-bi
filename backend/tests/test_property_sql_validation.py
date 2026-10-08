import pytest

from apps.dashboard.crud.property_sql_compiler import compile_property_sql
from apps.dashboard.crud.property_sql_validation import property_result_contract_issues
from test_property_sql_plan import config, field, plan


def test_canonical_query_passes_and_final_column_mutations_fail():
    p = plan()
    sql = compile_property_sql(p)
    assert property_result_contract_issues(sql, p) == []
    assert property_result_contract_issues(sql + '; SELECT 1', p)
    assert property_result_contract_issues(sql.replace('LEFT JOIN aggregated', 'INNER JOIN aggregated'), p)
    assert property_result_contract_issues(sql.replace('COUNT(DISTINCT "subject")', 'COUNT("subject")'), p)
    assert property_result_contract_issues(sql.replace('d.calendar_date AS "property_date"', 'a."property_date" AS "property_date"'), p)


def test_second_metric_field_cannot_borrow_first_metric_validation():
    conf = config()
    conf["metrics"].append({"field": field("region"), "aggregation": "count_distinct"})
    p = plan(conf)
    sql = compile_property_sql(p)
    assert property_result_contract_issues(sql.replace('COUNT(DISTINCT "region")', 'COUNT(DISTINCT "subject")'), p)


@pytest.mark.parametrize("change", [
    lambda s: s.replace('"amount" > 5', '"amount" > 0'),
    lambda s: s.replace('"day" <= {{dashboard_end_yyyymmdd}}', 'TRUE'),
    lambda s: s.replace('AS "property_metric_1"\nFROM dashboard_dates', 'AS "wrong"\nFROM dashboard_dates'),
])
def test_predicates_and_output_are_verified(change):
    conf = config()
    conf["filters"] = {"logic": "and", "rules": [{"field": field("amount"), "operator": "gt", "value": "5"}]}
    p = plan(conf)
    sql = compile_property_sql(p)
    assert change(sql) != sql
    assert property_result_contract_issues(change(sql), p)
