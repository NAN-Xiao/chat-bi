import copy

import pytest

from apps.dashboard.crud.interval_execution_contract import (
    attach_interval_contract, read_interval_contract, validate_interval_execution_result,
    validate_interval_execution_context,
)
from apps.dashboard.crud.interval_sql_compiler import compile_interval_sql, GUARD_COLUMN
from test_interval_sql_plan import plan


def signed():
    p = plan()
    return attach_interval_contract(compile_interval_sql(p), p, tenant_id=1, datasource_id=2, tracking_metadata={})


def test_signed_sql_allows_only_dashboard_bound_substitution():
    sql = signed()
    assert read_interval_contract(sql)["kind"] == "interval"
    rendered = sql.replace("{{dashboard_start_date}}", "DATE '2026-09-01'").replace("{{dashboard_end_date}}", "DATE '2026-09-03'")
    assert read_interval_contract(rendered)
    with pytest.raises(ValueError): read_interval_contract(rendered.replace("<= 90", "<= 91"))
    with pytest.raises(ValueError): read_interval_contract(sql[sql.index('*/') + 2:])


def test_clean_guard_is_removed_before_field_mapping():
    contract = read_interval_contract(signed())
    fields = [*contract["columns"], GUARD_COLUMN]
    result = {"fields": fields, "data": [{**dict.fromkeys(contract["columns"], 0), GUARD_COLUMN: 0}]}
    cleaned = validate_interval_execution_result(result, contract)
    assert cleaned["fields"] == contract["columns"] and GUARD_COLUMN not in cleaned["data"][0]
    assert cleaned["_interval_contract"]["guard_status"] == "passed"


@pytest.mark.parametrize("bad", [None, 1, 2, "0"])
def test_conflicting_or_malformed_guard_fails(bad):
    contract = read_interval_contract(signed())
    with pytest.raises(ValueError):
        validate_interval_execution_result({"fields": [*contract["columns"], GUARD_COLUMN], "data": [{GUARD_COLUMN: bad}]}, contract)


def test_missing_guard_is_not_empty_success():
    with pytest.raises(ValueError): validate_interval_execution_result({"fields": [], "data": []}, read_interval_contract(signed()))


def test_dst_naive_time_is_rejected_and_absolute_time_is_allowed():
    contract = read_interval_contract(signed())
    contract["naive_timezones"] = ["America/New_York"]
    with pytest.raises(ValueError, match="INTERVAL_TIME_AMBIGUOUS"):
        validate_interval_execution_context(contract, ("2026-03-08", "2026-03-09"))
    contract["naive_timezones"] = []
    validate_interval_execution_context(contract, ("2026-03-08", "2026-03-09"))


def test_dst_outside_actual_window_does_not_reject_valid_query():
    contract = read_interval_contract(signed())
    contract["naive_timezones"] = ["America/New_York"]
    validate_interval_execution_context(contract, ("2026-03-09", "2026-03-10"))


def test_result_limit_fails_explicitly_instead_of_truncating_calendar(monkeypatch):
    from common.core.config import settings
    monkeypatch.setattr(settings, "SHUZHI_QUERY_RESULT_MAX_ROWS", 2)
    contract = read_interval_contract(signed())
    result = {"fields": [*contract["columns"], GUARD_COLUMN],
              "data": [{**dict.fromkeys(contract["columns"], 0), GUARD_COLUMN: 0} for _ in range(3)]}
    with pytest.raises(ValueError, match="结果超过"):
        validate_interval_execution_result(result, contract)
