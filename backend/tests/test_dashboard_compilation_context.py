"""Exercise the real collector and context service: no bypass of context preparation."""
from types import SimpleNamespace

import pytest

from apps.dashboard.crud import ai_sql_generator as generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest
from apps.datasource.crud import sql_engine
from apps.ai_model.embedding import EmbeddingModelCache
from test_property_sql_graph import request as property_request
from test_retention_sql_graph import config


@pytest.mark.parametrize("model", ["property", "interval", "retention", "funnel", "path", "revenue", "attribution"])
def test_real_collect_context_has_no_ai_dependencies(monkeypatch, model):
    datasource = SimpleNamespace(id=1, name="测试源", type="postgresql")
    class Session:
        def get(self, *args): return datasource
    def forbidden(*args, **kwargs):
        pytest.fail("deterministic configuration must not construct model context or call embedding/LLM")
    monkeypatch.setattr(generator, "require_current_tenant_id", lambda user: 2001)
    monkeypatch.setattr(generator, "get_tracking_config", lambda *a, **kw: {"enabled": False})
    monkeypatch.setattr(generator, "_dashboard_config_prompt", forbidden)
    monkeypatch.setattr(generator, "_create_dashboard_ai_sql_llm", forbidden)
    monkeypatch.setattr(EmbeddingModelCache, "get_model", forbidden)
    monkeypatch.setattr(sql_engine, "find_data_skills", forbidden)
    monkeypatch.setattr(sql_engine, "find_tracking_prompt_context", forbidden)
    monkeypatch.setattr(sql_engine, "has_datasource_access", lambda *args: True)
    def schema(**kwargs):
        assert "embedding" not in kwargs
        return "# Table: events\n[(uid:varchar)]", ["events"]
    monkeypatch.setattr(sql_engine, "get_ai_table_schema", forbidden)
    monkeypatch.setattr(sql_engine, "get_compilation_table_schema", schema, raising=False)
    req = property_request() if model == "property" else DashboardAiSqlGenerateRequest(datasource=1, context={**config(), "analysisModel": model})
    state = generator._node_collect_context({"session": Session(), "current_user": SimpleNamespace(id=1001, tenant_id=2001),
                                            "request": req, "graph_trace": []})
    assert state["allowed_fields_by_table"] == {"events": {"uid"}}
    assert state["tracking_metadata"] == {"enabled": False}
    assert state["data_skill"] == "" and state["skill_model_id"] is None
