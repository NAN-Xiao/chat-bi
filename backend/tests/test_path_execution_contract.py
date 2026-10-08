import copy

import pytest

from apps.dashboard.crud.path_execution_contract import (
    attach_path_contract, read_path_contract, validate_path_execution_result,
    validate_path_execution_context,
)
from apps.dashboard.crud.path_sql_compiler import compile_path_sql, PATH_GUARD_COLUMN as GUARD_COLUMN
from path_compiler_fixture import plan


def signed():
    p = plan()
    return attach_path_contract(compile_path_sql(p), p, tenant_id=1, datasource_id=2, tracking_metadata={})


def test_signed_sql_allows_only_dashboard_bound_substitution():
    sql = signed()
    assert read_path_contract(sql)["kind"] == "path"
    rendered = sql.replace("{{dashboard_start_date}}", "DATE '2026-09-01'").replace("{{dashboard_end_date}}", "DATE '2026-09-03'")
    assert read_path_contract(rendered)
    with pytest.raises(ValueError): read_path_contract(rendered.replace("> 1800", "> 1801"))
    with pytest.raises(ValueError): read_path_contract(sql[sql.index('*/') + 2:])


def test_clean_guard_is_removed_before_field_mapping():
    contract = read_path_contract(signed())
    fields = [*contract["columns"], GUARD_COLUMN]
    result = {"fields": fields, "data": [{**dict.fromkeys(contract["columns"], 0), GUARD_COLUMN: 0}]}
    cleaned = validate_path_execution_result(result, contract)
    assert cleaned["fields"] == contract["columns"] and GUARD_COLUMN not in cleaned["data"][0]
    assert cleaned["_path_contract"]["guard_status"] == "passed"


@pytest.mark.parametrize("bad", [None, 1, 2, "0"])
def test_conflicting_or_malformed_guard_fails(bad):
    contract = read_path_contract(signed())
    with pytest.raises(ValueError):
        validate_path_execution_result({"fields": [*contract["columns"], GUARD_COLUMN], "data": [{GUARD_COLUMN: bad}]}, contract)


def test_missing_guard_is_not_empty_success():
    with pytest.raises(ValueError): validate_path_execution_result({"fields": [], "data": []}, read_path_contract(signed()))


def test_dst_naive_time_is_rejected_and_absolute_time_is_allowed():
    contract = read_path_contract(signed())
    contract["naive_timezones"] = ["America/New_York"]
    with pytest.raises(ValueError, match="PATH_TIME_AMBIGUOUS"):
        validate_path_execution_context(contract, ("2026-03-08", "2026-03-09"))
    contract["naive_timezones"] = []
    validate_path_execution_context(contract, ("2026-03-08", "2026-03-09"))


def test_dst_outside_actual_window_does_not_reject_valid_query():
    contract = read_path_contract(signed())
    contract["naive_timezones"] = ["America/New_York"]
    validate_path_execution_context(contract, ("2026-03-09", "2026-03-10"))


def test_result_limit_fails_explicitly_instead_of_truncating_calendar(monkeypatch):
    from common.core.config import settings
    monkeypatch.setattr(settings, "SHUZHI_QUERY_RESULT_MAX_ROWS", 2)
    contract = read_path_contract(signed())
    result = {"fields": [*contract["columns"], GUARD_COLUMN],
              "data": [{**dict.fromkeys(contract["columns"], 0), GUARD_COLUMN: 0} for _ in range(3)]}
    with pytest.raises(ValueError, match="结果超过"):
        validate_path_execution_result(result, contract)


@pytest.mark.parametrize("start", ["-DATE '2026-09-01'", "ABS(DATE '2026-09-01')"])
def test_signed_date_slot_cannot_hide_an_expression(start):
    from apps.dashboard.crud.path_execution_contract import path_date_range
    sql=signed().replace("{{dashboard_start_date}}",start).replace("{{dashboard_end_date}}","DATE '2026-09-03'")
    with pytest.raises(ValueError): path_date_range(sql,read_path_contract(sql))
