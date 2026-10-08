from types import SimpleNamespace

import pytest

from apps.db.db import check_sql_read
from apps.datasource.crud import sql_engine_executor as executor
from apps.dashboard.crud import path_execution_contract as contract_module
from apps.dashboard.crud import dashboard_service as service
from test_path_execution_contract import signed


def test_signed_sql_passes_shared_read_only_validation():
    ok, message = check_sql_read(signed(), SimpleNamespace(type="pg"))
    assert ok, message


@pytest.mark.parametrize("sql", ["/* ordinary */ DELETE FROM events", "-- ordinary\nDROP TABLE events", "/*!50000 DELETE FROM events */ SELECT 1", "WITH gone AS (DELETE FROM events RETURNING *) SELECT * FROM gone", "/* ordinary */ SELECT 1; DELETE FROM events"])
def test_comments_never_hide_writes(sql):
    assert not check_sql_read(sql, SimpleNamespace(type="mysql"))[0]


def test_public_execute_preserves_server_evidence_and_enables_cache(monkeypatch):
    sql = signed().replace("{{dashboard_start_date}}", "DATE '2026-09-01'").replace("{{dashboard_end_date}}", "DATE '2026-09-03'")
    contract = contract_module.read_path_contract(sql)
    datasource = SimpleNamespace(id=2, type="pg")
    session = SimpleNamespace(get=lambda *a: datasource)
    monkeypatch.setattr(executor, "has_datasource_access", lambda *a: True)
    def prepare(**kwargs):
        ok, message = check_sql_read(kwargs["sql"], datasource)
        assert ok, message
        return kwargs["sql"], {"events"}
    monkeypatch.setattr(executor, "prepare_query_sql", prepare)
    monkeypatch.setattr(contract_module, "validate_path_workspace_contract", lambda *a, **k: contract)
    monkeypatch.setattr(executor, "_execute_after_validation", lambda **k: {"fields": [*contract["columns"], "__path_order_error"], "data": [{**dict.fromkeys(contract["columns"], 0), "__path_order_error": 0}]})
    result = executor.execute_user_query(session, SimpleNamespace(id=1), 2, sql, origin_column=True)
    assert result["status"] == "success", result
    assert result["_path_contract"]["guard_status"] == "passed"
    key = service.DashboardSqlPreviewCacheKey(1, "path-test", 2, "unit-test", path_contract=contract)
    monkeypatch.setattr(service, "_dashboard_sql_preview_redis_client", lambda: None)
    monkeypatch.setattr(service, "_dashboard_sql_preview_cache_ttl", lambda: 60)
    service._dashboard_sql_preview_cache_set(key, result)
    cached = service._dashboard_sql_preview_cache_get(key)
    assert cached and cached["fields"] == contract["columns"]
    service._dashboard_sql_preview_cache_set(key, {"status": "failed"})
    assert service._dashboard_sql_preview_cache_get(key) is None
