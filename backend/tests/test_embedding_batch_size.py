from pathlib import Path

from apps.ai_model.embedding import EmbeddingModelInfo, OpenAICompatibleEmbeddings
from common.core.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def _embedding_model(batch_size: int) -> OpenAICompatibleEmbeddings:
    return OpenAICompatibleEmbeddings(
        EmbeddingModelInfo(
            model="test-embedding",
            api_base_url="https://example.test/v1",
            api_key="test-key",
            batch_size=batch_size,
            normalize_embeddings=False,
        )
    )


def test_embedding_batch_size_defaults_to_ten(monkeypatch):
    monkeypatch.delenv("EMBEDDING_BATCH_SIZE", raising=False)

    embedding_settings = Settings(_env_file=None)

    assert embedding_settings.EMBEDDING_BATCH_SIZE == 10


def test_embedding_batch_size_supports_positive_environment_override(monkeypatch):
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "7")

    embedding_settings = Settings(_env_file=None)

    assert embedding_settings.EMBEDDING_BATCH_SIZE == 7


def test_embedding_documents_batches_23_inputs_as_ten_ten_three(monkeypatch):
    model = _embedding_model(batch_size=10)
    texts = [f"text-{index}" for index in range(23)]
    positions = {text: index for index, text in enumerate(texts)}
    batches: list[list[str]] = []

    def embed_batch(batch: list[str]) -> list[list[float]]:
        batches.append(list(batch))
        return [[float(positions[text])] for text in batch]

    monkeypatch.setattr(model, "_embed_batch", embed_batch)

    vectors = model.embed_documents(texts)

    assert [len(batch) for batch in batches] == [10, 10, 3]
    assert [text for batch in batches for text in batch] == texts
    assert vectors == [[float(index)] for index in range(23)]


def test_embedding_documents_respects_explicit_positive_batch_size(monkeypatch):
    model = _embedding_model(batch_size=4)
    batches: list[list[str]] = []

    def embed_batch(batch: list[str]) -> list[list[float]]:
        batches.append(list(batch))
        return [[float(text)] for text in batch]

    monkeypatch.setattr(model, "_embed_batch", embed_batch)

    vectors = model.embed_documents([str(index) for index in range(9)])

    assert [len(batch) for batch in batches] == [4, 4, 1]
    assert vectors == [[float(index)] for index in range(9)]


def test_deployment_configuration_propagates_embedding_batch_size():
    install_conf = (REPO_ROOT / "installer/install.conf").read_text(encoding="utf-8")
    install_template = (
        REPO_ROOT / "installer/shuzhi/templates/shuzhi.conf"
    ).read_text(encoding="utf-8")
    jenkinsfile = (REPO_ROOT / "Jenkinsfile").read_text(encoding="utf-8")

    assert "SHUZHI_EMBEDDING_BATCH_SIZE=10" in install_conf.splitlines()
    assert (
        "EMBEDDING_BATCH_SIZE=${SHUZHI_EMBEDDING_BATCH_SIZE}"
        in install_template.splitlines()
    )
    assert ': "${SHUZHI_EMBEDDING_BATCH_SIZE:?' in jenkinsfile
    assert (
        'echo "EMBEDDING_BATCH_SIZE=${SHUZHI_EMBEDDING_BATCH_SIZE}"'
        in jenkinsfile
    )
