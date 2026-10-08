"""Dispatch server-owned query contracts without changing existing protocols."""
from apps.dashboard.crud import interval_execution_contract as interval
from apps.dashboard.crud import path_execution_contract as path
from apps.dashboard.crud import attribution_execution_contract as attribution
from apps.dashboard.crud import ranking_execution_contract as ranking


def read_analysis_contract(sql):
    contracts = [c for c in (interval.read_interval_contract(sql), path.read_path_contract(sql), attribution.read_attribution_contract(sql), ranking.read_ranking_contract(sql)) if c]
    if len(contracts) > 1:
        raise ValueError("一条查询不能包含多个分析执行协议。")
    return contracts[0] if contracts else None


def require_analysis_contract(sql, expected=None):
    contract = read_analysis_contract(sql)
    if expected is not None and contract != expected:
        raise ValueError("分析图表的执行协议与 SQL 不一致，请重新生成。")
    return contract


def validate_analysis_workspace_contract(session, current_user, datasource_id, sql, expected=None):
    contract = require_analysis_contract(sql, expected)
    if not contract:
        return None
    if contract['kind'] == 'ranking':
        return ranking.validate_ranking_workspace_contract(session, current_user, datasource_id, sql, expected)
    if contract['kind'] == 'attribution':
        return attribution.validate_attribution_workspace_contract(session,current_user,datasource_id,sql,expected)
    validate = (path.validate_path_workspace_contract if contract["kind"] == "path"
                else interval.validate_interval_workspace_contract)
    return validate(session, current_user, datasource_id, sql, expected)


def validate_analysis_execution_result(result, contract):
    if not contract:
        return result
    if contract['kind'] == 'ranking':
        return ranking.validate_ranking_execution_result(result, contract)
    if contract['kind'] == 'attribution':
        return attribution.validate_attribution_execution_result(result,contract)
    validate = (path.validate_path_execution_result if contract["kind"] == "path"
                else interval.validate_interval_execution_result)
    return validate(result, contract)
