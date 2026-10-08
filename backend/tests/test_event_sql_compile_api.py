import asyncio
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from apps.dashboard.api import dashboard_api as api
from apps.dashboard.crud import ai_sql_generator as g
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest
from event_sql_fixture import config, context

@pytest.mark.parametrize("entry",["ai_sql_generate_api","sql_compile_api"])
@pytest.mark.parametrize("default_model",[False,True])
def test_old_and_compilation_routes_share_zero_model_payload(monkeypatch,entry,default_model):
    monkeypatch.setattr(g,"_node_collect_context",context);monkeypatch.setattr(g,"MANUAL_CHART_GRAPH",g._build_manual_chart_graph())
    monkeypatch.setattr(g,"_create_dashboard_ai_sql_llm",lambda *a,**k:pytest.fail("旧事件请求不能调用模型"))
    async def receive():await asyncio.Event().wait()
    c=config()
    if default_model:c.pop("analysisModel")
    r=asyncio.run(getattr(api,entry).__wrapped__(session=None,current_user=SimpleNamespace(id=1),request=DashboardAiSqlGenerateRequest(datasource=1,context=c,chart_type="table"),http_request=SimpleNamespace(receive=receive)))
    assert r.success,r.issues

@pytest.mark.parametrize("entry",["ai_sql_generate_api","sql_compile_api"])
@pytest.mark.parametrize("ending,status",[("timeout",504),("disconnect",499)])
def test_event_compilation_lifetime_cancels_on_timeout_and_disconnect(monkeypatch,entry,ending,status):
    monkeypatch.setattr(api,"SQL_COMPILATION_TIMEOUT_SECONDS",0.02)
    async def check():
        stopped=asyncio.Event()
        async def compile(**kwargs):
            try:await asyncio.Event().wait()
            finally:stopped.set()
        async def receive():
            if ending=="disconnect":return {"type":"http.disconnect"}
            await asyncio.Event().wait()
        monkeypatch.setattr(api,"compile_dashboard_sql",compile)
        with pytest.raises(HTTPException) as error:
            await getattr(api,entry).__wrapped__(session=None,current_user=SimpleNamespace(id=1),request=DashboardAiSqlGenerateRequest(datasource=1,context=config()),http_request=SimpleNamespace(receive=receive))
        assert error.value.status_code==status and stopped.is_set()
    asyncio.run(check())

def test_unknown_model_is_rejected_instead_of_event_fallback():
    c=config();c["analysisModel"]="typo"
    with pytest.raises(HTTPException) as e:asyncio.run(g.compile_dashboard_sql(None,SimpleNamespace(id=1),DashboardAiSqlGenerateRequest(datasource=1,context=c)))
    assert e.value.status_code==400
