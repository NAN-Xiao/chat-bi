"""Permission-first retrieval behavior tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.datasource.crud.permission_scope import PermissionScopeSnapshot
from apps.knowledge_base.retrieval import KnowledgeCitation, KnowledgeRetrievalService


class _EmbeddingModel:
    class config:
        model = "test-embedding"
        normalize_embeddings = False

    def embed_query(self, _query):
        return [1.0, 0.0]


class _Reranker:
    class config:
        model = "test-reranker"

    def __init__(self, scores):
        self.scores = scores
        self.calls = []

    def rerank(self, query, documents):
        self.calls.append((query, documents))
        return self.scores


@pytest.fixture(autouse=True)
def disable_network_rerank_by_default(monkeypatch):
    monkeypatch.setattr("apps.knowledge_base.retrieval.settings.KNOWLEDGE_RETRIEVAL_RERANK_ENABLED", False)


def _snapshot():
    return PermissionScopeSnapshot(
        tenant_id=2,
        user_id=8,
        datasource_id=10,
        permission_version="perm-1",
        schema_hash="schema-1",
        allowed_object_keys=frozenset({"allowed-key"}),
        denied_object_keys=frozenset({"denied-key"}),
        row_constraints_hash="row-1",
    )


def test_retrieval_filters_before_loading_chunk_content(monkeypatch):
    service = KnowledgeRetrievalService(embedding_model=_EmbeddingModel())
    candidates = [
        SimpleNamespace(
            id=1,
            version_id=11,
            knowledge_base_name="指标口径库",
            version_number=3,
            source_file_name="metrics.md",
        ),
        SimpleNamespace(id=2, version_id=11),
    ]
    rows = {
        1: SimpleNamespace(
            id=1,
            knowledge_base_id=20,
            version_id=11,
            section_path="收入",
            source_block_id="block-revenue",
            content="allowed content",
            visibility_scope="ADMIN_PUBLIC",
            embedding=[1.0, 0.0],
            embedding_signature=None,
        ),
        2: SimpleNamespace(
            id=2,
            knowledge_base_id=20,
            version_id=11,
            section_path="secret",
            content="forbidden content",
            visibility_scope="ADMIN_PUBLIC",
            embedding=[1.0, 0.0],
            embedding_signature=None,
        ),
    }
    loaded_ids = []
    monkeypatch.setattr(service, "_load_candidate_metadata", lambda *_args, **_kwargs: candidates)
    monkeypatch.setattr(service, "_load_candidate_references", lambda _session, *, chunk_id, version_id: [SimpleNamespace(id=chunk_id)])
    monkeypatch.setattr(service, "_references_allowed", lambda _session, refs, *, snapshot: refs[0].id == 1)
    monkeypatch.setattr(service, "_load_allowed_chunks", lambda _session, ids: [loaded_ids.extend(ids) or rows[item] for item in ids])
    monkeypatch.setattr("apps.knowledge_base.retrieval.embedding_payload_signature", lambda *_args: "signature")
    rows[1].embedding_signature = "signature"
    result = service.search(
        session=SimpleNamespace(),
        tenant_id=2,
        datasource_id=10,
        surface="SMART_QA",
        query="收入",
        permission_snapshot=_snapshot(),
        top_k=5,
        max_context_chars=12000,
    )
    assert loaded_ids == [1]
    assert [item.chunk_id for item in result.citations] == [1]
    assert result.citations[0].knowledge_base_name == "指标口径库"
    assert result.citations[0].version_number == 3
    assert result.citations[0].source_file_name == "metrics.md"
    assert result.citations[0].source_block_id == "block-revenue"
    assert "forbidden content" not in result.context


def test_retrieval_reranks_candidates_before_final_threshold_and_context(monkeypatch):
    service = KnowledgeRetrievalService(
        embedding_model=_EmbeddingModel(),
        reranker_model=_Reranker([(1, 0.95), (0, 0.82), (2, 0.61)]),
    )
    candidates = [SimpleNamespace(id=index, version_id=11) for index in (1, 2, 3)]
    rows = [
        SimpleNamespace(
            id=index,
            knowledge_base_id=20,
            version_id=11,
            section_path=str(index),
            content=f"content-{index}",
            visibility_scope="ADMIN_PUBLIC",
            embedding=[1.0, 0.0],
            embedding_signature="signature",
        )
        for index in (1, 2, 3)
    ]
    monkeypatch.setattr(service, "_load_candidate_metadata", lambda *_args, **_kwargs: candidates)
    monkeypatch.setattr(service, "_load_candidate_references", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(service, "_load_allowed_chunks", lambda *_args, **_kwargs: rows)
    monkeypatch.setattr("apps.knowledge_base.retrieval.embedding_payload_signature", lambda *_args: "signature")
    monkeypatch.setattr("apps.knowledge_base.retrieval.settings.KNOWLEDGE_RETRIEVAL_RERANK_ENABLED", True)
    monkeypatch.setattr("apps.knowledge_base.retrieval.settings.KNOWLEDGE_RETRIEVAL_INITIAL_TOP_K", 3)
    monkeypatch.setattr("apps.knowledge_base.retrieval.settings.KNOWLEDGE_RETRIEVAL_VECTOR_MIN_SCORE", 0.4)
    monkeypatch.setattr("apps.knowledge_base.retrieval.settings.KNOWLEDGE_RETRIEVAL_MIN_SCORE", 0.7)

    result = service.search(
        session=SimpleNamespace(),
        tenant_id=2,
        datasource_id=10,
        surface="SMART_QA",
        query="收入",
        permission_snapshot=_snapshot(),
    )

    assert [item.chunk_id for item in result.citations] == [2, 1]
    assert [item.rerank_score for item in result.citations] == [0.95, 0.82]
    assert '<retrieved-knowledge priority="reference-only" rank="1" score="0.950000" id="2">' in result.context
    assert "content-3" not in result.context
    assert service.reranker_model.calls == [("收入", ["content-1", "content-2", "content-3"])]


def test_retrieval_takes_top_five_after_rerank(monkeypatch):
    chunk_ids = tuple(range(1, 7))
    service = KnowledgeRetrievalService(
        embedding_model=_EmbeddingModel(),
        reranker_model=_Reranker([(index - 1, 0.95 - index * 0.02) for index in chunk_ids]),
    )
    candidates = [SimpleNamespace(id=index, version_id=11) for index in chunk_ids]
    rows = [
        SimpleNamespace(
            id=index,
            knowledge_base_id=20,
            version_id=11,
            section_path=str(index),
            content=f"content-{index}",
            visibility_scope="ADMIN_PUBLIC",
            embedding=[1.0, 0.0],
            embedding_signature="signature",
        )
        for index in chunk_ids
    ]
    monkeypatch.setattr(service, "_load_candidate_metadata", lambda *_args, **_kwargs: candidates)
    monkeypatch.setattr(service, "_load_candidate_references", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(service, "_load_allowed_chunks", lambda *_args, **_kwargs: rows)
    monkeypatch.setattr("apps.knowledge_base.retrieval.embedding_payload_signature", lambda *_args: "signature")
    monkeypatch.setattr("apps.knowledge_base.retrieval.settings.KNOWLEDGE_RETRIEVAL_RERANK_ENABLED", True)
    monkeypatch.setattr("apps.knowledge_base.retrieval.settings.KNOWLEDGE_RETRIEVAL_INITIAL_TOP_K", 6)
    monkeypatch.setattr("apps.knowledge_base.retrieval.settings.KNOWLEDGE_RETRIEVAL_TOP_K", 5)
    monkeypatch.setattr("apps.knowledge_base.retrieval.settings.KNOWLEDGE_RETRIEVAL_VECTOR_MIN_SCORE", 0.4)
    monkeypatch.setattr("apps.knowledge_base.retrieval.settings.KNOWLEDGE_RETRIEVAL_MIN_SCORE", 0.7)

    result = service.search(
        session=SimpleNamespace(),
        tenant_id=2,
        datasource_id=10,
        surface="SMART_QA",
        query="收入",
        permission_snapshot=_snapshot(),
    )

    assert [item.chunk_id for item in result.citations] == [1, 2, 3, 4, 5]
    assert result.context.count("<retrieved-knowledge") == 5
    assert "content-6" not in result.context


def test_permission_context_mismatch_fails_without_model_call():
    service = KnowledgeRetrievalService(embedding_model=_EmbeddingModel())
    result = service.search(
        session=SimpleNamespace(),
        tenant_id=99,
        datasource_id=10,
        surface="SMART_QA",
        query="收入",
        permission_snapshot=_snapshot(),
    )
    assert result.failure_type == "PERMISSION_CONTEXT_MISMATCH"
    assert result.citations == ()


def test_retrieval_bounds_first_long_citation_without_breaking_context_tags():
    citation = KnowledgeCitation(
        chunk_id=7,
        knowledge_base_id=20,
        version_id=21,
        section_path="收入",
        score=0.9,
        content="统计口径" * 100,
        visibility_scope="ADMIN_PUBLIC",
    )

    bounded = KnowledgeRetrievalService._bound_context(
        [citation],
        top_k=1,
        max_chars=160,
    )
    result = KnowledgeRetrievalService._result("query-1", "embedding-1", tuple(bounded))

    assert len(result.context) <= 160
    assert result.context.startswith(
        '<retrieved-knowledge priority="reference-only" rank="1" score="0.900000" id="7">'
    )
    assert result.context.endswith("</retrieved-knowledge>")
    assert result.citations[0].content in result.context
    assert result.citations[0].content != citation.content


def test_retrieval_evaluates_missing_datasource_applicability(monkeypatch):
    service = KnowledgeRetrievalService(embedding_model=_EmbeddingModel())
    candidate = SimpleNamespace(id=1, version_id=11, applicability_status=None)
    row = SimpleNamespace(
        id=1,
        knowledge_base_id=20,
        version_id=11,
        section_path="收入",
        content="allowed content",
        visibility_scope="ADMIN_PUBLIC",
        embedding=[1.0, 0.0],
        embedding_signature="signature",
    )
    monkeypatch.setattr(service, "_load_candidate_metadata", lambda *_args, **_kwargs: [candidate])
    monkeypatch.setattr(
        service,
        "_evaluate_applicability",
        lambda *_args, **_kwargs: SimpleNamespace(eligible=True),
    )
    monkeypatch.setattr(service, "_load_candidate_references", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(service, "_load_allowed_chunks", lambda *_args, **_kwargs: [row])
    monkeypatch.setattr("apps.knowledge_base.retrieval.embedding_payload_signature", lambda *_args: "signature")
    result = service.search(
        session=SimpleNamespace(),
        tenant_id=2,
        datasource_id=10,
        surface="SMART_QA",
        query="收入",
        permission_snapshot=_snapshot(),
    )
    assert [item.chunk_id for item in result.citations] == [1]


def test_load_allowed_chunks_uses_sqlmodel_scalar_select():
    class _Result:
        def all(self):
            return [SimpleNamespace(id=1)]

    class _Session:
        def exec(self, statement):
            assert statement.__class__.__name__ == "SelectOfScalar"
            return _Result()

    rows = KnowledgeRetrievalService._load_allowed_chunks(_Session(), [1])
    assert [item.id for item in rows] == [1]


def test_candidate_query_uses_publication_lifecycle_instead_of_active_flag():
    class _Result:
        def all(self):
            return []

    class _Session:
        statement = None

        def exec(self, statement):
            self.statement = statement
            return _Result()

    session = _Session()
    KnowledgeRetrievalService._load_candidate_metadata(
        session,
        tenant_id=2,
        datasource_id=10,
        schema_hash="schema-1",
    )
    sql = str(session.statement).lower()

    assert "knowledge_base_version.status" in sql
    assert "knowledge_base.current_version_id" in sql
    assert "knowledge_base.archived" in sql
    assert "knowledge_base.active" not in sql


def test_chunk_reference_inherits_version_resolution_for_existing_versions():
    class _Result:
        def __init__(self, value):
            self.value = value

        def first(self):
            return self.value

    class _Session:
        def __init__(self):
            self.calls = 0

        def exec(self, statement):
            self.calls += 1
            if self.calls == 1:
                return _Result(None)
            if self.calls == 2:
                return _Result(SimpleNamespace(id=9))
            return _Result(SimpleNamespace(canonical_key="allowed-key"))

    reference = SimpleNamespace(
        id=17,
        owner_type="KNOWLEDGE_CHUNK",
        version_id=11,
        tenant_id=2,
        declared_key="declared",
        source_kind="EXPLICIT",
        datasource_id=None,
    )
    assert KnowledgeRetrievalService._references_allowed(
        _Session(),
        [reference],
        snapshot=_snapshot(),
    )
