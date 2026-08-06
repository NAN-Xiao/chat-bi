"""Publisher batch checks are deterministic and fail closed."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.knowledge_base.chunking import KnowledgeChunkDraft
from apps.knowledge_base.publisher import KnowledgePublisher


class _EmbeddingModel:
    class config:
        batch_size = 2
        model = "test-embedding"
        normalize_embeddings = False

    def __init__(self, *, fail_at: int | None = None):
        self.calls = 0
        self.fail_at = fail_at

    def embed_documents(self, texts):
        self.calls += 1
        if self.fail_at == self.calls:
            raise RuntimeError("upstream unavailable")
        return [[float(len(text)), 1.0] for text in texts]


def _publisher(model):
    publisher = KnowledgePublisher(SimpleNamespace(), embedding_model=model)
    publisher._set_stage = lambda **_kwargs: None
    publisher._assert_snapshot = lambda *_args: None
    publisher._heartbeat = lambda *_args, **_kwargs: None
    return publisher


def _chunks():
    return [
        KnowledgeChunkDraft(i, "正文", f"chunk-{i}", str(i) * 64, 2)
        for i in range(3)
    ]


def test_embedding_batches_are_complete_and_have_one_signature():
    artifact = _publisher(_EmbeddingModel())._embed(
        SimpleNamespace(id=1, revision=1, content_hash="x"),
        SimpleNamespace(id=2),
        _chunks(),
    )
    assert len(artifact.vectors) == 3
    assert artifact.dimension == 2
    assert artifact.embedding_signature


def test_embedding_failure_is_propagated_before_any_artifact_is_persisted():
    publisher = _publisher(_EmbeddingModel(fail_at=2))
    with pytest.raises(RuntimeError, match="upstream unavailable"):
        publisher._embed(
            SimpleNamespace(id=1, revision=1, content_hash="x"),
            SimpleNamespace(id=2),
            _chunks(),
        )
