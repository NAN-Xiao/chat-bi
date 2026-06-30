"""
脚本说明：这个脚本放通用工具相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
from typing import Optional

import base64

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from common.core.config import settings

simple_aes_iv_text = 'shuzhi_em_aes_iv'


def _normalize_bytes(text: str, size: int) -> bytes:
    """
    是什么：_normalize_bytes 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    raw = (text or "").encode("utf-8")
    if len(raw) >= size:
        return raw[:size]
    return raw.ljust(size, b"\0")


def shuzhi_aes_encrypt(text: str, key: Optional[str] = None) -> str:
    """
    是什么：shuzhi_aes_encrypt 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return simple_aes_encrypt(text, key)

def shuzhi_aes_decrypt(text: str, key: Optional[str] = None) -> str:
    """
    是什么：shuzhi_aes_decrypt 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return simple_aes_decrypt(text, key)

def simple_aes_encrypt(text: str, key: Optional[str] = None, ivtext: Optional[str] = None) -> str:
    """
    是什么：simple_aes_encrypt 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    cipher = AES.new(
        _normalize_bytes(key or settings.SECRET_KEY[:32], 32),
        AES.MODE_CBC,
        _normalize_bytes(ivtext or simple_aes_iv_text, 16),
    )
    encrypted = cipher.encrypt(pad((text or "").encode("utf-8"), AES.block_size))
    return base64.b64encode(encrypted).decode("utf-8")

def simple_aes_decrypt(text: str, key: Optional[str] = None, ivtext: Optional[str] = None) -> str:
    """
    是什么：simple_aes_decrypt 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    cipher = AES.new(
        _normalize_bytes(key or settings.SECRET_KEY[:32], 32),
        AES.MODE_CBC,
        _normalize_bytes(ivtext or simple_aes_iv_text, 16),
    )
    decrypted = cipher.decrypt(base64.b64decode(text))
    return unpad(decrypted, AES.block_size).decode("utf-8")
