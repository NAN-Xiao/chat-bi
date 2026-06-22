import base64
import json

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from common.utils.crypto import decrypt_sensitive_text, encrypt_sensitive_text

key = b"Zhishu1234567890"
_FERNET_PREFIX = "fernet:v1:"


def _is_plain_json(value: str) -> bool:
    try:
        json.loads(value)
        return True
    except Exception:
        return False


def _legacy_aes_encrypt(data: str) -> str:
    raw = bytes(data, "utf-8")
    cipher = AES.new(key, AES.MODE_ECB)
    encrypted = cipher.encrypt(pad(raw, AES.block_size))
    return base64.b64encode(encrypted).decode("utf-8")


def aes_encrypt(data):
    return encrypt_datasource_configuration(data)


def aes_decrypt(encrypted_data):
    if encrypted_data is None:
        return ""

    text = encrypted_data.decode("utf-8") if isinstance(encrypted_data, bytes) else str(encrypted_data)
    if not text:
        return ""
    return decrypt_sensitive_text(text)


def encrypt_datasource_configuration(configuration: str | bytes | None) -> str:
    if configuration is None:
        return ""

    text = configuration.decode("utf-8") if isinstance(configuration, bytes) else str(configuration)
    if not text or text.startswith(_FERNET_PREFIX):
        return text

    plaintext = text if _is_plain_json(text) else aes_decrypt(text)
    return encrypt_sensitive_text(plaintext)


def decrypt_datasource_configuration_for_output(configuration: str | bytes | None) -> str | None:
    if configuration in (None, ""):
        return None
    return aes_decrypt(configuration)


def legacy_aes_encrypt_for_tests(data: str) -> str:
    return _legacy_aes_encrypt(data)
