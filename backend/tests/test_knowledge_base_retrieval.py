"""Permission-first retrieval behavior tests."""

from __future__ import annotations

from types import SimpleNamespace

from apps.datasource.crud.permission_scope import PermissionScopeSnapshot
from apps.knowledge_base.retrieval import KnowledgeRetrievalService


class _EmbeddingModel:
    class config:
        model = "test-embedding"
        normalize_embeddings = False

    def embed_query(self, _query):
        return [1.0, 0.0]


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
        SimpleNamespace(id=1, version_id=11),
        SimpleNamespace(id=2, version_id=11),
    ]
    rows = {
        1: SimpleNamespace(
            id=1,
            knowledge_base_id=20,
            version_id=11,
            section_path="收入",
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
    assert "forbidden content" not in result.context


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
