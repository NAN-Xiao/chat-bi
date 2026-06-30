"""
脚本说明：这个脚本放通用工具相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
import base64
from hashlib import sha256

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from cryptography.fernet import Fernet, InvalidToken

from common.core.config import settings

_AES_KEY = b"Shuzhi1234567890"
_BUILTIN_LEGACY_AES_KEYS = (
    bytes([90, 104, 105, 115, 104, 117, 49, 50, 51, 52, 53, 54, 55, 56, 57, 48]),
)
_FERNET_PREFIX = "fernet:v1:"
_AES_KEY_SIZES = {16, 24, 32}


def _encryption_secret() -> str:
    """
    是什么：_encryption_secret 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return (
        settings.SENSITIVE_CONFIG_ENCRYPTION_KEY
        or settings.DATASOURCE_CONFIG_ENCRYPTION_KEY
        or settings.SECRET_KEY
    )


def _fernet() -> Fernet:
    """
    是什么：_fernet 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    derived = base64.urlsafe_b64encode(sha256(_encryption_secret().encode("utf-8")).digest())
    return Fernet(derived)


def _legacy_ecb_encrypt(text: str) -> str:
    """
    是什么：_legacy_ecb_encrypt 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    cipher = AES.new(_AES_KEY, AES.MODE_ECB)
    encrypted = cipher.encrypt(pad((text or "").encode("utf-8"), AES.block_size))
    return base64.b64encode(encrypted).decode("utf-8")


def _valid_aes_key(key: bytes) -> bytes | None:
    """
    是什么：_valid_aes_key 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return key if len(key) in _AES_KEY_SIZES else None


def _decode_legacy_key_token(token: str) -> bytes | None:
    """
    是什么：_decode_legacy_key_token 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if token.startswith("base64:"):
        try:
            return _valid_aes_key(base64.b64decode(token.removeprefix("base64:"), validate=True))
        except Exception:
            return None

    if token.startswith("hex:"):
        try:
            return _valid_aes_key(bytes.fromhex(token.removeprefix("hex:")))
        except Exception:
            return None

    try:
        decoded = _valid_aes_key(base64.b64decode(token, validate=True))
        if decoded:
            return decoded
    except Exception:
        pass

    try:
        decoded = _valid_aes_key(bytes.fromhex(token))
        if decoded:
            return decoded
    except Exception:
        pass

    return _valid_aes_key(token.encode("utf-8"))


def get_legacy_config_aes_keys() -> tuple[bytes, ...]:
    """
    是什么：get_legacy_config_aes_keys 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具需要的数据找出来，整理成后面好用的样子。
    """
    raw_value = settings.LEGACY_CONFIG_AES_KEYS or ""
    keys: list[bytes] = list(_BUILTIN_LEGACY_AES_KEYS)
    for token in raw_value.split(","):
        token = token.strip()
        if not token:
            continue
        key = _decode_legacy_key_token(token)
        if key and key not in keys:
            keys.append(key)
    return tuple(keys)


def _legacy_ecb_decrypt_with_key(text: str, key: bytes) -> str:
    """
    是什么：_legacy_ecb_decrypt_with_key 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    cipher = AES.new(key, AES.MODE_ECB)
    decrypted = cipher.decrypt(base64.b64decode(text))
    return unpad(decrypted, AES.block_size).decode("utf-8")


def _legacy_ecb_decrypt(text: str) -> str:
    """
    是什么：_legacy_ecb_decrypt 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    try:
        return _legacy_ecb_decrypt_with_key(text, _AES_KEY)
    except Exception:
        for legacy_key in get_legacy_config_aes_keys():
            try:
                return _legacy_ecb_decrypt_with_key(text, legacy_key)
            except Exception:
                continue
        raise


def encrypt_sensitive_text(text: str | None) -> str | None:
    """
    是什么：encrypt_sensitive_text 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
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
    """
    是什么：decrypt_sensitive_text 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
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
        # 对登录请求以及历史未加密记录保留明文兼容行为。
        # 兼容服务端密钥加密上线前已存在的记录。
        return text


def shuzhi_decrypt_sync(text: str | None) -> str | None:
    """
    是什么：shuzhi_decrypt_sync 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return decrypt_sensitive_text(text)


async def shuzhi_decrypt(text: str | None) -> str | None:
    """
    是什么：shuzhi_decrypt 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return shuzhi_decrypt_sync(text)


async def shuzhi_encrypt(text: str | None) -> str | None:
    """
    是什么：shuzhi_encrypt 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return encrypt_sensitive_text(text)


def legacy_shuzhi_encrypt_for_tests(text: str) -> str:
    """
    是什么：legacy_shuzhi_encrypt_for_tests 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return _legacy_ecb_encrypt(text)
