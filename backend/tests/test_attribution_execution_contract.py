import pytest
from attribution_compiler_fixture import plan, TRACKING
from apps.dashboard.crud.attribution_sql_compiler import compile_attribution_sql

def test_contract_binds_sql_metadata_and_preserves_resolved_date_parameters():
    from apps.dashboard.crud.attribution_execution_contract import attach_attribution_contract, read_attribution_contract
    p = plan(); sql = attach_attribution_contract(compile_attribution_sql(p), p, tenant_id=11,datasource_id=12,tracking_metadata=TRACKING)
    contract = read_attribution_contract(sql)
    assert contract['kind'] == 'attribution' and contract['tenant_id'] == 11
    resolved = sql.replace('{{dashboard_start_date}}',"'2026-09-01'").replace('{{dashboard_end_date}}',"'2026-09-28'")
    assert read_attribution_contract(resolved) == contract
    with pytest.raises(ValueError): read_attribution_contract(sql.replace('touch_time <= t.target_time','touch_time >= t.target_time'))
    with pytest.raises(ValueError): read_attribution_contract(compile_attribution_sql(p))

def test_dispatcher_recognizes_attribution_contract():
    from apps.dashboard.crud.attribution_execution_contract import attach_attribution_contract
    from apps.dashboard.crud.analysis_execution_contract import read_analysis_contract, validate_analysis_execution_result
    p = plan(); sql = attach_attribution_contract(compile_attribution_sql(p),p,tenant_id=11,datasource_id=12,tracking_metadata=TRACKING)
    contract = read_analysis_contract(sql)
    assert contract['kind'] == 'attribution'
    with pytest.raises(ValueError): validate_analysis_execution_result({'fields':['wrong'],'data':[]},contract)
