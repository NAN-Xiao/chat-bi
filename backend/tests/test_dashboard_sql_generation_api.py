"""The SQL endpoint owns the generation lifetime without changing datasource permission input."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.routing import APIRoute
from starlette.middleware.base import BaseHTTPMiddleware

from apps.dashboard.api import dashboard_api
from apps.dashboard.crud import sql_generation_lifecycle as lifecycle
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest
from apps.system.schemas.business_access import require_chatbi_business_user


def test_compilation_has_its_own_authenticated_endpoint():
    routes = [r for r in dashboard_api.router.routes if isinstance(r, APIRoute) and r.path == "/dashboard/sql_compile"]
    assert len(routes) == 1
    assert require_chatbi_business_user in [d.call for d in routes[0].dependant.dependencies]


@pytest.mark.parametrize("model", ["heatmap", "unknown"])
def test_compilation_never_accepts_a_generative_model(monkeypatch, model):
    from apps.dashboard.crud import ai_sql_generator as generator
    from unittest.mock import AsyncMock
    graph = AsyncMock(side_effect=AssertionError("must reject before running graph"))
    monkeypatch.setattr(generator.MANUAL_CHART_GRAPH, "ainvoke", graph)
    request = DashboardAiSqlGenerateRequest(datasource=7, context={"analysisModel": model})
    with pytest.raises(HTTPException) as error:
        asyncio.run(generator.compile_dashboard_sql(session=None, current_user=SimpleNamespace(id=1), request=request))
    assert error.value.status_code == 400


@pytest.mark.parametrize("ending, status", [("timeout", 504), ("disconnect", 499)])
@pytest.mark.parametrize("model", ["retention", "funnel"])
def test_compilation_cancels_without_using_llm_budget(monkeypatch, ending, status, model):
    monkeypatch.setattr(dashboard_api, "SQL_COMPILATION_TIMEOUT_SECONDS", 0.02, raising=False)
    async def scenario():
        stopped = asyncio.Event()
        async def compile(**kwargs):
            try: await asyncio.Event().wait()
            finally: stopped.set()
        async def receive():
            if ending == "disconnect": return {"type": "http.disconnect"}
            await asyncio.Event().wait()
        monkeypatch.setattr(dashboard_api, "compile_dashboard_sql", compile, raising=False)
        with pytest.raises(HTTPException) as error:
            await dashboard_api.sql_compile_api.__wrapped__(session=None, current_user=SimpleNamespace(id=1),
                request=DashboardAiSqlGenerateRequest(datasource=7, context={"analysisModel": model}),
                http_request=SimpleNamespace(receive=receive))
        assert error.value.status_code == status and stopped.is_set()
    asyncio.run(scenario())


@pytest.mark.parametrize("ending", ["timeout", "disconnect"])
@pytest.mark.parametrize("model", ["retention", "funnel"])
def test_compilation_does_not_release_request_session_while_sync_collector_runs(monkeypatch, ending, model):
    import threading
    import time
    from apps.dashboard.crud import ai_sql_generator as generator
    finished = threading.Event()
    started = threading.Event()
    def collector(state):
        started.set()
        time.sleep(0.15)
        finished.set()
        return {}
    def next_node(state):
        pytest.fail("cancelled compilation must not continue after metadata collection")
    monkeypatch.setattr(generator, "_node_collect_context", collector)
    monkeypatch.setattr(generator, "_node_normalize_manual_config", next_node)
    monkeypatch.setattr(generator, "MANUAL_CHART_GRAPH", generator._build_manual_chart_graph())
    monkeypatch.setattr(dashboard_api, "SQL_COMPILATION_TIMEOUT_SECONDS", 0.05)
    async def scenario():
        async def receive():
            if ending == "disconnect":
                while not started.is_set(): await asyncio.sleep(0.001)
                return {"type": "http.disconnect"}
            await asyncio.Event().wait()
        with pytest.raises(HTTPException) as error:
            await dashboard_api.sql_compile_api.__wrapped__(session=object(), current_user=SimpleNamespace(id=1),
                request=DashboardAiSqlGenerateRequest(datasource=7, context={"analysisModel": model}),
                http_request=SimpleNamespace(receive=receive))
        assert error.value.status_code == (504 if ending == "timeout" else 499)
        assert finished.is_set(), "request Session must remain alive until the synchronous collector exits"
    asyncio.run(scenario())


def test_limits_endpoint_returns_configured_budget_under_business_auth(monkeypatch):
    monkeypatch.setattr(lifecycle.settings, "LLM_TASK_MAX_WAIT_SECONDS", 73)
    routes = [route for route in dashboard_api.router.routes if isinstance(route, APIRoute)
              and route.path == "/dashboard/ai_sql_generation_limits"]
    assert len(routes) == 1, "The frontend needs the server's actual generation budget"
    route = routes[0]
    assert require_chatbi_business_user in [dependency.call for dependency in route.dependant.dependencies]
    result = asyncio.run(route.endpoint(current_user=SimpleNamespace(id=1)))
    assert result == {"total_timeout_seconds": 73}


@pytest.mark.parametrize("ending, status", [("timeout", 504), ("disconnect", 499)])
def test_api_cancels_generator_when_request_ends(monkeypatch, ending, status):
    monkeypatch.setattr(lifecycle.settings, "LLM_TASK_MAX_WAIT_SECONDS", 0.02)

    async def scenario():
        stopped = asyncio.Event()

        async def generate(**kwargs):
            assert kwargs["request"].datasource == 7
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        async def receive():
            if ending == "disconnect":
                return {"type": "http.disconnect"}
            await asyncio.Event().wait()

        monkeypatch.setattr(dashboard_api, "generate_dashboard_ai_sql", generate)
        with pytest.raises(HTTPException) as error:
            await dashboard_api.ai_sql_generate_api.__wrapped__(
                session=None, current_user=SimpleNamespace(id=1),
                request=DashboardAiSqlGenerateRequest(datasource=7, context={"analysisModel": "heatmap"}),
                http_request=SimpleNamespace(receive=receive),
            )
        assert error.value.status_code == status
        assert stopped.is_set()

    asyncio.run(scenario())


@pytest.mark.parametrize("middleware_count", [0, 1, 3])
def test_real_asgi_disconnect_stops_generation_through_body_caching_middleware(monkeypatch, middleware_count):
    """Cancellation must work with the same BaseHTTPMiddleware receive wrappers used by the app."""
    monkeypatch.setattr(lifecycle.settings, "LLM_TASK_MAX_WAIT_SECONDS", 60)

    async def scenario():
        started, stopped = asyncio.Event(), asyncio.Event()
        messages = asyncio.Queue()
        messages.put_nowait({"type": "http.request", "body": b'{"datasource":7,"context":{"analysisModel":"heatmap"}}', "more_body": False})

        async def generate(**kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        monkeypatch.setattr(dashboard_api, "generate_dashboard_ai_sql", generate)
        app = FastAPI()

        async def dispatch(request, call_next):
            await request.body()
            return await call_next(request)

        for _ in range(middleware_count):
            app.add_middleware(BaseHTTPMiddleware, dispatch=dispatch)

        @app.post("/generate")
        async def endpoint(request: Request, payload: DashboardAiSqlGenerateRequest):
            return await dashboard_api.ai_sql_generate_api.__wrapped__(
                session=None, current_user=SimpleNamespace(id=1), request=payload, http_request=request,
            )

        async def send(_message):
            pass

        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
            "scheme": "http", "path": "/generate", "raw_path": b"/generate", "query_string": b"",
            "headers": [(b"content-type", b"application/json")], "client": ("127.0.0.1", 1),
            "server": ("test", 80), "root_path": "",
        }
        app_task = asyncio.create_task(app(scope, messages.get, send))
        await asyncio.wait_for(started.wait(), timeout=1)
        messages.put_nowait({"type": "http.disconnect"})
        try:
            await asyncio.wait_for(stopped.wait(), timeout=0.4)
            client_disconnect_cancelled_generation = True
        except TimeoutError:
            client_disconnect_cancelled_generation = False
        finally:
            app_task.cancel()
            await asyncio.gather(app_task, return_exceptions=True)
        assert client_disconnect_cancelled_generation, "ASGI disconnect did not stop SQL generation"

    asyncio.run(scenario())
