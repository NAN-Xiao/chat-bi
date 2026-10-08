import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from apps.dashboard.api import dashboard_api as api
from apps.dashboard.crud import ai_sql_generator as generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest
from apps.system.schemas.business_access import require_chatbi_business_user
from distribution_sql_fixture import config
from test_distribution_sql_graph import context


def test_dedicated_distribution_route_is_registered_with_business_auth():
    routes=[r for r in api.router.routes if isinstance(r,APIRoute) and r.path=="/dashboard/distribution/sql_compile"]
    assert len(routes)==1,"new distribution endpoint missing"
    assert require_chatbi_business_user in [d.call for d in routes[0].dependant.dependencies]


@pytest.mark.parametrize("model",["event","funnel","",None])
def test_dedicated_route_rejects_other_models_before_collecting(monkeypatch,model):
    assert hasattr(generator,"compile_distribution_dashboard_sql")
    monkeypatch.setattr(generator,"_node_collect_context",lambda *a:pytest.fail("wrong model must not read metadata"))
    with pytest.raises(HTTPException) as error:
        asyncio.run(generator.compile_distribution_dashboard_sql(None,None,DashboardAiSqlGenerateRequest(datasource=1,context={"analysisModel":model})))
    assert error.value.status_code==400


@pytest.mark.parametrize("entry",["distribution_sql_compile_api","ai_sql_generate_api","sql_compile_api"])
def test_existing_client_payload_works_through_all_routes(monkeypatch,entry):
    assert hasattr(api,entry)
    monkeypatch.setattr(generator,"_node_collect_context",context)
    monkeypatch.setattr(generator,"MANUAL_CHART_GRAPH",generator._build_manual_chart_graph())
    monkeypatch.setattr(generator,"_create_dashboard_ai_sql_llm",lambda *a,**kw:pytest.fail("no model"))
    async def receive(): await asyncio.Event().wait()
    result=asyncio.run(getattr(api,entry).__wrapped__(session=None,current_user=SimpleNamespace(id=1),
        request=DashboardAiSqlGenerateRequest(datasource=1,context=config()),http_request=SimpleNamespace(receive=receive)))
    assert result.success,result.issues
    assert result.analysis_model=="distribution" and result.chart_type=="table"


@pytest.mark.parametrize("entry",["distribution_sql_compile_api","ai_sql_generate_api"])
@pytest.mark.parametrize("ending,status",[("timeout",504),("disconnect",499)])
def test_new_and_existing_routes_share_compilation_budget_and_cancel(monkeypatch,entry,ending,status):
    assert hasattr(api,entry)
    monkeypatch.setattr(api,"SQL_COMPILATION_TIMEOUT_SECONDS",0.02)
    async def run():
        stopped=asyncio.Event()
        async def compile(**kw):
            try: await asyncio.Event().wait()
            finally: stopped.set()
        async def receive():
            if ending=="disconnect": return {"type":"http.disconnect"}
            await asyncio.Event().wait()
        monkeypatch.setattr(api,"compile_distribution_dashboard_sql",compile,raising=False)
        monkeypatch.setattr(api,"generate_dashboard_ai_sql",lambda **kw:pytest.fail("distribution must route before generic generation"))
        with pytest.raises(HTTPException) as error:
            await getattr(api,entry).__wrapped__(session=None,current_user=SimpleNamespace(id=1),
                request=DashboardAiSqlGenerateRequest(datasource=1,context=config()),http_request=SimpleNamespace(receive=receive))
        assert error.value.status_code==status and stopped.is_set()
    asyncio.run(run())


