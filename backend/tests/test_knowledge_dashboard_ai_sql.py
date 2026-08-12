"""Knowledge context integration for the dashboard SQL graph."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from apps.dashboard.crud import ai_sql_generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest


def test_dashboard_sql_generation_preserves_http_errors(monkeypatch):
    request = DashboardAiSqlGenerateRequest(datasource=10)

    class _Graph:
        async def ainvoke(self, _state):
            raise HTTPException(status_code=403, detail="当前用户无权访问项目 10")

    monkeypatch.setattr(ai_sql_generator, "MANUAL_CHART_GRAPH", _Graph())

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            ai_sql_generator.generate_dashboard_ai_sql(
                session=SimpleNamespace(),
                current_user=SimpleNamespace(id=8),
                request=request,
            )
        )

    assert error.value.status_code == 403
    assert error.value.detail == "当前用户无权访问项目 10"


@pytest.mark.parametrize(
    ("semantic", "expected_knowledge_context"),
    [
        (None, ""),
        (
            SimpleNamespace(
                knowledge_context=(
                    '<retrieved-knowledge priority="reference-only" id="chunk-7">'
                    "统计分析口径说明"
                    "</retrieved-knowledge>"
                ),
                structured_context="结构化知识不得进入 knowledge-context",
            ),
            '<retrieved-knowledge priority="reference-only" id="chunk-7">'
            "统计分析口径说明"
            "</retrieved-knowledge>",
        ),
    ],
    ids=["semantic-disabled", "retrieved-knowledge"],
)
def test_dashboard_context_is_built_after_normalization(
    monkeypatch,
    semantic,
    expected_knowledge_context,
):
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
            data_skill="<Data-Skills>收入执行规则</Data-Skills>",
            tracking_config="<Tracking>订单事件映射</Tracking>",
            skill_model_id=None,
            semantic=semantic,
            semantic_context="扁平语义上下文不得进入 knowledge-context",
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
    assert built["data_skill"] == "<Data-Skills>收入执行规则</Data-Skills>"
    assert built["tracking_config"] == "<Tracking>订单事件映射</Tracking>"
    assert built["knowledge_context"] == expected_knowledge_context
    assert "结构化知识不得进入 knowledge-context" not in built["knowledge_context"]
    assert "扁平语义上下文不得进入 knowledge-context" not in built["knowledge_context"]


def test_dashboard_response_exposes_safe_knowledge_citations():
    citation = SimpleNamespace(
        chunk_id=7,
        knowledge_base_id=20,
        version_id=21,
        section_path="收入",
        score=0.9,
        content="不得返回的知识正文",
        visibility_scope="ADMIN_PUBLIC",
    )
    semantic = SimpleNamespace(
        knowledge_citations=[citation],
        knowledge_version_hash="version-1",
        warnings=["检索告警"],
    )
    context = SimpleNamespace(
        semantic=semantic,
        data_skill="skill",
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
    assert "不得返回的知识正文" not in str(result.knowledge_citations)
    assert result.context_snapshot["surface"] == "dashboard_ai_sql"
    assert result.context_snapshot["business_context"]["permission_version"] == "permission-1"
    assert result.context_snapshot["business_context"]["selected_skills"]
    assert result.context_snapshot["data_skill"]["content_chars"] == len("skill")
