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


class _EmbeddingModelWithoutConfig:
    def __init__(self):
        self.batch_sizes: list[int] = []

    def embed_documents(self, texts):
        self.batch_sizes.append(len(texts))
        return [[float(len(text)), 1.0] for text in texts]


def _publisher(model):
    publisher = KnowledgePublisher(SimpleNamespace(), embedding_model=model)
    publisher._set_stage = lambda **_kwargs: None
    publisher._assert_snapshot = lambda *_args: None
    publisher._heartbeat = lambda *_args, **_kwargs: None
    return publisher


def _chunks(count: int = 3):
    return [
        KnowledgeChunkDraft(i, "正文", f"chunk-{i}", str(i) * 64, 2)
        for i in range(count)
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


def test_embedding_without_model_config_uses_application_batch_size(monkeypatch):
    model = _EmbeddingModelWithoutConfig()
    monkeypatch.setattr(
        "apps.knowledge_base.publisher.settings.EMBEDDING_BATCH_SIZE",
        10,
    )

    artifact = _publisher(model)._embed(
        SimpleNamespace(id=1, revision=1, content_hash="x"),
        SimpleNamespace(id=2),
        _chunks(23),
    )

    assert model.batch_sizes == [10, 10, 3]
    assert len(artifact.vectors) == 23
