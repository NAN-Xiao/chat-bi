import asyncio

import pytest

from apps.datasource.utils.utils import (
    aes_decrypt,
    encrypt_datasource_configuration,
    legacy_aes_encrypt_for_tests,
)
from apps.system.api.aimodel import _encrypt_ai_model_secrets
from common.core.config import settings
from common.utils.crypto import (
    decrypt_sensitive_text,
    encrypt_sensitive_text,
    legacy_zhishu_encrypt_for_tests,
)


@pytest.fixture(autouse=True)
def stable_encryption_key(monkeypatch):
    monkeypatch.setattr(settings, "SENSITIVE_CONFIG_ENCRYPTION_KEY", "s" * 48)
    monkeypatch.setattr(settings, "DATASOURCE_CONFIG_ENCRYPTION_KEY", None)
    monkeypatch.setattr(settings, "LEGACY_CONFIG_AES_KEYS", None)


def test_sensitive_text_uses_versioned_server_side_encryption():
    encrypted = encrypt_sensitive_text("secret-value")

    assert encrypted.startswith("fernet:v1:")
    assert encrypted != legacy_zhishu_encrypt_for_tests("secret-value")
    assert decrypt_sensitive_text(encrypted) == "secret-value"


def test_sensitive_text_keeps_legacy_aes_readable():
    legacy = legacy_zhishu_encrypt_for_tests("legacy-secret")

    assert decrypt_sensitive_text(legacy) == "legacy-secret"


def test_sensitive_text_reads_explicit_legacy_aes_keys(monkeypatch):
    legacy_key = b"LegacyNeutralKey"
    legacy = legacy_zhishu_encrypt_for_tests("legacy-secret", key=legacy_key)

    assert decrypt_sensitive_text(legacy) == legacy

    monkeypatch.setattr(settings, "LEGACY_CONFIG_AES_KEYS", legacy_key.decode("utf-8"))

    assert decrypt_sensitive_text(legacy) == "legacy-secret"


def test_datasource_configuration_encrypts_and_reads_legacy_values():
    plain = '{"host":"db.example.com","password":"secret"}'
    legacy = legacy_aes_encrypt_for_tests(plain)

    assert aes_decrypt(legacy) == plain

    encrypted = encrypt_datasource_configuration(legacy)

    assert encrypted.startswith("fernet:v1:")
    assert aes_decrypt(encrypted) == plain


def test_ai_model_connection_fields_are_encrypted_on_write():
    data = {
        "api_key": "sk-prod-secret",
        "api_domain": "https://llm.example.com/v1",
        "name": "default",
    }

    encrypted = asyncio.run(_encrypt_ai_model_secrets(data))

    assert encrypted["name"] == "default"
    assert encrypted["api_key"].startswith("fernet:v1:")
    assert encrypted["api_domain"].startswith("fernet:v1:")
    assert decrypt_sensitive_text(encrypted["api_key"]) == "sk-prod-secret"
    assert decrypt_sensitive_text(encrypted["api_domain"]) == "https://llm.example.com/v1"
