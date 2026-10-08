from types import SimpleNamespace
from apps.dashboard.crud import attribution_execution_contract as contract_module
from apps.datasource.crud import sql_engine_executor as executor
from apps.dashboard.crud.attribution_sql_compiler import compile_attribution_sql, GUARD_COLUMN
from attribution_compiler_fixture import FIELDS, TRACKING, plan

def test_public_mysql_execution_forwards_explicit_timezone_control_and_strips_guard(monkeypatch):
    fields = {**FIELDS,'occurred_at':{'type':'bigint','field_role':'event_time','extra_properties':{'encoding':'epoch_milliseconds'}}}
    p = plan(metadata_fields={'events':fields},dialect='mysql',engine='mysql')
    sql = contract_module.attach_attribution_contract(compile_attribution_sql(p),p,tenant_id=11,datasource_id=12,tracking_metadata=TRACKING)
    sql = sql.replace('{{dashboard_start_date}}',"'2026-09-01'").replace('{{dashboard_end_date}}',"'2026-09-28'")
    contract = contract_module.read_attribution_contract(sql)
    datasource = SimpleNamespace(id=12,type='mysql')
    session = SimpleNamespace(get=lambda *a:datasource)
    monkeypatch.setattr(executor,'has_datasource_access',lambda *a:True)
    monkeypatch.setattr(executor,'prepare_query_sql',lambda **kw:(kw['sql'],{'events'}))
    monkeypatch.setattr(contract_module,'validate_attribution_workspace_contract',lambda *a,**kw:contract)
    def database(ds,sql,**kw):
        assert kw['interval_timezone_verify_only'] is True
        assert kw['interval_timezones'] == ('Asia/Shanghai',)
        return {'fields':[*contract['columns'],GUARD_COLUMN],'data':[{**dict.fromkeys(contract['columns'],0),GUARD_COLUMN:0}]}
    monkeypatch.setattr(executor,'_unsafe_exec_sql_after_validation',database)
    result = executor.execute_user_query(session,SimpleNamespace(id=1),12,sql,origin_column=True)
    assert result['status'] == 'success', result
    assert result['fields'] == contract['columns']
    assert GUARD_COLUMN not in result['data'][0]