@pytest.mark.parametrize("entry",["distribution_sql_compile_api","ai_sql_generate_api","sql_compile_api"])
def test_all_http_entries_enforce_datasource_permission_before_compilation(monkeypatch,entry):
    from apps.system.schemas import permission
    user=SimpleNamespace(id=1)
    request_context=SimpleNamespace(state=SimpleNamespace(current_user=user))
    monkeypatch.setattr(permission.RequestContext,"get_request",lambda:request_context)
    monkeypatch.setattr(permission,"i18n",lambda r:lambda message:message)
    monkeypatch.setattr(permission,"_has_admin_permission",lambda u:False)
    async def deny(current_user,resource_type,resource,roles):
        assert current_user is user and resource_type=="ds" and resource==7
        return False
    monkeypatch.setattr(permission,"check_project_permission",deny)
    monkeypatch.setattr(api,"compile_distribution_dashboard_sql",lambda **kw:pytest.fail("denied request reached compiler"))
    with pytest.raises(HTTPException) as error:
        asyncio.run(getattr(api,entry)(session=None,current_user=user,
            request=DashboardAiSqlGenerateRequest(datasource=7,context=config()),http_request=request_context))
    assert error.value.status_code==403


@pytest.mark.parametrize("entry",["distribution_sql_compile_api","ai_sql_generate_api"])
@pytest.mark.parametrize("ending",["timeout","disconnect"])
def test_cancellation_drains_sync_metadata_before_request_session_closes(monkeypatch,entry,ending):
    import threading
    import time
    started,finished=threading.Event(),threading.Event()
    def collector(state):
        started.set()
        time.sleep(0.12)
        finished.set()
        return {}
    monkeypatch.setattr(generator,"_node_collect_context",collector)
    monkeypatch.setattr(generator,"_node_normalize_manual_config",lambda s:pytest.fail("cancelled compilation advanced to next node"))
    monkeypatch.setattr(generator,"MANUAL_CHART_GRAPH",generator._build_manual_chart_graph())
    monkeypatch.setattr(api,"SQL_COMPILATION_TIMEOUT_SECONDS",0.04)
    async def scenario():
        async def receive():
            if ending=="disconnect":
                while not started.is_set(): await asyncio.sleep(0.001)
                return {"type":"http.disconnect"}
            await asyncio.Event().wait()
        with pytest.raises(HTTPException) as error:
            await getattr(api,entry).__wrapped__(session=object(),current_user=SimpleNamespace(id=1),
                request=DashboardAiSqlGenerateRequest(datasource=1,context=config()),http_request=SimpleNamespace(receive=receive))
        assert error.value.status_code==(504 if ending=="timeout" else 499)
        assert finished.is_set()
    asyncio.run(scenario())


def test_registered_new_route_accepts_http_json_and_returns_current_client_schema(monkeypatch):
    import httpx
    from fastapi import FastAPI
    from apps.system.schemas import permission
    app=FastAPI()
    app.include_router(api.router,prefix="/api/v1")
    route=next(r for r in api.router.routes if r.path=="/dashboard/distribution/sql_compile")
    user=SimpleNamespace(id=1)
    for dep in route.dependant.dependencies:
        if dep.name=="current_user": app.dependency_overrides[dep.call]=lambda:user
        else: app.dependency_overrides[dep.call]=lambda:None
    monkeypatch.setattr(permission.RequestContext,"get_request",lambda:SimpleNamespace(state=SimpleNamespace(current_user=user)))
    monkeypatch.setattr(permission,"i18n",lambda r:lambda message:message)
    monkeypatch.setattr(permission,"_has_admin_permission",lambda u:False)
    async def allowed(*args): return True
    monkeypatch.setattr(permission,"check_project_permission",allowed)
    monkeypatch.setattr(generator,"_node_collect_context",context)
    monkeypatch.setattr(generator,"MANUAL_CHART_GRAPH",generator._build_manual_chart_graph())
    monkeypatch.setattr(generator,"_create_dashboard_ai_sql_llm",lambda *a,**kw:pytest.fail("HTTP request called LLM"))
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://fixture") as client:
            response=await client.post("/api/v1/dashboard/distribution/sql_compile",json={"datasource":1,"context":config()})
            assert response.status_code==200,response.text
            payload=response.json()
            assert payload["success"] and payload["analysis_model"]=="distribution" and payload["chart_type"]=="table"
            assert payload["sql"].startswith("WITH ") and payload["result_config"]["entity_count_field"]=="entity_count"
    asyncio.run(scenario())
