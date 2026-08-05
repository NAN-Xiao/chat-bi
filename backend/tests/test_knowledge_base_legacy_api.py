"""Keep legacy knowledge behavior disabled by configuration until cutover."""

from common.core.config import Settings


def test_knowledge_v2_feature_flags_default_to_disabled() -> None:
    settings = Settings(
        _env_file=None,
        SECRET_KEY="test-secret",
    )

    assert settings.KNOWLEDGE_MANAGEMENT_V2_ENABLED is False
    assert settings.KNOWLEDGE_RUNTIME_CONTEXT_ENABLED is False
