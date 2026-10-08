from types import SimpleNamespace
import pytest
from apps.db.db import check_sql_read
from apps.datasource.crud import sql_engine_executor as executor
from apps.dashboard.crud import ranking_execution_contract as contracts
from apps.dashboard.crud.ranking_sql_compiler import GUARD_COLUMN
from test_ranking_execution_contract import signed


@pytest.mark.parametrize("conflict",[False,True])
def test_public_execution_preserves_evidence_or_returns_explicit_failure(monkeypatch,conflict):
    sql,p = signed()
    sql = sql.replace("{{dashboard_start_yyyymmdd}}","20260902").replace("{{dashboard_end_yyyymmdd}}","20260929")
    contract = contracts.read_ranking_contract(sql)
    ds = SimpleNamespace(id=1,type="pg")
    monkeypatch.setattr(executor,"has_datasource_access",lambda *a:True)
    def prepare(**kwargs):
        ok,message = check_sql_read(kwargs["sql"],ds)
        assert ok,message
        return kwargs["sql"],{"events"}
    monkeypatch.setattr(executor,"prepare_query_sql",prepare)
    monkeypatch.setattr(contracts,"validate_ranking_workspace_contract",lambda *a,**k:contract)
    monkeypatch.setattr(executor,"_execute_after_validation",lambda **kw:{"fields":[*p.required_columns,GUARD_COLUMN],
        "data":[{**dict.fromkeys(p.required_columns,1),GUARD_COLUMN:int(conflict)}]})
    result = executor.execute_user_query(SimpleNamespace(get=lambda *a:ds),SimpleNamespace(id=1),1,sql,origin_column=True)
    if conflict:
        assert result["status"] == "failed"
        assert "RANKING_PROPERTY_CONFLICT" in result["message"]
    else:
        assert result["status"] == "success",result
        assert result["_ranking_contract"]["guard_status"] == "passed"
        assert GUARD_COLUMN not in result["fields"]
