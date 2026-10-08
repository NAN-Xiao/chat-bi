import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from apps.dashboard.api import dashboard_api as api
from apps.dashboard.crud import ai_sql_generator as generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest
from revenue_sql_fixture import config, context
from test_revenue_sql_graph import json_config_and_context


@pytest.mark.parametrize("entry", ["ai_sql_generate_api", "sql_compile_api"])
def test_existing_revenue_payload_uses_compiler_in_both_routes(monkeypatch, entry):
    monkeypatch.setattr(generator, "_node_collect_context", context)
    monkeypatch.setattr(generator, "MANUAL_CHART_GRAPH", generator._build_manual_chart_graph())
    monkeypatch.setattr(generator, "_create_dashboard_ai_sql_llm", lambda *a, **k: pytest.fail("收入接口不得调用模型"))
    async def receive(): await asyncio.Event().wait()
    response = asyncio.run(getattr(api, entry).__wrapped__(session=None, current_user=SimpleNamespace(id=1),
        request=DashboardAiSqlGenerateRequest(datasource=1, chart_type="table", context=config()),
        http_request=SimpleNamespace(receive=receive)))
    assert response.success, response.issues
    assert response.analysis_model == "revenue" and response.result_config["type"] == "revenue_cohort_table"


@pytest.mark.parametrize("entry", ["ai_sql_generate_api", "sql_compile_api"])
@pytest.mark.parametrize("ending,status", [("timeout", 504), ("disconnect", 499)])
def test_revenue_routes_share_compilation_timeout_and_cancellation(monkeypatch, entry, ending, status):
    monkeypatch.setattr(api, "SQL_COMPILATION_TIMEOUT_SECONDS", 0.02)
    async def run():
        stopped = asyncio.Event()
        async def compile(**kwargs):
            try: await asyncio.Event().wait()
            finally: stopped.set()
        async def receive():
            if ending == "disconnect": return {"type": "http.disconnect"}
            await asyncio.Event().wait()
        monkeypatch.setattr(api, "compile_dashboard_sql", compile)
        monkeypatch.setattr(api, "generate_dashboard_ai_sql", lambda **kw: pytest.fail("不能进入通用模型路径"))
        with pytest.raises(HTTPException) as error:
            await getattr(api, entry).__wrapped__(session=None, current_user=SimpleNamespace(id=1),
                request=DashboardAiSqlGenerateRequest(datasource=1, context=config()), http_request=SimpleNamespace(receive=receive))
        assert error.value.status_code == status and stopped.is_set()
    asyncio.run(run())


@pytest.mark.parametrize("entry", ["ai_sql_generate_api", "sql_compile_api"])
def test_datasource_permission_denies_before_revenue_compilation(monkeypatch, entry):
    from apps.system.schemas import permission
    user = SimpleNamespace(id=1)
    request_context = SimpleNamespace(state=SimpleNamespace(current_user=user))
    monkeypatch.setattr(permission.RequestContext, "get_request", lambda: request_context)
    monkeypatch.setattr(permission, "i18n", lambda r: lambda message: message)
    monkeypatch.setattr(permission, "_has_admin_permission", lambda u: False)
    async def deny(current_user, resource_type, resource, roles):
        assert resource_type == "ds" and resource == 7
        return False
    monkeypatch.setattr(permission, "check_project_permission", deny)
    monkeypatch.setattr(api, "compile_dashboard_sql", lambda **kw: pytest.fail("拒绝访问后不得编译"))
    with pytest.raises(HTTPException) as error:
        asyncio.run(getattr(api, entry)(session=None, current_user=user,
            request=DashboardAiSqlGenerateRequest(datasource=7, context=config()), http_request=request_context))
    assert error.value.status_code == 403


@pytest.mark.parametrize("entry", ["ai_sql_generate_api", "sql_compile_api"])
def test_json_metric_and_cost_work_without_client_semantic_type(monkeypatch, entry):
    conf, collector = json_config_and_context()
    monkeypatch.setattr(generator, "_node_collect_context", collector)
    monkeypatch.setattr(generator, "MANUAL_CHART_GRAPH", generator._build_manual_chart_graph())
    monkeypatch.setattr(generator, "_create_dashboard_ai_sql_llm", lambda *a, **k: pytest.fail("不得调用模型"))
    async def receive(): await asyncio.Event().wait()
    response = asyncio.run(getattr(api, entry).__wrapped__(session=None, current_user=SimpleNamespace(id=1),
        request=DashboardAiSqlGenerateRequest(datasource=1, chart_type="table", context=conf),
        http_request=SimpleNamespace(receive=receive)))
    assert response.success, response.issues
    assert "cost_value" in response.sql and "payload" in response.sql
