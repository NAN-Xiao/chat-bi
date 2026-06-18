import base64
from hashlib import sha256

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from cryptography.fernet import Fernet, InvalidToken

from common.core.config import settings

_AES_KEY = b"Zhishu1234567890"
_LEGACY_AES_KEYS = (b"SQLBot1234567890",)
_FERNET_PREFIX = "fernet:v1:"


def _encryption_secret() -> str:
    return (
        settings.SENSITIVE_CONFIG_ENCRYPTION_KEY
        or settings.DATASOURCE_CONFIG_ENCRYPTION_KEY
        or settings.SECRET_KEY
    )


def _fernet() -> Fernet:
    derived = base64.urlsafe_b64encode(sha256(_encryption_secret().encode("utf-8")).digest())
    return Fernet(derived)


def _legacy_ecb_encrypt(text: str) -> str:
    cipher = AES.new(_AES_KEY, AES.MODE_ECB)
    encrypted = cipher.encrypt(pad((text or "").encode("utf-8"), AES.block_size))
    return base64.b64encode(encrypted).decode("utf-8")


def _legacy_ecb_decrypt_with_key(text: str, key: bytes) -> str:
    cipher = AES.new(key, AES.MODE_ECB)
    decrypted = cipher.decrypt(base64.b64decode(text))
    return unpad(decrypted, AES.block_size).decode("utf-8")


def _legacy_ecb_decrypt(text: str) -> str:
    try:
        return _legacy_ecb_decrypt_with_key(text, _AES_KEY)
    except Exception:
        for legacy_key in _LEGACY_AES_KEYS:
            try:
                return _legacy_ecb_decrypt_with_key(text, legacy_key)
            except Exception:
                continue
        raise


def encrypt_sensitive_text(text: str | None) -> str | None:
    if text is None:
        return None
    if not isinstance(text, str):
        return text
    if text == "" or text.startswith(_FERNET_PREFIX):
        return text

    plaintext = decrypt_sensitive_text(text)
    token = _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")
    return f"{_FERNET_PREFIX}{token}"


def decrypt_sensitive_text(text: str | None) -> str | None:
    if text is None:
        return None
    if not isinstance(text, str):
        return text
    if text == "":
        return text
    if text.startswith(_FERNET_PREFIX):
        try:
            return _fernet().decrypt(text[len(_FERNET_PREFIX):].encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Invalid encrypted sensitive configuration") from exc
    try:
        return _legacy_ecb_decrypt(text)
    except Exception:
        # Keep plaintext-compatible behavior for login requests and for
        # rows that existed before server-side secret encryption.
        return text


def zhishu_decrypt_sync(text: str | None) -> str | None:
    return decrypt_sensitive_text(text)


async def zhishu_decrypt(text: str | None) -> str | None:
    return zhishu_decrypt_sync(text)


async def zhishu_encrypt(text: str | None) -> str | None:
    return encrypt_sensitive_text(text)


def legacy_zhishu_encrypt_for_tests(text: str) -> str:
    return _legacy_ecb_encrypt(text)
