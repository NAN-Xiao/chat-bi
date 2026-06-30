from typing import Optional

import base64

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from common.core.config import settings

simple_aes_iv_text = 'shuzhi_em_aes_iv'


def _normalize_bytes(text: str, size: int) -> bytes:
    raw = (text or "").encode("utf-8")
    if len(raw) >= size:
        return raw[:size]
    return raw.ljust(size, b"\0")


def shuzhi_aes_encrypt(text: str, key: Optional[str] = None) -> str:
    return simple_aes_encrypt(text, key)

def shuzhi_aes_decrypt(text: str, key: Optional[str] = None) -> str:
    return simple_aes_decrypt(text, key)

def simple_aes_encrypt(text: str, key: Optional[str] = None, ivtext: Optional[str] = None) -> str:
    cipher = AES.new(
        _normalize_bytes(key or settings.SECRET_KEY[:32], 32),
        AES.MODE_CBC,
        _normalize_bytes(ivtext or simple_aes_iv_text, 16),
    )
    encrypted = cipher.encrypt(pad((text or "").encode("utf-8"), AES.block_size))
    return base64.b64encode(encrypted).decode("utf-8")

def simple_aes_decrypt(text: str, key: Optional[str] = None, ivtext: Optional[str] = None) -> str:
    cipher = AES.new(
        _normalize_bytes(key or settings.SECRET_KEY[:32], 32),
        AES.MODE_CBC,
        _normalize_bytes(ivtext or simple_aes_iv_text, 16),
    )
    decrypted = cipher.decrypt(base64.b64decode(text))
    return unpad(decrypted, AES.block_size).decode("utf-8")
