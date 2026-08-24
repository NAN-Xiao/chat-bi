"""Tests for the permission-first semantic context contract."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

from apps.datasource.crud import semantic_context
from apps.datasource.crud.permission_scope import PermissionScopeSnapshot
from apps.knowledge_base.retrieval import KnowledgeCitation, KnowledgeRetrievalResult


class _Session:
    def get(self, model, identifier):
        return SimpleNamespace(id=identifier, type="postgresql", type_name="PostgreSQL")


def _snapshot() -> PermissionScopeSnapshot:
    return PermissionScopeSnapshot(
        tenant_id=2,
        user_id=8,
        datasource_id=10,
        permission_version="permission-1",
        schema_hash="schema-1",
        allowed_object_keys=frozenset(),
        denied_object_keys=frozenset(),
        row_constraints_hash="rows-1",
    )


class _Retrieval:
    def __init__(self, trace):
        self.trace = trace

    def search(self, **kwargs):
        self.trace.append("retrieval")
        return KnowledgeRetrievalResult(
            query_hash="query-1",
            model_signature="embedding-1",
            citations=(
                KnowledgeCitation(
                    chunk_id=7,
                    knowledge_base_id=20,
                    version_id=21,
                    section_path="收入",
                    score=0.9,
                    content="只读参考内容",
                    visibility_scope="ADMIN_PUBLIC",
                    knowledge_base_name="指标口径库",
                    version_number=3,
                    source_block_id="block-revenue",
                    source_file_name="metrics.md",
                ),
            ),
            context='<retrieved-knowledge priority="reference-only">只读参考内容</retrieved-knowledge>',
            failure_type="NO_ELIGIBLE_KNOWLEDGE",
        )


class _CapturingRetrieval:
    def __init__(self):
        self.calls = []
        self.query_hashes = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        query_hash = hashlib.sha256(kwargs["query"].encode("utf-8")).hexdigest()
        self.query_hashes.append(query_hash)
        return KnowledgeRetrievalResult(
            query_hash=query_hash,
            model_signature="embedding-1",
            citations=(),
            context="",
        )


def _stub_semantic_dependencies(monkeypatch, *, skill_text: str, skill_list: list[str]):
    monkeypatch.setattr(semantic_context, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(semantic_context.PermissionScopeService, "build_snapshot", lambda **kwargs: _snapshot())
    monkeypatch.setattr(semantic_context, "eligible_data_skill_ids", lambda *args, **kwargs: frozenset())
    monkeypatch.setattr(
        semantic_context,
        "find_data_skills",
        lambda *args, **kwargs: (skill_text, skill_list, None),
    )
    monkeypatch.setattr(semantic_context, "find_tracking_prompt_context", lambda *args, **kwargs: ("", []))


def test_semantic_context_orders_authority_and_retrieval(monkeypatch):
    trace = []
    monkeypatch.setattr(semantic_context, "has_datasource_access", lambda *args, **kwargs: True)

    monkeypatch.setattr(
        semantic_context.PermissionScopeService,
        "build_snapshot",
        lambda **kwargs: trace.append("permission") or _snapshot(),
    )
    monkeypatch.setattr(
        semantic_context,
        "eligible_data_skill_ids",
        lambda *args, **kwargs: trace.append("eligible_skills") or frozenset({31}),
    )

    def skills(*_args, **kwargs):
        trace.append("find_data_skills")
        kwargs["selection_metadata"].update(
            selected_skill_ids=(31,), selection_mode="AUTOMATIC", source_hashes=("skill-1",)
        )
        return "<Data-Skills>口径</Data-Skills>", ["口径"], 3

    monkeypatch.setattr(semantic_context, "find_data_skills", skills)
    monkeypatch.setattr(
        semantic_context,
        "_default_schema_loader",
        lambda **kwargs: trace.append("schema") or ("schema", ["event"]),
    )
    monkeypatch.setattr(
        semantic_context,
        "find_tracking_prompt_context",
        lambda *args, **kwargs: trace.append("tracking") or ("tracking", []),
    )
    result = semantic_context.BusinessSemanticContextService.build(
        session=_Session(),
        current_user=SimpleNamespace(id=8, tenant_id=2),
        tenant_id=2,
        datasource_id=10,
        question="收入",
        structured_loader=lambda **kwargs: trace.append("structured")
        or SimpleNamespace(text="structured knowledge", warnings=()),
        retrieval_service=_Retrieval(trace),
        audit_writer=lambda **kwargs: trace.append("audit"),
    )

    assert trace == [
        "permission",
        "eligible_skills",
        "find_data_skills",
        "schema",
        "tracking",
        "structured",
        "retrieval",
        "audit",
    ]
    assert result.semantic.knowledge_citations[0].chunk_id == 7
    assert result.semantic.retrieval_failure_type == "NO_ELIGIBLE_KNOWLEDGE"
    assert result.semantic.context_hash
    snapshot = result.semantic.snapshot_metadata()
    assert snapshot["retrieval_failure_type"] == "NO_ELIGIBLE_KNOWLEDGE"
    assert snapshot["knowledge_citations"][0]["knowledge_base_name"] == "指标口径库"
    assert snapshot["knowledge_citations"][0]["version_number"] == 3
    assert snapshot["knowledge_citations"][0]["source_block_id"] == "block-revenue"
    assert snapshot["knowledge_citations"][0]["source_file_name"] == "metrics.md"
    assert "content" not in snapshot["knowledge_citations"][0]


def test_retrieval_query_uses_only_normalized_primary_intent(monkeypatch):
    _stub_semantic_dependencies(
        monkeypatch,
        skill_text="<Data-Skills>DAU、WAU、MAU、付费用户</Data-Skills>",
        skill_list=["DAU 口径", "WAU 口径", "MAU 口径", "付费用户口径"],
    )
    retrieval = _CapturingRetrieval()

    semantic_context.BusinessSemanticContextService.build(
        session=_Session(),
        current_user=SimpleNamespace(id=8, tenant_id=2),
        tenant_id=2,
        datasource_id=10,
        question="  商店购买  ",
        surface="SMART_QA",
        schema="授权 Schema：DAU、WAU、MAU、付费用户",
        allowed_tables=["event", "event_realtime", "user"],
        structured_loader=lambda **kwargs: SimpleNamespace(text="", warnings=()),
        retrieval_service=retrieval,
    )

    assert retrieval.calls[0]["query"] == "商店购买"


def test_retrieval_query_and_hash_ignore_auxiliary_context_changes(monkeypatch):
    retrieval = _CapturingRetrieval()

    _stub_semantic_dependencies(
        monkeypatch,
        skill_text="<Data-Skills>DAU 和新增用户</Data-Skills>",
        skill_list=["DAU 口径", "新增用户口径"],
    )
    semantic_context.BusinessSemanticContextService.build(
        session=_Session(),
        current_user=SimpleNamespace(id=8, tenant_id=2),
        tenant_id=2,
        datasource_id=10,
        question="商店购买",
        surface="SMART_QA",
        schema="Schema A：活跃和新增用户",
        allowed_tables=["event", "user"],
        structured_loader=lambda **kwargs: SimpleNamespace(text="", warnings=()),
        retrieval_service=retrieval,
    )

    _stub_semantic_dependencies(
        monkeypatch,
        skill_text="<Data-Skills>付费用户和 MAU</Data-Skills>",
        skill_list=["付费用户口径", "MAU 口径"],
    )
    semantic_context.BusinessSemanticContextService.build(
        session=_Session(),
        current_user=SimpleNamespace(id=8, tenant_id=2),
        tenant_id=2,
        datasource_id=10,
        question="商店购买",
        surface="analysis_assistant",
        schema="Schema B：付费和月活用户",
        allowed_tables=["payment", "session"],
        structured_loader=lambda **kwargs: SimpleNamespace(text="", warnings=()),
        retrieval_service=retrieval,
    )

    queries = [call["query"] for call in retrieval.calls]
    assert queries == ["商店购买", "商店购买"]
    assert retrieval.query_hashes == [
        hashlib.sha256("商店购买".encode()).hexdigest(),
        hashlib.sha256("商店购买".encode()).hexdigest(),
    ]


def test_blank_primary_intent_reaches_existing_empty_query_result(monkeypatch):
    _stub_semantic_dependencies(
        monkeypatch,
        skill_text="<Data-Skills>DAU、WAU、付费用户</Data-Skills>",
        skill_list=["DAU 口径", "WAU 口径", "付费用户口径"],
    )

    result = semantic_context.BusinessSemanticContextService.build(
        session=_Session(),
        current_user=SimpleNamespace(id=8, tenant_id=2),
        tenant_id=2,
        datasource_id=10,
        question=" \t\n ",
        surface="SMART_QA",
        schema="授权 Schema：DAU、WAU、付费用户",
        allowed_tables=["event", "user"],
        structured_loader=lambda **kwargs: SimpleNamespace(text="", warnings=()),
        retrieval_service=semantic_context.KnowledgeRetrievalService(),
    )

    assert result.semantic.retrieval_failure_type == "EMPTY_QUERY"
    assert result.semantic.knowledge_context == ""
    assert result.semantic.knowledge_citations == []


def test_context_hash_changes_with_permission_or_knowledge_snapshot(monkeypatch):
    monkeypatch.setattr(semantic_context, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(semantic_context.PermissionScopeService, "build_snapshot", lambda **kwargs: _snapshot())
    monkeypatch.setattr(semantic_context, "eligible_data_skill_ids", lambda *args, **kwargs: frozenset())
    monkeypatch.setattr(
        semantic_context,
        "find_data_skills",
        lambda *args, **kwargs: ("", [], None),
    )
    monkeypatch.setattr(semantic_context, "_default_schema_loader", lambda **kwargs: ("schema", []))
    monkeypatch.setattr(semantic_context, "find_tracking_prompt_context", lambda *args, **kwargs: ("", []))
    base = semantic_context.BusinessSemanticContextService.build(
        session=_Session(),
        current_user=SimpleNamespace(id=8, tenant_id=2),
        tenant_id=2,
        datasource_id=10,
        question="收入",
        structured_loader=lambda **kwargs: SimpleNamespace(text="", warnings=()),
        retrieval_service=_Retrieval([]),
    )
    changed = PermissionScopeSnapshot(**{**_snapshot().__dict__, "permission_version": "permission-2"})
    with_snapshot = semantic_context.BusinessSemanticContextService.build(
        session=_Session(),
        current_user=SimpleNamespace(id=8, tenant_id=2),
        tenant_id=2,
        datasource_id=10,
        question="收入",
        permission_snapshot=changed,
        structured_loader=lambda **kwargs: SimpleNamespace(text="", warnings=()),
        retrieval_service=_Retrieval([]),
    )
    assert with_snapshot.semantic.context_hash != base.semantic.context_hash


def test_knowledge_version_hash_is_stable_for_multiple_citations():
    citations = [
        KnowledgeCitation(
            chunk_id=9,
            knowledge_base_id=20,
            version_id=21,
            section_path="注意事项",
            score=0.8,
            content="第二个切片",
            visibility_scope="ADMIN_PUBLIC",
        ),
        KnowledgeCitation(
            chunk_id=7,
            knowledge_base_id=20,
            version_id=21,
            section_path="核心说明",
            score=0.9,
            content="第一个切片",
            visibility_scope="ADMIN_PUBLIC",
        ),
    ]

    version_hash = semantic_context._knowledge_version_hash(citations)

    assert version_hash
    assert version_hash == semantic_context._knowledge_version_hash(list(reversed(citations)))
