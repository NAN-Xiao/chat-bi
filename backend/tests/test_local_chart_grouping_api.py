import asyncio
from types import SimpleNamespace

from apps.dashboard.api.dashboard_api import local_grouping_plan_api
from apps.dashboard.models.dashboard_model import DashboardLocalGroupingRequest


def test_local_plan_api_does_not_resolve_datasource_or_execute_query(monkeypatch):
    from apps.dashboard.crud import dashboard_service

    def forbidden(*args, **kwargs):
        raise AssertionError('本地汇总规则解析不得读取数据源或执行SQL')

    monkeypatch.setattr(dashboard_service, 'preview_sql', forbidden)
    monkeypatch.setattr(dashboard_service, 'resolve_chart_execution_datasource', forbidden)
    monkeypatch.setattr(dashboard_service, '_execute_dashboard_chart_sql', forbidden)
    result = asyncio.run(local_grouping_plan_api(SimpleNamespace(), DashboardLocalGroupingRequest(
        sql='SELECT day,region,SUM(amount) AS value FROM facts GROUP BY day,region',
        dialect='sqlite',
    )))
    assert result['dimensions'] == ['day', 'region']
    assert result['metrics']['value']['aggregation'] == 'sum'
