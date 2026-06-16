import base64
from typing import Optional

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


_AES_KEY = b"Zhishu1234567890"
_LEGACY_AES_KEYS = (b"SQLBot1234567890",)


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


async def zhishu_decrypt(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    if not isinstance(text, str):
        return text
    if text == "":
        return text
    try:
        return _legacy_ecb_decrypt(text)
    except Exception:
        # Keep plaintext-compatible behavior for requests like login and
        # for records that may already be stored as raw text.
        return text


async def zhishu_encrypt(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    if not isinstance(text, str):
        return text
    return _legacy_ecb_encrypt(text)
