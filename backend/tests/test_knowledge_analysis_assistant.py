"""Unified semantic context integration for report interpretation."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from apps.analysis_assistant.api import analysis_assistant as analysis_api
from apps.datasource.models.datasource import CoreDatasource


async def _collect_body(response) -> str:
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)
    return b"".join(item if isinstance(item, bytes) else str(item).encode() for item in chunks).decode()


def test_report_interpretation_uses_business_context_when_runtime_enabled(monkeypatch):
    datasource = CoreDatasource(id=10, name="业务库", type="postgresql", type_name="PostgreSQL")
    citation = SimpleNamespace(
        chunk_id=7,
        knowledge_base_id=20,
        version_id=21,
        section_path="收入",
        score=0.9,
        visibility_scope="ADMIN_PUBLIC",
    )
    semantic = SimpleNamespace(
        semantic_text="tracking\n\nskill\n\nknowledge",
        knowledge_citations=[citation],
        knowledge_version_hash="version-1",
        warnings=["检索告警"],
    )
    business_context = SimpleNamespace(
        semantic=semantic,
        semantic_context=semantic.semantic_text,
        data_skill="skill",
        tracking_config="tracking",
        snapshot_metadata=lambda: {
            "knowledge_citations": [{"chunk_id": "7"}],
            "knowledge_version_hash": "version-1",
            "retrieval_warnings": ["检索告警"],
        },
    )

    monkeypatch.setattr(analysis_api.settings, "KNOWLEDGE_RUNTIME_CONTEXT_ENABLED", True)
    monkeypatch.setattr(analysis_api, "_report_interpretation_preflight", lambda *args, **kwargs: None)
    monkeypatch.setattr(analysis_api, "_tenant_rate_limit_response", lambda *args, **kwargs: _none_async())
    monkeypatch.setattr(analysis_api, "_get_report_interpretation_datasource", lambda *args, **kwargs: datasource)
    build_calls = []

    def build_context(**kwargs):
        build_calls.append(kwargs)
        return business_context

    monkeypatch.setattr(analysis_api.BusinessSqlContextService, "build", staticmethod(build_context))
    monkeypatch.setattr(analysis_api, "_create_llm", lambda *args, **kwargs: _llm_pair())
    monkeypatch.setattr(analysis_api, "record_tenant_usage_detached", lambda **kwargs: None)
    monkeypatch.setattr(analysis_api, "_current_tenant_id", lambda user: 2)

    request = analysis_api.AnalysisAssistantRequest(
        datasource_id=10,
        context='{"title":"收入趋势","data":[{"value":999}]}',
        messages=[analysis_api.AnalysisAssistantMessage(role="user", content="解读收入")],
    )
    response = asyncio.run(
        analysis_api.report_interpretation(request, SimpleNamespace(id=8, tenant_id=2), SimpleNamespace())
    )
    body = asyncio.run(_collect_body(response))

    assert '"type":"context_snapshot"' in body
    assert '"type":"context_warning"' in body
    assert '"type":"knowledge_citations"' in body
    assert '"chunk_id":"7"' in body
    assert '999' not in analysis_api._report_retrieval_query(request)
    assert len(build_calls) == 1
    assert (
        build_calls[0]["target_scope"]
        == analysis_api.CustomPromptTargetScopeEnum.REPORT_INTERPRETATION
    )
    assert build_calls[0]["include_all_target_scopes"] is False


async def _none_async():
    return None


async def _llm_pair():
    class _Llm:
        def stream(self, _messages):
            yield SimpleNamespace(content="### 数据概览\n有数据")

    return _Llm(), SimpleNamespace(model_id=1, model_name="test")
