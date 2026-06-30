import asyncio
import base64

import pytest
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

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
    legacy_shuzhi_encrypt_for_tests,
)


CONFIGURED_LEGACY_AES_KEY = b"LegacyTestKey123"
SQLBOT_LEGACY_AES_KEY = b"SQLBot1234567890"
OLD_BRAND_LEGACY_AES_KEY = bytes([90, 104, 105, 115, 104, 117, 49, 50, 51, 52, 53, 54, 55, 56, 57, 48])


def _legacy_ecb_encrypt_with_key(text: str, key: bytes) -> str:
    cipher = AES.new(key, AES.MODE_ECB)
    encrypted = cipher.encrypt(pad(text.encode("utf-8"), AES.block_size))
    return base64.b64encode(encrypted).decode("utf-8")


@pytest.fixture(autouse=True)
def stable_encryption_key(monkeypatch):
    monkeypatch.setattr(settings, "SENSITIVE_CONFIG_ENCRYPTION_KEY", "s" * 48)
    monkeypatch.setattr(settings, "DATASOURCE_CONFIG_ENCRYPTION_KEY", None)
    monkeypatch.setattr(settings, "LEGACY_CONFIG_AES_KEYS", "")


def test_sensitive_text_uses_versioned_server_side_encryption():
    encrypted = encrypt_sensitive_text("secret-value")

    assert encrypted.startswith("fernet:v1:")
    assert encrypted != legacy_shuzhi_encrypt_for_tests("secret-value")
    assert decrypt_sensitive_text(encrypted) == "secret-value"


def test_sensitive_text_keeps_legacy_aes_readable():
    legacy = legacy_shuzhi_encrypt_for_tests("legacy-secret")

    assert decrypt_sensitive_text(legacy) == "legacy-secret"


def test_sensitive_text_reads_configured_legacy_aes_key(monkeypatch):
    monkeypatch.setattr(settings, "LEGACY_CONFIG_AES_KEYS", CONFIGURED_LEGACY_AES_KEY.decode("utf-8"))
    legacy = _legacy_ecb_encrypt_with_key("legacy-secret", CONFIGURED_LEGACY_AES_KEY)

    assert decrypt_sensitive_text(legacy) == "legacy-secret"


def test_sensitive_text_reads_builtin_old_brand_legacy_aes_key():
    legacy = _legacy_ecb_encrypt_with_key("legacy-secret", OLD_BRAND_LEGACY_AES_KEY)

    assert decrypt_sensitive_text(legacy) == "legacy-secret"


def test_datasource_configuration_encrypts_and_reads_legacy_values():
    plain = '{"host":"db.example.com","password":"secret"}'
    legacy = legacy_aes_encrypt_for_tests(plain)

    assert aes_decrypt(legacy) == plain

    encrypted = encrypt_datasource_configuration(legacy)

    assert encrypted.startswith("fernet:v1:")
    assert aes_decrypt(encrypted) == plain


def test_datasource_configuration_reads_configured_legacy_aes_key(monkeypatch):
    monkeypatch.setattr(settings, "LEGACY_CONFIG_AES_KEYS", f"base64:{base64.b64encode(CONFIGURED_LEGACY_AES_KEY).decode('utf-8')}")
    plain = '{"host":"db.example.com","password":"secret"}'
    legacy = _legacy_ecb_encrypt_with_key(plain, CONFIGURED_LEGACY_AES_KEY)

    assert aes_decrypt(legacy) == plain

    encrypted = encrypt_datasource_configuration(legacy)

    assert encrypted.startswith("fernet:v1:")
    assert aes_decrypt(encrypted) == plain


def test_datasource_configuration_reads_sqlbot_legacy_aes_key():
    plain = '{"host":"127.0.0.1","database":"slg_bi_mock"}'
    legacy = _legacy_ecb_encrypt_with_key(plain, SQLBOT_LEGACY_AES_KEY)

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
