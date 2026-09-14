from common.core.config import Settings


def test_default_embedding_model_is_authorized_remote_model() -> None:
    settings = Settings(_env_file=None)

    assert settings.DEFAULT_EMBEDDING_MODEL == "qwen3.7-text-embedding"
    assert settings.EMBEDDING_MODEL == "qwen3.7-text-embedding"
