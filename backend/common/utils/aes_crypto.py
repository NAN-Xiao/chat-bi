from typing import Optional

import base64

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from common.core.config import settings

simple_aes_iv_text = 'shuzhi_em_aes_iv'


def _normalize_bytes(text: str, size: int) -> bytes:
    """
    是什么：_normalize_bytes 是 backend/common/utils/aes_crypto.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：解析、转换或格式化通用工具相关数据，生成后续流程可使用的结构。
    """
    raw = (text or "").encode("utf-8")
    if len(raw) >= size:
        return raw[:size]
    return raw.ljust(size, b"\0")


def shuzhi_aes_encrypt(text: str, key: Optional[str] = None) -> str:
    """
    是什么：shuzhi_aes_encrypt 是 backend/common/utils/aes_crypto.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 shuzhi_aes_encrypt 的语义处理通用工具相关逻辑，并把结果返回或写入状态。
    """
    return simple_aes_encrypt(text, key)

def shuzhi_aes_decrypt(text: str, key: Optional[str] = None) -> str:
    """
    是什么：shuzhi_aes_decrypt 是 backend/common/utils/aes_crypto.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 shuzhi_aes_decrypt 的语义处理通用工具相关逻辑，并把结果返回或写入状态。
    """
    return simple_aes_decrypt(text, key)

def simple_aes_encrypt(text: str, key: Optional[str] = None, ivtext: Optional[str] = None) -> str:
    """
    是什么：simple_aes_encrypt 是 backend/common/utils/aes_crypto.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 simple_aes_encrypt 的语义处理通用工具相关逻辑，并把结果返回或写入状态。
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
    是什么：simple_aes_decrypt 是 backend/common/utils/aes_crypto.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 simple_aes_decrypt 的语义处理通用工具相关逻辑，并把结果返回或写入状态。
    """
    cipher = AES.new(
        _normalize_bytes(key or settings.SECRET_KEY[:32], 32),
        AES.MODE_CBC,
        _normalize_bytes(ivtext or simple_aes_iv_text, 16),
    )
    decrypted = cipher.decrypt(base64.b64decode(text))
    return unpad(decrypted, AES.block_size).decode("utf-8")
