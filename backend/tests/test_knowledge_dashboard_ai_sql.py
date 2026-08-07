"""Knowledge context integration for the dashboard SQL graph."""

from __future__ import annotations

from types import SimpleNamespace

from apps.dashboard.crud import ai_sql_generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest


def test_dashboard_context_is_built_after_normalization(monkeypatch):
    request = DashboardAiSqlGenerateRequest(
        datasource=10,
        intent="收入趋势",
        title="区域收入",
        chart_type="line",
        context={"metrics": [{"field": "orders.amount", "aggregation": "sum"}]},
    )
    trace = []
    build_calls = []

    monkeypatch.setattr(ai_sql_generator.settings, "KNOWLEDGE_RUNTIME_CONTEXT_ENABLED", True)
    monkeypatch.setattr(ai_sql_generator, "require_current_tenant_id", lambda _user: 2)
    monkeypatch.setattr(ai_sql_generator, "get_tracking_config", lambda *args, **kwargs: SimpleNamespace(
        enabled=False,
        datasource_id=10,
        default_event_table=None,
    ))
    monkeypatch.setattr(
        ai_sql_generator,
        "_dashboard_event_scope",
        lambda *args, **kwargs: {"status": "general", "table_list": None},
    )

    datasource = SimpleNamespace(id=10, name="业务库", type="postgresql", type_name="PostgreSQL")

    class _Session:
        def get(self, model, identifier):
            return datasource

    def build(**kwargs):
        build_calls.append(kwargs)
        trace.append(kwargs["question"])
        return SimpleNamespace(
            datasource=datasource,
            schema="schema",
            sql_dialect="postgres",
            allowed_tables=["orders"],
            data_skill="",
            tracking_config="",
            skill_model_id=None,
            semantic=None,
        )

    monkeypatch.setattr(ai_sql_generator.BusinessSqlContextService, "build", staticmethod(build))
    collected = ai_sql_generator._node_collect_context(
        {"session": _Session(), "current_user": SimpleNamespace(id=8, tenant_id=2), "request": request, "graph_trace": []}
    )
    state = {
        **collected,
        "request": request,
        "session": _Session(),
        "current_user": SimpleNamespace(id=8, tenant_id=2),
    }
    normalized = ai_sql_generator._node_normalize_manual_config(state)
    built = ai_sql_generator._node_build_business_sql_context({**state, **normalized})

    assert trace
    assert "收入趋势" in trace[0]
    assert "orders.amount" in trace[0]
    assert build_calls[0]["surface"] == "dashboard_ai_sql"
    assert built["allowed_tables"] == ["orders"]


def test_dashboard_response_exposes_safe_knowledge_citations():
    citation = SimpleNamespace(
        chunk_id=7,
        knowledge_base_id=20,
        version_id=21,
        section_path="收入",
        score=0.9,
        visibility_scope="ADMIN_PUBLIC",
    )
    semantic = SimpleNamespace(
        knowledge_citations=[citation],
        knowledge_version_hash="version-1",
        warnings=["检索告警"],
    )
    context = SimpleNamespace(
        semantic=semantic,
        semantic_context="tracking\n\nskill\n\nknowledge",
        datasource_id=10,
        snapshot_metadata=lambda: {
            "permission_version": "permission-1",
            "schema_hash": "schema-1",
            "selected_skills": [{"id": "7", "selection_mode": "AUTOMATIC"}],
            "knowledge_version_hash": "version-1",
            "knowledge_citations": [{"knowledge_base_id": "20", "version_id": "21"}],
            "warnings": ["检索告警"],
        },
    )
    result = ai_sql_generator._node_finalize_response(
        {
            "business_sql_context": context,
            "request": DashboardAiSqlGenerateRequest(datasource=10, data_skill_id=7),
            "datasource": SimpleNamespace(id=10, name="业务库"),
            "graph_trace": [],
        }
    )["response"]

    assert result.knowledge_citations[0]["chunk_id"] == "7"
    assert result.knowledge_version_hash == "version-1"
    assert result.retrieval_warnings == ["检索告警"]
    assert "content" not in result.knowledge_citations[0]
    assert result.context_snapshot["surface"] == "dashboard_ai_sql"
    assert result.context_snapshot["business_context"]["permission_version"] == "permission-1"
    assert result.context_snapshot["business_context"]["selected_skills"]
