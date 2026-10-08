"""Every deterministic model owns the same compilation lifetime on both routes."""
import asyncio
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from apps.dashboard.api import dashboard_api as api
from apps.dashboard.crud import ai_sql_generator as generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest

@pytest.mark.parametrize('model', sorted(generator.DETERMINISTIC_SQL_MODELS))
def test_legacy_route_uses_compiler_timeout_for_every_deterministic_model(monkeypatch, model):
    monkeypatch.setattr(api, 'SQL_COMPILATION_TIMEOUT_SECONDS', 0.01)
    async def scenario():
        stopped = asyncio.Event()
        async def compiler(**kwargs):
            try: await asyncio.Event().wait()
            finally: stopped.set()
        async def receive(): await asyncio.Event().wait()
        for name in ('compile_dashboard_sql', 'compile_distribution_dashboard_sql', 'compile_path_dashboard_sql'):
            monkeypatch.setattr(api, name, compiler)
        monkeypatch.setattr(api, 'generate_dashboard_ai_sql', lambda **kw: pytest.fail('确定性模型不能进入 LLM 生命周期'))
        with pytest.raises(HTTPException) as error:
            await api.ai_sql_generate_api.__wrapped__(session=None, current_user=SimpleNamespace(id=1),
                request=DashboardAiSqlGenerateRequest(datasource=1, context={'analysisModel': model}),
                http_request=SimpleNamespace(receive=receive))
        assert error.value.status_code == 504 and stopped.is_set()
    asyncio.run(scenario())

@pytest.mark.parametrize('model', sorted(generator.DETERMINISTIC_SQL_MODELS))
def test_direct_generation_service_dispatches_all_deterministic_models_to_compiler(monkeypatch, model):
    async def compiled(*a, **kw): return 'compiled'
    monkeypatch.setattr(generator, 'compile_dashboard_sql', compiled)
    monkeypatch.setattr(generator, '_execute_manual_chart_graph', lambda *a: pytest.fail('绕过了编译生命周期'))
    result = asyncio.run(generator.generate_dashboard_ai_sql(None, SimpleNamespace(id=1),
        DashboardAiSqlGenerateRequest(datasource=1, context={'analysisModel':model})))
    assert result == 'compiled'

@pytest.mark.parametrize('model', sorted(generator.DETERMINISTIC_SQL_MODELS))
def test_direct_compiler_always_has_a_compilation_deadline(monkeypatch, model):
    async def execute(*args):
        run=generator.current_generation_run()
        assert run is not None
        assert run.deadline-run.started_at == pytest.approx(60)
        return 'compiled'
    monkeypatch.setattr(generator, '_execute_manual_chart_graph', execute)
    assert asyncio.run(generator.compile_dashboard_sql(None, SimpleNamespace(id=1),
        DashboardAiSqlGenerateRequest(datasource=1, context={'analysisModel':model}))) == 'compiled'
