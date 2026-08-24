"""Verify knowledge management and retrieval runtime defaults."""

from __future__ import annotations

import pytest

from common.core.config import Settings


def test_knowledge_defaults_enabled_when_environment_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "KNOWLEDGE_MANAGEMENT_V2_ENABLED",
        "KNOWLEDGE_RUNTIME_CONTEXT_ENABLED",
        "KNOWLEDGE_RETRIEVAL_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None, SECRET_KEY="test-secret")

    assert settings.KNOWLEDGE_MANAGEMENT_V2_ENABLED is True
    assert settings.KNOWLEDGE_RUNTIME_CONTEXT_ENABLED is True
    assert settings.KNOWLEDGE_RETRIEVAL_ENABLED is True


def test_knowledge_v2_management_accepts_explicit_disable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KNOWLEDGE_MANAGEMENT_V2_ENABLED", "false")

    settings = Settings(_env_file=None, SECRET_KEY="test-secret")

    assert settings.KNOWLEDGE_MANAGEMENT_V2_ENABLED is False


@pytest.mark.parametrize(
    ("disabled_name", "enabled_name"),
    [
        ("KNOWLEDGE_RUNTIME_CONTEXT_ENABLED", "KNOWLEDGE_RETRIEVAL_ENABLED"),
        ("KNOWLEDGE_RETRIEVAL_ENABLED", "KNOWLEDGE_RUNTIME_CONTEXT_ENABLED"),
    ],
)
def test_knowledge_runtime_flags_accept_independent_explicit_disable(
    monkeypatch: pytest.MonkeyPatch,
    disabled_name: str,
    enabled_name: str,
) -> None:
    monkeypatch.setenv(disabled_name, "false")
    monkeypatch.delenv(enabled_name, raising=False)

    settings = Settings(_env_file=None, SECRET_KEY="test-secret")

    assert getattr(settings, disabled_name) is False
    assert getattr(settings, enabled_name) is True
