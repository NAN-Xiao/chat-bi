import pytest
from apps.dashboard.crud.ranking_execution_contract import attach_ranking_contract, read_ranking_contract, validate_ranking_execution_result
from apps.dashboard.crud.ranking_sql_compiler import compile_ranking_sql, GUARD_COLUMN
from apps.dashboard.crud.ranking_sql_validation import ranking_result_contract_issues
from apps.dashboard.crud.analysis_execution_contract import read_analysis_contract, validate_analysis_execution_result
from ranking_sql_fixture import plan


def signed():
    p = plan()
    return attach_ranking_contract(compile_ranking_sql(p),p,tenant_id=99,datasource_id=1,tracking_metadata={}),p


def test_signed_sql_supports_parameter_substitution_but_not_semantic_changes():
    sql,p = signed(); contract = read_ranking_contract(sql)
    assert read_analysis_contract(sql) == contract
    assert ranking_result_contract_issues(sql,p) == []
    materialized = sql.replace("{{dashboard_start_yyyymmdd}}","20260901").replace("{{dashboard_end_yyyymmdd}}","20260928")
    assert read_ranking_contract(materialized) == contract
    for broken in (sql.replace("DESC","ASC"),sql.replace("'visit'","'other'"),sql.split("\n",1)[1]):
        with pytest.raises(ValueError): read_ranking_contract(broken)
        assert ranking_result_contract_issues(broken,p)


def test_every_execution_surface_strips_guard_and_rejects_conflicts():
    sql,p = signed(); contract = read_ranking_contract(sql)
    row = dict(zip(p.required_columns,[1,"A",2,10,2,"one"]))
    result = {"status":"success","fields":[*p.required_columns,GUARD_COLUMN],"data":[{**row,GUARD_COLUMN:0}]}
    assert validate_analysis_execution_result(result,contract)["data"] == [row]
    result["data"][0][GUARD_COLUMN] = 1
    with pytest.raises(ValueError,match="RANKING_PROPERTY_CONFLICT"): validate_analysis_execution_result(result,contract)
    result["data"][0][GUARD_COLUMN] = None
    with pytest.raises(ValueError): validate_ranking_execution_result(result,contract)


def test_missing_guard_cannot_be_accepted():
    sql,p = signed()
    with pytest.raises(ValueError): validate_ranking_execution_result({"status":"success","fields":list(p.required_columns),"data":[]},read_ranking_contract(sql))


@pytest.mark.parametrize("dialect", ["postgres","mysql","starrocks","doris"])
@pytest.mark.parametrize("parameter", ["date","timestamp"])
def test_workspace_accepts_date_literals_rendered_by_dashboard(monkeypatch,dialect,parameter):
    from types import SimpleNamespace
    from apps.dashboard.crud.dashboard_date_filter import _sql_date_literal, _sql_timestamp_literal
    from apps.dashboard.crud.ranking_execution_contract import validate_ranking_workspace_contract
    from apps.system.crud import tracking_config
    from apps.system.schemas import access_context
    from ranking_sql_fixture import config,FIELDS
    conf = config(); conf["time"]["dateParameterType"] = parameter
    fields = {**FIELDS,"day":{"type":"date" if parameter == "date" else "datetime","extra_properties":{"timezone":"Asia/Shanghai"}}}
    p = plan(conf,fields=fields,dialect=dialect)
    sql = attach_ranking_contract(compile_ranking_sql(p),p,tenant_id=99,datasource_id=1,tracking_metadata={})
    render = _sql_date_literal if parameter == "date" else _sql_timestamp_literal
    for token,value in zip(p.parameter_tokens,["2026-09-02","2026-09-30"]):
        sql = sql.replace(token,render(value if parameter == "date" else value+" 00:00:00",dialect))
    monkeypatch.setattr(tracking_config,"get_tracking_config",lambda *a,**k:{})
    monkeypatch.setattr(access_context,"require_current_tenant_id",lambda u:99)
    assert validate_ranking_workspace_contract(None,SimpleNamespace(id=1),1,sql)["kind"] == "ranking"


def test_cache_requires_guard_evidence_and_invalidates_failure(monkeypatch):
    from apps.dashboard.crud import dashboard_service as service
    sql,p = signed(); contract = read_ranking_contract(sql)
    key = service.DashboardSqlPreviewCacheKey(99,"ranking-test",1,"ranking-cache",ranking_contract=contract)
    monkeypatch.setattr(service,"_dashboard_sql_preview_redis_client",lambda:None)
    monkeypatch.setattr(service,"_dashboard_sql_preview_cache_ttl",lambda:60)
    row = dict.fromkeys(p.required_columns,1)
    good = validate_ranking_execution_result({"status":"success","fields":[*p.required_columns,GUARD_COLUMN],"data":[{**row,GUARD_COLUMN:0}]},contract)
    service._dashboard_sql_preview_cache_set(key,good)
    assert service._dashboard_sql_preview_cache_get(key)["data"] == [row]
    assert service._dashboard_sql_preview_cache_get(key,allow_expired=True) is None
    service._dashboard_sql_preview_cache_set(key,{"status":"failed"})
    assert service._dashboard_sql_preview_cache_get(key) is None
    good.pop("_ranking_contract")
    service._dashboard_sql_preview_cache_set(key,good)
    assert service._dashboard_sql_preview_cache_get(key) is None
