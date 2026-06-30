import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from passlib.context import CryptContext
from passlib.exc import UnknownHashError

from common.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_MD5_HEX_RE = re.compile(r"^[a-fA-F0-9]{32}$")


ALGORITHM = "HS256"


def create_access_token(data: dict | Any, expires_delta: timedelta) -> str:
    """
    是什么：create_access_token 是 backend/common/core/security.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：创建、初始化或组装核心配置和基础设施相关对象和数据，并返回或写入对应状态。
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    # to_encode = {"exp": expire, "account": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    是什么：verify_password 是 backend/common/core/security.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验核心配置和基础设施相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    是什么：get_password_hash 是 backend/common/core/security.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询核心配置和基础设施相关数据，整理后返回给调用方。
    """
    return pwd_context.hash(password)


def hash_password(password: str) -> str:
    """
    是什么：hash_password 是 backend/common/core/security.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 hash_password 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    return get_password_hash(password)


def md5pwd(password: str) -> str:
    """
    是什么：md5pwd 是 backend/common/core/security.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 md5pwd 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    m = hashlib.md5()
    m.update(password.encode("utf-8"))
    return m.hexdigest()


def is_md5_password_hash(value: str | None) -> bool:
    """
    是什么：is_md5_password_hash 是 backend/common/core/security.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 is_md5_password_hash 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    return bool(value and _MD5_HEX_RE.fullmatch(value))


def verify_md5pwd(plain_password: str, md5_password: str) -> bool:
    """
    是什么：verify_md5pwd 是 backend/common/core/security.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验核心配置和基础设施相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    return md5pwd(plain_password) == md5_password


def verify_stored_password(plain_password: str, stored_password: str) -> tuple[bool, bool]:
    """
    是什么：verify_stored_password 是 backend/common/core/security.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验核心配置和基础设施相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    if is_md5_password_hash(stored_password):
        return verify_md5pwd(plain_password, stored_password), True
    try:
        return pwd_context.verify(plain_password, stored_password), pwd_context.needs_update(stored_password)
    except (UnknownHashError, ValueError):
        return False, False


def default_pwd() -> str:
    """
    是什么：default_pwd 是 backend/common/core/security.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 default_pwd 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    return settings.DEFAULT_PWD


def default_password_hash() -> str:
    """
    是什么：default_password_hash 是 backend/common/core/security.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 default_password_hash 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    return hash_password(default_pwd())


def default_md5_pwd() -> str:
    """
    是什么：default_md5_pwd 是 backend/common/core/security.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 default_md5_pwd 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    pwd = default_pwd()
    return md5pwd(pwd)
