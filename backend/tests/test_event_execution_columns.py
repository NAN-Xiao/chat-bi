"""Explicit SQL aliases survive the shared origin-column execution contract."""
from apps.datasource.crud.sql_engine_executor import _normalize_query_result

def test_origin_columns_do_not_invent_short_aliases_for_json_dimension_names():
    columns=["dt","adinfo.mediaSource","currentinfo.country","metric"]
    result=_normalize_query_result({"fields":columns,"data":[dict(zip(columns,[20261001,"Organic","CN",3]))]},True)
    assert result["fields"]==columns
    assert list(result["data"][0])==columns

def test_origin_columns_preserve_two_explicit_aliases_with_same_short_name():
    columns=["initial.country","current.country"]
    result=_normalize_query_result({"fields":columns,"data":[dict(zip(columns,["CN","US"]))]},True)
    assert result["fields"]==columns and result["data"]==[{"initial.country":"CN","current.country":"US"}]

def test_preview_does_not_reuse_results_from_previous_column_format(monkeypatch):
    from types import SimpleNamespace
    from apps.dashboard.crud import dashboard_service as service
    from collections import OrderedDict
    monkeypatch.setattr(service.settings,"DASHBOARD_BUSINESS_TIMEZONE","Asia/Shanghai")
    monkeypatch.setattr(service,"_DASHBOARD_SQL_PREVIEW_CACHE",OrderedDict())
    monkeypatch.setattr(service,"_dashboard_sql_preview_cache_ttl",lambda:60)
    previous=service.DashboardSqlPreviewCacheKey(tenant_id=1,user_id='2',datasource_id=7,
        fingerprint='d403b1351ea45c3b81ebdf010f75482d533c2fdf6ff3108b4a2fd40bb5a56d7e')
    service._dashboard_sql_preview_memory_set(previous,{"status":"success","fields":["value"],"data":[{"value":1}]})
    current=service._dashboard_sql_preview_cache_key(SimpleNamespace(id=2,tenant_id=1),7,"SELECT 1 AS value",None)
    assert service._dashboard_sql_preview_memory_get(current) is None
