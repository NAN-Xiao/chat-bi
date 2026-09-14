from common.core.config import Settings


def test_default_embedding_model_is_authorized_remote_model() -> None:
    settings = Settings(_env_file=None)

    assert settings.DEFAULT_EMBEDDING_MODEL == "Alibaba/text-embedding-v4"
    assert settings.EMBEDDING_MODEL == "Alibaba/text-embedding-v4"
